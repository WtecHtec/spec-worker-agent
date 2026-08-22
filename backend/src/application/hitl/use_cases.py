"""
人机协同 (HITL) 应用用例（查询待审批、响应审批、恢复入队）
"""
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.models import HitlRequest
from src.domain.exceptions import TaskNotFoundException, HitlRequestNotFoundException
from src.domain.repositories.task import ITaskRepository, ICheckpointRepository
from src.domain.repositories.hitl import IHitlRepository
from src.domain.interfaces.infrastructure import ITaskQueue
from src.domain.services.hitl import HitlDecisionService


@dataclass
class RespondHitlResult:
    message: str
    resume_from_step: int
    task_id: str


class GetPendingHitlUseCase:
    """获取任务当前待审批请求用例"""

    def __init__(
        self,
        task_repo: ITaskRepository,
        hitl_repo: IHitlRepository,
    ):
        self.task_repo = task_repo
        self.hitl_repo = hitl_repo

    async def execute(self, task_id: str, user_id: str) -> Optional[HitlRequest]:
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            raise TaskNotFoundException(task_id)

        return await self.hitl_repo.get_pending_by_task(task_id)


class RespondHitlUseCase:
    """响应人工审批用例"""

    def __init__(
        self,
        db: AsyncSession,
        task_repo: ITaskRepository,
        hitl_repo: IHitlRepository,
        ckpt_repo: ICheckpointRepository,
        queue: ITaskQueue,
    ):
        self.db = db
        self.task_repo = task_repo
        self.hitl_repo = hitl_repo
        self.ckpt_repo = ckpt_repo
        self.queue = queue

    async def execute(
        self,
        task_id: str,
        hitl_id: str,
        user_id: str,
        decision: str,
        user_input: Optional[dict] = None,
    ) -> RespondHitlResult:
        # 1. 验证任务归属
        task = await self.task_repo.get_by_id(task_id)
        if not task or task.user_id != user_id:
            raise TaskNotFoundException(task_id)

        # 2. 获取审批请求
        hitl = await self.hitl_repo.get_by_id(hitl_id)
        if not hitl or hitl.task_id != task_id:
            raise HitlRequestNotFoundException(hitl_id)

        # 3. 领域服务校验并应用决策
        HitlDecisionService.validate_and_apply(hitl, decision, user_input)

        # 4. 持久化审批结果
        await self.hitl_repo.resolve(hitl_id, decision, user_input)

        # 5. 更新任务状态为 PENDING
        await self.task_repo.update_status(task_id, "PENDING")
        await self.db.commit()

        # 6. 读取断点并重新入队
        ckpt = await self.ckpt_repo.get_by_task(task_id)
        resume_from = ckpt.last_completed_step if ckpt else hitl.step_index
        await self.queue.enqueue(task_id, priority=task.priority, resume_from_step=resume_from)

        return RespondHitlResult(
            message="ok",
            resume_from_step=resume_from,
            task_id=task_id,
        )
