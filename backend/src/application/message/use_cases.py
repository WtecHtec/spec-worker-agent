"""
消息与任务触发应用用例（编排发消息、权限检查、并发互斥、任务创建与入队）
"""
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.models import Message, Task
from src.domain.exceptions import SessionNotFoundException, UserNotFoundException
from src.domain.repositories.user import IUserRepository
from src.domain.repositories.session import ISessionRepository, IMessageRepository
from src.domain.repositories.task import ITaskRepository, ICheckpointRepository
from src.domain.interfaces.infrastructure import ITaskQueue
from src.domain.services.scheduler import TaskSchedulerService


@dataclass
class SendMessageResult:
    message_id: str
    task_id: str
    session_id: str
    status: str = "streaming"


class SendMessageUseCase:
    """
    发消息核心用例：
    1. 验证会话权限与归属
    2. 执行单用户全局最大并发配额校验 (TaskSchedulerService)
    3. 执行同会话未完结任务互斥冲突校验 (TaskSchedulerService)
    4. 写入 USER 消息与 AGENT 占位消息
    5. 创建 Task 实体 (PENDING) 并初始化 Checkpoint
    6. 推入 Redis Stream 任务队列
    7. 事务提交并返回结果
    """

    def __init__(
        self,
        db: AsyncSession,
        user_repo: IUserRepository,
        session_repo: ISessionRepository,
        message_repo: IMessageRepository,
        task_repo: ITaskRepository,
        ckpt_repo: ICheckpointRepository,
        queue: ITaskQueue,
    ):
        self.db = db
        self.user_repo = user_repo
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.ckpt_repo = ckpt_repo
        self.queue = queue

    async def execute(self, session_id: str, user_id: str, content: str) -> SendMessageResult:
        # 1. 验证会话归属
        session = await self.session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id:
            raise SessionNotFoundException(session_id)

        # 2. 检查单用户全局并发配额
        user = await self.user_repo.get_by_id(user_id)
        active_count = await self.task_repo.count_active_by_user(user_id)
        TaskSchedulerService.validate_user_quota(user, active_count)

        # 3. 检查单会话并发互斥
        running_task = await self.task_repo.get_active_in_session(session_id)
        TaskSchedulerService.validate_session_concurrency(session_id, running_task)

        # 4. 计算优先级
        priority = TaskSchedulerService.assign_priority(user, content)

        # 5. 写入 USER 消息
        user_msg = await self.message_repo.create_user_message(session_id, content)

        # 6. 创建 Task 实体 (PENDING)
        task = await self.task_repo.create(
            user_id=user_id,
            input_data={"type": "text", "content": content},
            session_id=session_id,
            title=content[:50],
            priority=priority,
        )

        # 7. 创建 AGENT 占位消息与初始 Checkpoint
        agent_msg = await self.message_repo.create_agent_placeholder(session_id, task.id)
        await self.task_repo.set_trigger_message(task.id, user_msg.id)
        await self.ckpt_repo.create(task.id)

        # 8. 提交数据库事务
        await self.db.commit()

        # 9. 推入 Redis Stream 队列
        await self.queue.enqueue(task.id, priority=priority, resume_from_step=0)

        return SendMessageResult(
            message_id=agent_msg.id,
            task_id=task.id,
            session_id=session_id,
            status="streaming",
        )


class GetSessionMessagesUseCase:
    """获取会话消息历史用例"""

    def __init__(
        self,
        session_repo: ISessionRepository,
        message_repo: IMessageRepository,
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo

    async def execute(self, session_id: str, user_id: str, after_seq: int = 0) -> list[Message]:
        session = await self.session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id:
            raise SessionNotFoundException(session_id)

        return await self.message_repo.list_by_session(session_id, after_seq=after_seq)
