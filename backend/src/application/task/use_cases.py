"""
任务管理应用用例（取消任务、查询详情、查询步骤流水）
"""
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.models import Task, TaskStep
from src.domain.exceptions import TaskNotFoundException
from src.domain.repositories.task import ITaskRepository, ITaskStepRepository
from src.domain.repositories.session import IMessageRepository
from src.domain.interfaces.infrastructure import IEventPublisher


class CancelTaskUseCase:
    """取消任务用例"""

    def __init__(
        self,
        db: AsyncSession,
        task_repo: ITaskRepository,
        msg_repo: IMessageRepository,
        event_publisher: IEventPublisher,
    ):
        self.db = db
        self.task_repo = task_repo
        self.msg_repo = msg_repo
        self.event_publisher = event_publisher

    async def execute(self, task_id: str, user_id: str) -> Task:
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            raise TaskNotFoundException(task_id)

        # 若已处于终态，直接返回当前实体
        if task.is_terminal:
            return task

        now = datetime.now(timezone.utc)
        task.cancel(now)
        updated_task = await self.task_repo.update_status(
            task_id,
            status="CANCELLED",
            error="Cancelled by user",
            completed_at=now,
        )

        # 同步更新 AGENT 占位消息状态
        agent_msg = await self.msg_repo.get_by_task_id(task_id)
        if agent_msg:
            await self.msg_repo.update_message(
                agent_msg.id,
                status="failed",
                content={
                    **agent_msg.content,
                    "text": "任务已被取消。",
                    "task_status": "CANCELLED",
                },
            )

        await self.db.commit()

        # 发布取消广播事件
        await self.event_publisher.publish(task_id, {
            "event": "task_cancelled",
            "task_id": task_id,
        })

        return updated_task or task


class GetTaskDetailUseCase:
    """获取任务详情用例"""

    def __init__(self, task_repo: ITaskRepository):
        self.task_repo = task_repo

    async def execute(self, task_id: str, user_id: str) -> Task:
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            raise TaskNotFoundException(task_id)
        return task


class GetTaskStepsUseCase:
    """获取任务步骤流水用例"""

    def __init__(
        self,
        task_repo: ITaskRepository,
        step_repo: ITaskStepRepository,
    ):
        self.task_repo = task_repo
        self.step_repo = step_repo

    async def execute(self, task_id: str, user_id: str, after_step: int = 0) -> list[TaskStep]:
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            raise TaskNotFoundException(task_id)

        return await self.step_repo.list_after(task_id, after_index=after_step)
