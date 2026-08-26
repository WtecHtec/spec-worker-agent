import os
import sys
import asyncio
import signal
import uuid
import structlog
from datetime import datetime, timezone
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.config.settings import get_settings
from src.infrastructure.db.database import AsyncSessionLocal
from src.infrastructure.db.models import TaskStepModel
from src.infrastructure.db.repositories import (
    TaskRepository, CheckpointRepository, MessageRepository, FileRepository,
)
from src.application.file.use_cases import detect_category_and_mime
from src.infrastructure.redis.client import get_redis
from src.infrastructure.redis.adapters import RedisTaskQueue, RedisPubSub, RedisLock
from src.infrastructure.executor.factory import create_executor

settings = get_settings()
logger = structlog.get_logger()

WORKER_ID = f"worker-{uuid.uuid4().hex[:8]}"
_shutdown = False
_signal_count = 0


def _handle_signal(sig, frame):
    global _shutdown, _signal_count
    _signal_count += 1
    logger.info("shutdown_signal_received", signal=sig, count=_signal_count)
    _shutdown = True
    if _signal_count >= 2:
        logger.warning("force_exit_immediately")
        os._exit(130)


async def process_task(task_id: str, resume_from_step: int, msg_id: str):
    log = logger.bind(task_id=task_id, worker_id=WORKER_ID)

    async with AsyncSessionLocal() as db:
        task_repo = TaskRepository(db)
        ckpt_repo = CheckpointRepository(db)
        msg_repo = MessageRepository(db)
        redis = await get_redis()
        queue = RedisTaskQueue(redis)
        pubsub = RedisPubSub(redis)
        lock = RedisLock(redis)

        # 1. 获取分布式锁
        acquired = await lock.acquire(task_id, WORKER_ID)
        if not acquired:
            log.warning("lock_acquire_failed_skip")
            return

        try:
            # 2. 加载任务和 Checkpoint（优先校验是否已被取消）
            if await redis.exists(f"task:cancelled:{task_id}"):
                log.info("task_already_cancelled_before_execution")
                await queue.ack(msg_id)
                return

            task = await task_repo.get_by_id(task_id)
            if not task or task.status in ("COMPLETED", "FAILED", "CANCELLED"):
                log.info("task_already_finished", status=task.status if task else "not_found")
                await queue.ack(msg_id)
                return

            checkpoint = await ckpt_repo.get_by_task(task_id)
            if not checkpoint:
                log.error("checkpoint_not_found")
                return

            # 3. 标记 RUNNING
            now = datetime.now(timezone.utc)
            await task_repo.update_status(
                task_id, "RUNNING",
                worker_id=WORKER_ID,
                worker_heartbeat=now,
                started_at=now,
            )
            await db.commit()
            # 4. 加载会话最近 10 条历史消息上下文（供 Planner / ReAct 理解多轮连续指令如“继续”）
            history_messages = []
            if task.session_id:
                raw_msgs = await msg_repo.list_by_session(task.session_id, limit=15)
                for m in raw_msgs:
                    # 过滤当前任务对应的触发消息与流式占位消息
                    if m.task_id == task.id or (m.role == "AGENT" and m.status == "streaming" and not m.content.get("text")):
                        continue
                    text = m.content.get("text") or m.content.get("summary") or ""
                    if text.strip():
                        history_messages.append({
                            "role": "user" if m.role == "USER" else "assistant",
                            "content": text.strip(),
                        })
                history_messages = history_messages[-10:]

            task_input = dict(task.input) if isinstance(task.input, dict) else {"content": str(task.input)}
            task_input["user_id"] = task.user_id
            task_input["task_id"] = task.id
            task_input["session_id"] = task.session_id
            task_input["history_messages"] = history_messages

            executor = create_executor(task_input, resume_from_step=resume_from_step)
            current_version = checkpoint.version
            last_step = resume_from_step

            # 5. 执行循环
            async for step in executor.run():
                # 检查任务是否已被用户取消（Redis 快速感知 + DB 实时检查）
                if await redis.exists(f"task:cancelled:{task_id}"):
                    log.info("task_was_cancelled_by_redis_signal")
                    await queue.ack(msg_id)
                    return

                db.expire_all()
                fresh_task = await task_repo.get_by_id(task_id)
                if not fresh_task or fresh_task.status == "CANCELLED":
                    log.info("task_was_cancelled_aborting")
                    await queue.ack(msg_id)
                    return

                if _shutdown:
                    log.info("graceful_shutdown_pause")
                    await task_repo.update_status(task_id, "PAUSED",
                                                  paused_reason="worker_shutdown")
                    await db.commit()
                    return

                step_index = step["step_index"]
                step_type = step["type"]
                content = step["content"]

                # 幂等写入步骤
                stmt = pg_insert(TaskStepModel).values(
                    task_id=task_id,
                    step_index=step_index,
                    type=step_type,
                    content=content,
                ).on_conflict_do_nothing(constraint="uq_task_step")
                await db.execute(stmt)

                # 自动捕获工具产生的文件并入库
                if step_type == "TOOL_RESULT" and isinstance(content, dict) and not content.get("is_error"):
                    meta = content.get("metadata") or {}
                    file_path = meta.get("file_path")
                    if file_path and task.session_id:
                        try:
                            file_repo = FileRepository(db)
                            file_size = int(meta.get("bytes") or meta.get("file_size") or 0)
                            cat, mime = detect_category_and_mime(file_path)
                            file_name = os.path.basename(file_path) or file_path
                            await file_repo.upsert(
                                session_id=task.session_id,
                                user_id=task.user_id,
                                file_path=file_path,
                                file_name=file_name,
                                file_size=file_size,
                                mime_type=mime,
                                category=cat,
                                storage_type=meta.get("mode") or "sandbox",
                                task_id=task_id,
                            )
                            log.info("auto_recorded_session_file", file_path=file_path, session_id=task.session_id)
                        except Exception as file_err:
                            log.warning("failed_to_auto_record_file", error=str(file_err), file_path=file_path)

                # 更新 Checkpoint（乐观锁）
                ok = await ckpt_repo.update(
                    task_id, step_index, expected_version=current_version
                )
                if not ok:
                    # 如果由于重试或并发导致版本冲突，重新加载版本继续
                    fresh_ckpt = await ckpt_repo.get_by_task(task_id)
                    if fresh_ckpt:
                        current_version = fresh_ckpt.version
                        await ckpt_repo.update(task_id, step_index, expected_version=current_version)

                current_version += 1
                last_step = step_index
                await db.commit()

                # 心跳续期
                await lock.renew(task_id, WORKER_ID)
                await task_repo.update_status(task_id, "RUNNING",
                                              worker_heartbeat=datetime.now(timezone.utc))
                await db.commit()

                # 通知 SSE Handler
                await pubsub.publish(task_id, {
                    "event": "new_step",
                    "task_id": task_id,
                    "step_index": step_index,
                    "step_type": step_type,
                })
                log.info("step_completed", step_index=step_index, type=step_type)

                # HITL：写请求后暂停任务并退出
                if step.get("wait_for_human"):
                    from src.infrastructure.db.models import HitlRequestModel
                    from datetime import timedelta
                    hitl = HitlRequestModel(
                        task_id=task_id,
                        step_index=step_index,
                        type=content.get("type", "choice"),
                        question=content.get("question", ""),
                        options=content.get("options"),
                        expires_at=datetime.now(timezone.utc) + timedelta(
                            hours=settings.hitl_default_timeout_hours
                        ),
                    )
                    db.add(hitl)
                    await task_repo.update_status(task_id, "WAITING_HUMAN")

                    # 同步更新 AGENT 占位消息状态
                    agent_msg = await msg_repo.get_by_task_id(task_id)
                    if agent_msg:
                        await msg_repo.update_message(
                            agent_msg.id,
                            status="streaming",
                            content={
                                **agent_msg.content,
                                "task_status": "WAITING_HUMAN",
                                "hitl_question": content.get("question", ""),
                            }
                        )

                    await db.commit()
                    await pubsub.publish(task_id, {
                        "event": "hitl_created",
                        "task_id": task_id,
                        "hitl_id": hitl.id,
                        "question": content.get("question"),
                        "options": content.get("options"),
                    })
                    await queue.ack(msg_id)
                    log.info("task_waiting_human", step_index=step_index)
                    return

            # 6. 任务完成
            # 再次检查是否被取消
            fresh_task = await task_repo.get_by_id(task_id)
            if await redis.exists(f"task:cancelled:{task_id}"):
                log.info("task_cancelled_by_redis_signal_at_finish")
                await queue.ack(msg_id)
                return

            db.expire_all()
            fresh_task = await task_repo.get_by_id(task_id)
            if fresh_task and fresh_task.status == "CANCELLED":
                log.info("task_cancelled_at_finish_aborting")
                await queue.ack(msg_id)
                return

            result = executor.get_result()
            await task_repo.update_status(
                task_id, "COMPLETED",
                result=result,
                completed_at=datetime.now(timezone.utc),
            )

            # 更新 AGENT 占位消息为 done
            agent_msg = await msg_repo.get_by_task_id(task_id)
            if agent_msg:
                final_text = result.get("summary", "任务执行完成。")
                await msg_repo.update_message(
                    agent_msg.id,
                    status="done",
                    content={
                        **agent_msg.content,
                        "text": final_text,
                        "task_status": "COMPLETED",
                        "summary": result.get("summary", ""),
                    }
                )
            await db.commit()

            await pubsub.publish(task_id, {
                "event": "task_completed",
                "task_id": task_id,
                "result": result,
            })
            await queue.ack(msg_id)
            log.info("task_completed")

        except Exception as e:
            log.exception("task_error", error=str(e))
            await task_repo.update_status(task_id, "FAILED", error=str(e))
            agent_msg = await msg_repo.get_by_task_id(task_id)
            if agent_msg:
                await msg_repo.update_message(
                    agent_msg.id,
                    status="failed",
                    content={
                        **agent_msg.content,
                        "text": f"任务执行出错: {str(e)}",
                        "task_status": "FAILED",
                        "error": str(e),
                    }
                )
            await db.commit()
            await queue.ack(msg_id)
        finally:
            await lock.release(task_id, WORKER_ID)


