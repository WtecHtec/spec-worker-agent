"""
人机协同 (HITL) 仓储抽象接口（领域层）
"""
from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.models import HitlRequest


class IHitlRepository(ABC):
    @abstractmethod
    async def get_pending_by_task(self, task_id: str) -> Optional[HitlRequest]:
        """获取指定任务当前待处理的 PENDING 审批请求"""
        pass

    @abstractmethod
    async def get_by_id(self, hitl_id: str) -> Optional[HitlRequest]:
        """根据 ID 获取审批请求"""
        pass

    @abstractmethod
    async def list_expired_requests(self) -> list[HitlRequest]:
        """查询所有超时未响应的 PENDING 审批请求"""
        pass

    @abstractmethod
    async def mark_expired(self, hitl_id: str) -> None:
        """标记审批为 EXPIRED 超时"""
        pass

    @abstractmethod
    async def resolve(self, hitl_id: str, decision: str, user_input: Optional[dict] = None) -> None:
        """记录用户审批决策并更新状态为 RESOLVED"""
        pass
