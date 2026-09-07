from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class TraceSpanEntity:
    """领域实体：甘特图单步 Span"""
    id: str
    trace_id: str
    name: str
    type: str  # "node" | "llm" | "tool"
    status: str  # "success" | "error"
    start_time: datetime
    end_time: datetime
    duration_ms: int
    reported_at: datetime
    created_at: datetime
    parent_span_id: Optional[str] = None
    tokens: Optional[dict[str, Any]] = None
    input_data: Optional[dict[str, Any]] = None
    output_data: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


@dataclass
class TurnTraceEntity:
    """领域实体：一次完整对话轮次 (Turn/Run) 的 Trace 聚合根"""
    id: str
    session_id: str
    run_id: str
    status: str
    total_duration_ms: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    model_name: str
    tool_calls_count: int
    reported_at: datetime
    created_at: datetime
    message_id: Optional[str] = None
    spans: list[TraceSpanEntity] = field(default_factory=list)
