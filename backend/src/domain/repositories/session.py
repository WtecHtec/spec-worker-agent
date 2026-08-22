"""
会话与消息仓储抽象接口（领域层）
"""
from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.models import Session, Message


class ISessionRepository(ABC):
    @abstractmethod
    async def create(self, user_id: str, title: str = "新会话", agent_config: Optional[dict] = None) -> Session:
        """创建新会话"""
        pass

    @abstractmethod
    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """根据 ID 获取会话"""
        pass

    @abstractmethod
    async def list_by_user(self, user_id: str) -> list[Session]:
        """获取用户的所有会话（按最后活跃时间倒序）"""
        pass


class IMessageRepository(ABC):
    @abstractmethod
    async def create_user_message(self, session_id: str, text: str) -> Message:
        """创建用户消息"""
        pass

    @abstractmethod
    async def create_agent_placeholder(self, session_id: str, task_id: str) -> Message:
        """创建 AGENT 占位消息"""
        pass

    @abstractmethod
    async def list_by_session(self, session_id: str, after_seq: int = 0) -> list[Message]:
        """分页获取会话消息列表（按 seq 递增）"""
        pass

    @abstractmethod
    async def get_by_task_id(self, task_id: str) -> Optional[Message]:
        """根据 task_id 获取关联的 AGENT 消息"""
        pass

    @abstractmethod
    async def update_message(self, message_id: str, status: Optional[str] = None, content: Optional[dict] = None) -> None:
        """更新消息状态与正文内容"""
        pass
