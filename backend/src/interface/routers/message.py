from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import (
    UserRepository, SessionRepository, MessageRepository, TaskRepository, CheckpointRepository,
)
from src.infrastructure.redis.client import get_redis
from src.infrastructure.redis.adapters import RedisTaskQueue
from src.interface.middleware.auth import get_current_user_id
from src.application.message.use_cases import SendMessageUseCase, GetSessionMessagesUseCase

router = APIRouter(prefix="/sessions", tags=["messages"])


class SendMessageRequest(BaseModel):
    content: str


class SendMessageResponse(BaseModel):
    message_id: str
    task_id: str
    stream_url: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content_type: str
    content: dict
    task_id: str | None
    status: str
    seq: int
    created_at: str


@router.post("/{session_id}/messages", response_model=SendMessageResponse, status_code=201)
async def send_message(
    session_id: str,
    body: SendMessageRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """发送消息触发异步任务端点（委托 SendMessageUseCase）"""
    redis = await get_redis()
    queue = RedisTaskQueue(redis)
    await queue.ensure_group()

    use_case = SendMessageUseCase(
        db=db,
        user_repo=UserRepository(db),
        session_repo=SessionRepository(db),
        message_repo=MessageRepository(db),
        task_repo=TaskRepository(db),
        ckpt_repo=CheckpointRepository(db),
        queue=queue,
    )
    result = await use_case.execute(session_id=session_id, user_id=user_id, content=body.content)

    return SendMessageResponse(
        message_id=result.message_id,
        task_id=result.task_id,
        stream_url=f"/tasks/{result.task_id}/stream",
    )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_session_messages(
    session_id: str,
    after_seq: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取会话消息历史（委托 GetSessionMessagesUseCase）"""
    use_case = GetSessionMessagesUseCase(
        session_repo=SessionRepository(db),
        message_repo=MessageRepository(db),
    )
    messages = await use_case.execute(session_id=session_id, user_id=user_id, after_seq=after_seq)

    return [
        MessageResponse(
            id=m.id,
            role=m.role,
            content_type=m.content_type,
            content=m.content,
            task_id=m.task_id,
            status=m.status,
            seq=m.seq,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in messages
    ]
