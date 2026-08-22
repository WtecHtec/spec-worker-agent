import asyncio
import json
from datetime import datetime, timedelta, timezone
import httpx

from src.infrastructure.db.database import AsyncSessionLocal
from src.infrastructure.db.models import (
    UserModel, SessionModel, MessageModel, TaskModel, TaskCheckpointModel, HitlRequestModel
)
from src.infrastructure.redis.client import get_redis
from src.infrastructure.redis.adapters import RedisLock, RedisTaskQueue
from src.application.worker.recovery import (
    recover_zombie_tasks, recover_paused_tasks, process_expired_hitl
)

BASE_URL = "http://localhost:8000"


async def main():
    print("========================================")
    print("       P2 可靠性与异常恢复 自动化测试       ")
    print("========================================")

    # 1. 测试健康检查与队列监控
    print("\n─── 1. 测试系统健康检查与 Redis 队列统计 ───")
    async with httpx.AsyncClient(base_url=BASE_URL) as client:
        resp = await client.get("/health/ready")
        assert resp.status_code == 200, f"Health check failed: {resp.text}"
        data = resp.json()
        print(f"✅ 健康检查状态: {data['status']}")
        print(f"   Database: {data['database']}")
        print(f"   Queue Stats: {json.dumps(data['queue'], ensure_ascii=False)}")
        assert data["database"] == "ok"
        assert "stream_length" in data["queue"]

    # 2. 测试分布式锁并发互斥
    print("\n─── 2. 测试 Redis 分布式锁互斥与释放 ───")
    redis = await get_redis()
    lock = RedisLock(redis)
    test_task_id = "test-lock-task-123"

    ok1 = await lock.acquire(test_task_id, "worker-A", ttl=10)
    assert ok1 is True, "Worker A 获取锁失败"
    print("✅ Worker A 成功获取分布式锁")

    ok2 = await lock.acquire(test_task_id, "worker-B", ttl=10)
    assert ok2 is False, "Worker B 在锁被占用时不应获取成功"
    print("✅ Worker B 获取锁被拒绝（互斥生效）")

    # Worker A 续期
    renewed = await lock.renew(test_task_id, "worker-A", ttl=15)
    assert renewed is True, "Worker A 续期失败"
    print("✅ Worker A 锁续期成功")

    # Worker A 释放锁
    await lock.release(test_task_id, "worker-A")
    print("✅ Worker A 释放锁")

    # Worker B 现在应该能获取
    ok3 = await lock.acquire(test_task_id, "worker-B", ttl=10)
    assert ok3 is True, "Worker B 应该能获取已释放的锁"
    print("✅ Worker B 成功获取已释放的锁")
    await lock.release(test_task_id, "worker-B")

    # 3. 测试僵尸任务自动回收 (Zombie Task Recovery)
    print("\n─── 3. 测试僵尸任务检测与自动重新入队 ───")
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(UserModel).limit(1))
        user = res.scalar_one_or_none()
        if not user:
            user = UserModel(email="recovery_test@example.com", hashed_password="xxx", display_name="Test")
            db.add(user)
            await db.flush()
        valid_user_id = user.id

        # 创建一个模拟崩溃的僵尸任务（心跳超时 120 秒前）
        zombie_task = TaskModel(
            user_id=valid_user_id,
            title="僵尸任务测试",
            input={"type": "text", "content": "sales"},
            status="RUNNING",
            worker_id="crashed-worker-999",
            worker_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=120),
        )
        db.add(zombie_task)
        await db.flush()

        ckpt = TaskCheckpointModel(
            task_id=zombie_task.id,
            last_completed_step=3,
            version=4,
        )
        db.add(ckpt)
        await db.commit()
        zombie_id = zombie_task.id
        print(f"👉 创建了僵尸任务: id={zombie_id}, heartbeat=120s ago")

    # 执行僵尸任务回收
    await recover_zombie_tasks()

    # 检查状态是否重置为 PENDING
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(TaskModel).where(TaskModel.id == zombie_id))
        recovered_task = res.scalar_one()
        assert recovered_task.status == "PENDING", f"期望 PENDING，实际 {recovered_task.status}"
        assert recovered_task.worker_id is None
        print(f"✅ 僵尸任务已被恢复器重置为 PENDING 并重新推入队列！")

    # 4. 测试 Worker 优雅退出 PAUSED 任务恢复
    print("\n─── 4. 测试优雅退出后 PAUSED 任务的重启恢复 ───")
    async with AsyncSessionLocal() as db:
        paused_task = TaskModel(
            user_id=valid_user_id,
            title="优雅退出暂停任务",
            input={"type": "text", "content": "sales"},
            status="PAUSED",
            paused_reason="worker_shutdown",
        )
        db.add(paused_task)
        await db.flush()
        db.add(TaskCheckpointModel(task_id=paused_task.id, last_completed_step=2))
        await db.commit()
        paused_id = paused_task.id
        print(f"👉 创建了 PAUSED 任务: id={paused_id}")

    # 执行启动恢复
    await recover_paused_tasks()

    async with AsyncSessionLocal() as db:
        res = await db.execute(select(TaskModel).where(TaskModel.id == paused_id))
        resumed_task = res.scalar_one()
        assert resumed_task.status == "PENDING"
        assert resumed_task.paused_reason is None
        print("✅ PAUSED 任务已被成功恢复并重新入队！")

    # 5. 测试 HITL 超时自动处理 (HITL Timeout Sweeper)
    print("\n─── 5. 测试 HITL 审批超时自动取消机制 ───")
    async with AsyncSessionLocal() as db:
        # 创建会话和消息
        session = SessionModel(user_id=valid_user_id, title="HITL超时测试")
        db.add(session)
        await db.flush()

        timed_out_task = TaskModel(
            user_id=valid_user_id,
            session_id=session.id,
            title="HITL超时任务",
            input={"type": "text", "content": "file"},
            status="WAITING_HUMAN",
        )
        db.add(timed_out_task)
        await db.flush()

        agent_msg = MessageModel(
            session_id=session.id,
            role="AGENT",
            content={"text": "等待人工确认", "task_id": timed_out_task.id, "task_status": "WAITING_HUMAN"},
            task_id=timed_out_task.id,
            status="streaming",
        )
        db.add(agent_msg)
        await db.flush()

        # 创建一个已过期的 HITL 请求 (expires_at 设为 30秒前)
        expired_hitl = HitlRequestModel(
            task_id=timed_out_task.id,
            step_index=4,
            type="choice",
            question="超时测试问题",
            default_action="cancel",
            status="PENDING",
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=30),
        )
        db.add(expired_hitl)
        await db.commit()
        hitl_task_id = timed_out_task.id
        hitl_id = expired_hitl.id
        print(f"👉 创建了超时的 HITL 请求: id={hitl_id}, task_id={hitl_task_id}")

    # 执行超时清理
    await process_expired_hitl()

    async with AsyncSessionLocal() as db:
        h_res = await db.execute(select(HitlRequestModel).where(HitlRequestModel.id == hitl_id))
        h = h_res.scalar_one()
        assert h.status == "EXPIRED", f"期望 EXPIRED，实际 {h.status}"

        t_res = await db.execute(select(TaskModel).where(TaskModel.id == hitl_task_id))
        t = t_res.scalar_one()
        assert t.status == "FAILED", f"期望 FAILED，实际 {t.status}"
        assert "timed out" in t.error

        m_res = await db.execute(select(MessageModel).where(MessageModel.task_id == hitl_task_id, MessageModel.role == "AGENT"))
        m = m_res.scalar_one()
        assert m.status == "failed"
        print(f"✅ HITL 超时处理成功：HITL=EXPIRED, Task=FAILED, Message=failed！")

    print("\n🎉 P2 所有可靠性保障功能（分布式锁、僵尸任务恢复、优雅退出恢复、HITL超时策略、队列监控）全部测试通过！")


if __name__ == "__main__":
    asyncio.run(main())
