import os
import logging
from typing import Optional
from sqlalchemy import select
from src.domain.models.trace import TurnTraceEntity, TraceSpanEntity
from src.domain.repositories.trace_repository import AbstractTraceRepository
from src.infrastructure.db.database import AsyncSessionLocal
from src.infrastructure.db.models import MessageTraceModel, TraceSpanModel

logger = logging.getLogger("trace_repository")


class SqlAlchemyTraceRepository(AbstractTraceRepository):
    """基于 SQLAlchemy ORM 的 Trace 仓储实现，支持分阶段实时增量入库"""

    async def init_trace(
        self, trace_id: str, session_id: str, run_id: str, message_id: Optional[str] = None
    ) -> None:
        """整张图启动时即刻建档落库，置初始状态为 running"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(MessageTraceModel).where(MessageTraceModel.id == trace_id)
                res = await session.execute(stmt)
                trace_model = res.scalar_one_or_none()
                if not trace_model:
                    trace_model = MessageTraceModel(
                        id=trace_id,
                        session_id=session_id,
                        message_id=message_id,
                        run_id=run_id,
                        status="running",
                        total_duration_ms=0,
                        total_tokens=0,
                        prompt_tokens=0,
                        completion_tokens=0,
                        model_name=os.getenv("LLM_MODEL", "deepseek-chat"),
                        tool_calls_count=0,
                    )
                    session.add(trace_model)
                    await session.commit()
                    logger.debug("[trace_repo] Initialized trace record: id=%s, status=running", trace_id)
            except Exception as e:
                await session.rollback()
                logger.error("[trace_repo] Failed to init trace: %s", str(e))

    async def append_span(
        self,
        span_entity: TraceSpanEntity,
        tokens_delta: Optional[dict] = None,
        is_tool: bool = False,
        duration_ms: int = 0,
    ) -> None:
        """单步完成时实时追加 Span，并原子累加消耗"""
        async with AsyncSessionLocal() as session:
            try:
                # 1. 插入当前 Span
                span_model = TraceSpanModel(
                    id=span_entity.id,
                    trace_id=span_entity.trace_id,
                    parent_span_id=span_entity.parent_span_id,
                    name=span_entity.name,
                    type=span_entity.type,
                    status=span_entity.status,
                    start_time=span_entity.start_time,
                    end_time=span_entity.end_time,
                    duration_ms=span_entity.duration_ms,
                    tokens=span_entity.tokens,
                    input_data=span_entity.input_data,
                    output_data=span_entity.output_data,
                    error_message=span_entity.error_message,
                    reported_at=span_entity.reported_at,
                    created_at=span_entity.created_at,
                )
                session.add(span_model)

                # 2. 同步更新母表统计与首个有效 message_id
                stmt = select(MessageTraceModel).where(MessageTraceModel.id == span_entity.trace_id)
                res = await session.execute(stmt)
                trace = res.scalar_one_or_none()
                if trace:
                    if tokens_delta:
                        p = tokens_delta.get("prompt_tokens", tokens_delta.get("prompt", 0)) or 0
                        c = tokens_delta.get("completion_tokens", tokens_delta.get("completion", 0)) or 0
                        t = tokens_delta.get("total_tokens", tokens_delta.get("total", 0)) or (p + c)
                        trace.prompt_tokens += p
                        trace.completion_tokens += c
                        trace.total_tokens += t
                    if is_tool:
                        trace.tool_calls_count += 1
                    if duration_ms > 0:
                        trace.total_duration_ms += duration_ms

                    # 提取 span 中产出的 message_id，第一时间挂载到母表
                    mid = None
                    if span_entity.output_data and isinstance(span_entity.output_data, dict):
                        mid = span_entity.output_data.get("message_id")
                    if not mid and span_entity.input_data and isinstance(span_entity.input_data, dict):
                        mid = span_entity.input_data.get("message_id")
                    if mid and not trace.message_id:
                        trace.message_id = str(mid)

                await session.commit()
                logger.debug("[trace_repo] Appended span %s to trace %s", span_entity.name, span_entity.trace_id)
            except Exception as e:
                await session.rollback()
                logger.error("[trace_repo] Failed to append span %s: %s", span_entity.id, str(e))

    async def finish_trace(
        self, trace_id: str, status: str = "success", final_message_id: Optional[str] = None
    ) -> None:
        """终态更新：置状态并更新 message_id"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(MessageTraceModel).where(MessageTraceModel.id == trace_id)
                res = await session.execute(stmt)
                trace = res.scalar_one_or_none()
                if trace:
                    trace.status = status
                    if final_message_id and not trace.message_id:
                        trace.message_id = final_message_id
                    await session.commit()
                    logger.debug("[trace_repo] Finished trace %s with status=%s", trace_id, status)
            except Exception as e:
                await session.rollback()
                logger.error("[trace_repo] Failed to finish trace %s: %s", trace_id, str(e))

    async def save_trace(self, trace_entity: TurnTraceEntity) -> None:
        """兜底完整 Upsert"""
        async with AsyncSessionLocal() as session:
            try:
                stmt = select(MessageTraceModel).where(MessageTraceModel.id == trace_entity.id)
                res = await session.execute(stmt)
                trace_model = res.scalar_one_or_none()

                if not trace_model:
                    trace_model = MessageTraceModel(
                        id=trace_entity.id,
                        session_id=trace_entity.session_id,
                        message_id=trace_entity.message_id,
                        run_id=trace_entity.run_id,
                        status=trace_entity.status,
                        total_duration_ms=trace_entity.total_duration_ms,
                        total_tokens=trace_entity.total_tokens,
                        prompt_tokens=trace_entity.prompt_tokens,
                        completion_tokens=trace_entity.completion_tokens,
                        model_name=trace_entity.model_name,
                        tool_calls_count=trace_entity.tool_calls_count,
                        reported_at=trace_entity.reported_at,
                        created_at=trace_entity.created_at,
                    )
                    session.add(trace_model)
                else:
                    trace_model.status = trace_entity.status
                    trace_model.total_duration_ms = max(trace_model.total_duration_ms, trace_entity.total_duration_ms)
                    trace_model.total_tokens = max(trace_model.total_tokens, trace_entity.total_tokens)
                    trace_model.prompt_tokens = max(trace_model.prompt_tokens, trace_entity.prompt_tokens)
                    trace_model.completion_tokens = max(trace_model.completion_tokens, trace_entity.completion_tokens)
                    trace_model.tool_calls_count = max(trace_model.tool_calls_count, trace_entity.tool_calls_count)
                    trace_model.reported_at = trace_entity.reported_at
                    if trace_entity.message_id and not trace_model.message_id:
                        trace_model.message_id = trace_entity.message_id

                # 插入尚未存在的 Spans
                existing_spans_res = await session.execute(
                    select(TraceSpanModel.id).where(TraceSpanModel.trace_id == trace_entity.id)
                )
                existing_span_ids = set(existing_spans_res.scalars().all())

                for span_entity in trace_entity.spans:
                    if span_entity.id not in existing_span_ids:
                        span_model = TraceSpanModel(
                            id=span_entity.id,
                            trace_id=trace_entity.id,
                            parent_span_id=span_entity.parent_span_id,
                            name=span_entity.name,
                            type=span_entity.type,
                            status=span_entity.status,
                            start_time=span_entity.start_time,
                            end_time=span_entity.end_time,
                            duration_ms=span_entity.duration_ms,
                            tokens=span_entity.tokens,
                            input_data=span_entity.input_data,
                            output_data=span_entity.output_data,
                            error_message=span_entity.error_message,
                            reported_at=span_entity.reported_at,
                            created_at=span_entity.created_at,
                        )
                        session.add(span_model)

                await session.commit()
                logger.info(
                    "[SqlAlchemyTraceRepository] Successfully saved trace via ORM: id=%s, spans=%d",
                    trace_entity.id,
                    len(trace_entity.spans),
                )
            except Exception as e:
                await session.rollback()
                logger.error("[SqlAlchemyTraceRepository] Failed to save trace via ORM: %s", str(e))
                raise

