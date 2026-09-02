from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import SessionRepository
from src.interface.middleware.auth import get_current_user_id
from src.application.session.use_cases import CreateSessionUseCase, ListSessionsUseCase, DeleteSessionUseCase
from fastapi import HTTPException


router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    id: str
    title: str | None
    status: str
    message_count: int
    created_at: str


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """创建会话端点（委托 CreateSessionUseCase）"""
    use_case = CreateSessionUseCase(db=db, session_repo=SessionRepository(db))
    session = await use_case.execute(user_id=user_id, title=body.title)
    return SessionResponse(
        id=session.id,
        title=session.title,
        status=session.status,
        message_count=session.message_count,
        created_at=session.created_at.isoformat() if session.created_at else "",
    )


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取用户会话列表（委托 ListSessionsUseCase）"""
    use_case = ListSessionsUseCase(session_repo=SessionRepository(db))
    sessions = await use_case.execute(user_id=user_id)
    return [
        SessionResponse(
            id=s.id,
            title=s.title,
            status=s.status,
            message_count=s.message_count,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in sessions
    ]


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除会话端点（委托 DeleteSessionUseCase）"""
    use_case = DeleteSessionUseCase(db=db, session_repo=SessionRepository(db))
    deleted = await use_case.execute(session_id=session_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="会话不存在或无权删除")
    return {"message": "session_deleted", "id": session_id}