async def worker_loop():
    redis = await get_redis()
    queue = RedisTaskQueue(redis)
    await queue.ensure_group()
    logger.info("worker_started", worker_id=WORKER_ID)

    while not _shutdown:
        try:
            messages = await queue.consume(WORKER_ID, count=1, block_ms=3000)
            for msg in messages:
                await process_task(
                    task_id=msg["task_id"],
                    resume_from_step=msg["resume_from_step"],
                    msg_id=msg["msg_id"],
                )
        except Exception as e:
            logger.exception("worker_loop_error", error=str(e))
            await asyncio.sleep(2)

    logger.info("worker_stopped")


async def main():
    from src.application.worker.recovery import recover_paused_tasks, recovery_scheduler_loop

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # 1. 启动时扫描并恢复上一次优雅退出遗留的 PAUSED 任务
    try:
        await recover_paused_tasks()
    except Exception as e:
        logger.exception("startup_recovery_failed", error=str(e))

    # 2. 启动后台定时巡检任务（僵尸任务回收 + HITL 超时处理）
    scheduler_task = asyncio.create_task(recovery_scheduler_loop(interval_seconds=10))

    # 3. 启动跨进程工具缓存失效监听器（接收 API 端 MCP/A2A 配置变动广播）
    from src.domain.services.tools.manager import user_tool_registry_manager
    invalidation_listener_task = asyncio.create_task(
        user_tool_registry_manager.start_invalidation_listener()
    )

    # 4. 启动并发工作协程
    workers = [asyncio.create_task(worker_loop())
               for _ in range(settings.worker_concurrency)]

    try:
        while not _shutdown:
            await asyncio.sleep(0.3)
            # 若所有 worker 都已结束则退出
            if all(w.done() for w in workers):
                break
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        for w in workers:
            w.cancel()
        scheduler_task.cancel()
        invalidation_listener_task.cancel()
        await asyncio.gather(*workers, scheduler_task, invalidation_listener_task, return_exceptions=True)
        logger.info("worker_main_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
