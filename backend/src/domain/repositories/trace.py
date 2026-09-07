"""
Trace 链路追踪与执行历程仓储抽象接口（领域层）
"""
from abc import ABC, abstractmethod
from typing import Optional
from src.domain.entities.models import MessageTrace


class ITraceRepository(ABC):
    @abstractmethod
    async def get_by_identifier(
        self, identifier: str, user_id: Optional[str] = None
    ) -> Optional[MessageTrace]:
        """
        根据 trace_id / run_id / message_id / session_id 获取单个 Trace 聚合及其 Spans 列表
        实现内部需处理标识符格式兼容、关联加载及时序排序，并在提供 user_id 时进行严格租户鉴权
        """
        pass

    @abstractmethod
    async def list_by_session_id(
        self, session_id: str, user_id: Optional[str] = None
    ) -> list[MessageTrace]:
        """
        获取指定会话下的所有已上报 Trace 摘要列表（按上报时间升序）
        并在提供 user_id 时进行严格租户鉴权
        """
        pass
