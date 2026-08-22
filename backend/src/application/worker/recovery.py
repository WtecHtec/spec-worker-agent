import asyncio
import structlog
from datetime import datetime, timezone

from src.config.settings import get_settings
from src.infrastructure.db.database import AsyncSessionLocal
from src.infrastructure.db.repositories import (
    TaskRepository, CheckpointRepository, MessageRepository, HitlRepository,
)
from src.infrastructure.redis.client import get_redis
from src.infrastructure.redis.adapters import RedisTaskQueue, RedisPubSub

settings = get_settings()
logger = structlog.get_logger()


async def recover_paused_tasks():
    """扫描并恢复因 Worker 优雅退出而 PAUSED 的任务"""
    async with AsyncSessionLocal() as db:
        task_repo = TaskRepository(db)
        ckpt_repo = CheckpointRepository(db)
        redis = await get_redis()
        queue = RedisTaskQueue(redis)

        paused_tasks = await task_repo.list_paused_shutdown_tasks()
        for task in paused_tasks:
            ckpt = await ckpt_repo.get_by_task(task.id)
            resume_from = ckpt.last_completed_step if ckpt else 0
            await task_repo.update_status(task.id, "PENDING", paused_reason=None)
            await db.commit()
            await queue.enqueue(task.id, priority=task.priority, resume_from_step=resume_from)
            logger.info("paused_task_resumed", task_id=task.id, resume_from_step=resume_from)


async def recover_zombie_tasks():
    """扫描心跳超时（Worker 崩溃或失联）的僵尸任务并重新入队"""
    async with AsyncSessionLocal() as db:
        task_repo = TaskRepository(db)
        ckpt_repo = CheckpointRepository(db)
        redis = await get_redis()
        queue = RedisTaskQueue(redis)

        zombies = await task_repo.list_zombie_tasks(
            timeout_seconds=settings.worker_heartbeat_timeout
        )
        for task in zombies:
            ckpt = await ckpt_repo.get_by_task(task.id)
            resume_from = ckpt.last_completed_step if ckpt else 0
            await task_repo.update_status(
                task.id, "PENDING",
                worker_id=None,
                worker_heartbeat=None,
            )
            await db.commit()
            await queue.enqueue(task.id, priority=task.priority, resume_from_step=resume_from)
            logger.warning("zombie_task_recovered", task_id=task.id, resume_from_step=resume_from)


async def process_expired_hitl():
    """扫描并处理超时的 HITL 请求"""
    async with AsyncSessionLocal() as db:
        hitl_repo = HitlRepository(db)
        task_repo = TaskRepository(db)
        msg_repo = MessageRepository(db)
        ckpt_repo = CheckpointRepository(db)
        redis = await get_redis()
        pubsub = RedisPubSub(redis)
        queue = RedisTaskQueue(redis)

        expired_list = await hitl_repo.list_expired_requests()
        for hitl in expired_list:
            await hitl_repo.mark_expired(hitl.id)
            task = await task_repo.get_by_id(hitl.task_id)
            if not task or task.status != "WAITING_HUMAN":
                continue

            if hitl.default_action == "proceed" and hitl.options:
                # 默认选项自动继续
                default_choice = hitl.options[0].get("value", "")
                await hitl_repo.resolve(hitl.id, decision=default_choice)
                ckpt = await ckpt_repo.get_by_task(task.id)
                resume_from = ckpt.last_completed_step if ckpt else 0
                await task_repo.update_status(task.id, "PENDING")
                await db.commit()
                await queue.enqueue(task.id, priority=task.priority, resume_from_step=resume_from)
                logger.info("expired_hitl_auto_proceed", task_id=task.id, choice=default_choice)
            else:
                # 默认取消/失败
                now = datetime.now(timezone.utc)
                await task_repo.update_status(
                    task.id, "FAILED",
                    error="HITL request timed out",
                    completed_at=now,
                )
                agent_msg = await msg_repo.get_by_task_id(task.id)
                if agent_msg:
                    await msg_repo.update_message(
                        agent_msg.id,
                        status="failed",
                        content={
                            **agent_msg.content,
                            "text": "人工确认已超时，任务已自动终止。",
                            "task_status": "FAILED",
                            "error": "HITL timeout",
                        }
                    )
                await db.commit()
                await pubsub.publish(task.id, {
                    "event": "task_failed",
                    "task_id": task.id,
                    "error": "HITL request timed out",
                })
                logger.info("expired_hitl_auto_cancelled", task_id=task.id)


async def recovery_scheduler_loop(interval_seconds: int = 15):
    """定时后台巡检任务"""
    logger.info("recovery_scheduler_started", interval=interval_seconds)
    while True:
        try:
            await recover_zombie_tasks()
            await process_expired_hitl()
        except Exception as e:
            logger.exception("recovery_scheduler_error", error=str(e))
        await asyncio.sleep(interval_seconds)
