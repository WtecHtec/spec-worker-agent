"""
会话管理应用用例（创建会话、查询会话列表）
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.models import Session
from src.domain.repositories.session import ISessionRepository


class CreateSessionUseCase:
    """创建会话用例"""

    def __init__(self, db: AsyncSession, session_repo: ISessionRepository):
        self.db = db
        self.session_repo = session_repo

    async def execute(self, user_id: str, title: Optional[str] = "新会话", agent_config: Optional[dict] = None) -> Session:
        session = await self.session_repo.create(user_id, title=title or "新会话", agent_config=agent_config)
        await self.db.commit()
        return session


class ListSessionsUseCase:
    """查询用户会话列表用例"""

    def __init__(self, session_repo: ISessionRepository):
        self.session_repo = session_repo

    async def execute(self, user_id: str, limit: int = 20) -> list[Session]:
        return await self.session_repo.list_by_user(user_id, limit=limit)
