from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import (
    TaskRepository, CheckpointRepository, HitlRepository,
)
from src.infrastructure.redis.client import get_redis
from src.infrastructure.redis.adapters import RedisTaskQueue
from src.interface.middleware.auth import get_current_user_id
from src.application.hitl.use_cases import GetPendingHitlUseCase, RespondHitlUseCase

router = APIRouter(prefix="/tasks", tags=["hitl"])


class HitlResponse(BaseModel):
    id: str
    task_id: str
    step_index: int
    type: str
    question: str
    options: list | None
    status: str
    expires_at: str


class RespondHitlRequest(BaseModel):
    decision: str                   # 选项 value 或文字输入
    user_input: dict | None = None  # form 类型时的额外数据


@router.get("/{task_id}/hitl/pending", response_model=HitlResponse | None)
async def get_pending_hitl(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询当前任务待响应的 HITL 请求（委托 GetPendingHitlUseCase）"""
    use_case = GetPendingHitlUseCase(
        task_repo=TaskRepository(db),
        hitl_repo=HitlRepository(db),
    )
    hitl = await use_case.execute(task_id=task_id, user_id=user_id)
    if not hitl:
        return None

    return HitlResponse(
        id=hitl.id,
        task_id=hitl.task_id,
        step_index=hitl.step_index,
        type=hitl.type,
        question=hitl.question,
        options=hitl.options,
        status=hitl.status,
        expires_at=str(hitl.expires_at) if hitl.expires_at else "",
    )


@router.post("/{task_id}/hitl/{hitl_id}/respond")
async def respond_hitl(
    task_id: str,
    hitl_id: str,
    body: RespondHitlRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """提交人工审批决策端点（委托 RespondHitlUseCase）"""
    redis = await get_redis()
    queue = RedisTaskQueue(redis)
    await queue.ensure_group()

    use_case = RespondHitlUseCase(
        db=db,
        task_repo=TaskRepository(db),
        hitl_repo=HitlRepository(db),
        ckpt_repo=CheckpointRepository(db),
        queue=queue,
    )
    result = await use_case.execute(
        task_id=task_id,
        hitl_id=hitl_id,
        user_id=user_id,
        decision=body.decision,
        user_input=body.user_input,
    )
    return {
        "message": result.message,
        "resume_from_step": result.resume_from_step,
        "task_id": result.task_id,
    }
