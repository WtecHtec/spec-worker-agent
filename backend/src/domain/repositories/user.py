"""
用户仓储抽象接口（领域层）
"""
from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.models import User


class IUserRepository(ABC):
    @abstractmethod
    async def create(self, email: str, password_hash: str, display_name: Optional[str] = None) -> User:
        """创建新用户"""
        pass

    @abstractmethod
    async def get_by_id(self, user_id: str) -> Optional[User]:
        """根据 ID 查询用户"""
        pass

    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[User]:
        """根据邮箱查询用户"""
        pass
