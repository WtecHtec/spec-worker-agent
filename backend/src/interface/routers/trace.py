from datetime import datetime, timezone, timedelta
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import TraceRepository
from src.interface.middleware.auth import get_current_user_id

router = APIRouter(tags=["traces"])

TZ_SHANGHAI = timezone(timedelta(hours=8))


def format_dt(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    # 转换为东八区时间并输出标准 ISO 格式（保留微秒精度以供甘特图毫秒对齐）
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_sh = dt.astimezone(TZ_SHANGHAI)
    return dt_sh.isoformat()


class SpanDetailResponse(BaseModel):
    id: str
    trace_id: str
    parent_span_id: Optional[str]
    name: str
    type: str
    status: str
    start_time: str
    end_time: str
    duration_ms: int
    tokens: Optional[dict[str, Any]]
    input_data: Optional[dict[str, Any]]
    output_data: Optional[dict[str, Any]]
    error_message: Optional[str]
    reported_at: str


class TraceDetailResponse(BaseModel):
    id: str
    session_id: str
    message_id: Optional[str]
    run_id: str
    status: str
    total_duration_ms: int
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    model_name: Optional[str]
    tool_calls_count: int
    reported_at: str
    created_at: str
    spans: list[SpanDetailResponse]


@router.get("/traces/{identifier}", response_model=TraceDetailResponse)
async def get_trace_by_identifier(
    identifier: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    按 trace_id / run_id / message_id 获取单条消息回复的完整 Trace 与甘特图 spans 列表
    （委托领域层 TraceRepository 获取业务聚合实体，实施严格的多租户用户隔离）
    """
    trace_repo = TraceRepository(db)
    trace = await trace_repo.get_by_identifier(identifier, user_id=user_id)

    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace with identifier '{identifier}' not found",
        )

    return TraceDetailResponse(
        id=trace.id,
        session_id=trace.session_id,
        message_id=trace.message_id,
        run_id=trace.run_id,
        status=trace.status,
        total_duration_ms=trace.total_duration_ms,
        total_tokens=trace.total_tokens,
        prompt_tokens=trace.prompt_tokens,
        completion_tokens=trace.completion_tokens,
        model_name=trace.model_name,
        tool_calls_count=trace.tool_calls_count,
        reported_at=format_dt(trace.reported_at) or "",
        created_at=format_dt(trace.created_at) or "",
        spans=[
            SpanDetailResponse(
                id=s.id,
                trace_id=s.trace_id,
                parent_span_id=s.parent_span_id,
                name=s.name,
                type=s.type,
                status=s.status,
                start_time=format_dt(s.start_time) or "",
                end_time=format_dt(s.end_time) or "",
                duration_ms=s.duration_ms,
                tokens=s.tokens,
                input_data=s.input_data,
                output_data=s.output_data,
                error_message=s.error_message,
                reported_at=format_dt(s.reported_at) or "",
            )
            for s in trace.spans
        ],
    )


@router.get("/sessions/{session_id}/traces")
async def get_session_traces(
    session_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取指定会话下所有已上报的 Trace 摘要列表（委托 TraceRepository，实施多租户隔离）"""
    trace_repo = TraceRepository(db)
    traces = await trace_repo.list_by_session_id(session_id, user_id=user_id)

    return [
        {
            "id": t.id,
            "session_id": t.session_id,
            "message_id": t.message_id,
            "run_id": t.run_id,
            "status": t.status,
            "total_duration_ms": t.total_duration_ms,
            "total_tokens": t.total_tokens,
            "prompt_tokens": t.prompt_tokens,
            "completion_tokens": t.completion_tokens,
            "model_name": t.model_name,
            "tool_calls_count": t.tool_calls_count,
            "reported_at": format_dt(t.reported_at),
        }
        for t in traces
    ]

