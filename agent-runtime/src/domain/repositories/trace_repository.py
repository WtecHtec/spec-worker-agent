from abc import ABC, abstractmethod
from typing import Optional
from src.domain.models.trace import TurnTraceEntity, TraceSpanEntity


class AbstractTraceRepository(ABC):
    """领域仓储接口：Trace 存储与持久化契约"""

    @abstractmethod
    async def save_trace(self, trace_entity: TurnTraceEntity) -> None:
        """持久化完整的 TurnTrace 及其包含的全部 TraceSpan"""
        pass

    @abstractmethod
    async def init_trace(
        self, trace_id: str, session_id: str, run_id: str, message_id: Optional[str] = None
    ) -> None:
        """图启动时立即初始化 Trace 主表记录（若已存在则忽略），状态为 running"""
        pass

    @abstractmethod
    async def append_span(
        self,
        span_entity: TraceSpanEntity,
        tokens_delta: Optional[dict] = None,
        is_tool: bool = False,
        duration_ms: int = 0,
    ) -> None:
        """增量写入单条 Span，并原子更新主表的 tokens / tool_calls_count / 累计耗时"""
        pass

    @abstractmethod
    async def finish_trace(
        self, trace_id: str, status: str = "success", final_message_id: Optional[str] = None
    ) -> None:
        """图运行终态更新：置状态为 success/error 并更新最终耗时与消息 ID"""
        pass

