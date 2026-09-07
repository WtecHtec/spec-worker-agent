import os
import uuid
import time
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from src.domain.models.trace import TurnTraceEntity, TraceSpanEntity
from src.domain.repositories.trace_repository import AbstractTraceRepository
from src.infrastructure.db.repositories.trace_repository import SqlAlchemyTraceRepository

logger = logging.getLogger("trace_manager")

# 东八区时区对象
TZ_SHANGHAI = timezone(timedelta(hours=8))


def extract_run_id(config: Optional[dict], fallback_id: Optional[str] = None) -> str:
    """精准提取 LangGraph 官方生命周期 run_id"""
    if isinstance(config, dict):
        # 1. 优先提取 metadata 里的官方 run_id
        meta = config.get("metadata")
        if isinstance(meta, dict) and meta.get("run_id"):
            return str(meta["run_id"])
        # 2. 顶层 run_id
        if config.get("run_id"):
            return str(config["run_id"])
        # 3. configurable 里的 run_id
        cfg = config.get("configurable")
        if isinstance(cfg, dict) and cfg.get("run_id"):
            return str(cfg["run_id"])
    return fallback_id or str(uuid.uuid4())


def extract_thread_id(config: Optional[dict], fallback_id: Optional[str] = None) -> str:
    """提取当前活跃 thread_id / session_id"""
    if isinstance(config, dict):
        cfg = config.get("configurable")
        if isinstance(cfg, dict) and cfg.get("thread_id"):
            return str(cfg["thread_id"])
        meta = config.get("metadata")
        if isinstance(meta, dict) and meta.get("thread_id"):
            return str(meta["thread_id"])
    return fallback_id or "default_session"


class RunTraceBuffer:
    def __init__(self, run_id: str, session_id: str, message_id: Optional[str] = None):
        # 统一使用整张图首个根 run_id 作为全局 trace_id，确保所有 spans 与主表 ID 100% 对齐
        self.trace_id = run_id
        self.run_id = run_id
        self.session_id = session_id
        self.first_message_id = message_id
        self.message_id = message_id
        self.associated_message_ids: list[str] = [message_id] if message_id else []
        self.start_time = datetime.now(TZ_SHANGHAI)
        self.start_timestamp = time.time()
        self.status = "running"
        self.model_name = os.getenv("LLM_MODEL", "deepseek-chat")
        self.spans: list[TraceSpanEntity] = []
        self.total_tokens = {"prompt": 0, "completion": 0, "total": 0}
        self.tool_calls_count = 0

    def add_message_id(self, mid: Optional[str]):
        if mid and mid not in self.associated_message_ids:
            self.associated_message_ids.append(mid)
        if mid and not self.first_message_id:
            self.first_message_id = mid
        if mid and not self.message_id:
            self.message_id = mid

    def add_span(
        self,
        name: str,
        span_type: str,
        start_time: datetime,
        end_time: datetime,
        duration_ms: int,
        status: str = "success",
        tokens: Optional[dict] = None,
        input_data: Optional[dict] = None,
        output_data: Optional[dict] = None,
        error_message: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ) -> TraceSpanEntity:
        span_id = str(uuid.uuid4())
        now = datetime.now(TZ_SHANGHAI)
        span_entity = TraceSpanEntity(
            id=span_id,
            trace_id=self.trace_id,
            parent_span_id=parent_span_id,
            name=name,
            type=span_type,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            tokens=tokens,
            input_data=input_data,
            output_data=output_data,
            error_message=error_message,
            reported_at=now,
            created_at=now,
        )
        self.spans.append(span_entity)

        if tokens:
            self.total_tokens["prompt"] += tokens.get("prompt_tokens", tokens.get("prompt", 0))
            self.total_tokens["completion"] += tokens.get("completion_tokens", tokens.get("completion", 0))
            self.total_tokens["total"] += tokens.get("total_tokens", tokens.get("total", 0))

        if span_type == "tool":
            self.tool_calls_count += 1

        if status == "error":
            self.status = "error"

        return span_entity

    def to_entity(self, final_message_id: Optional[str] = None) -> TurnTraceEntity:
        now = datetime.now(TZ_SHANGHAI)
        total_duration_ms = max(1, int((time.time() - self.start_timestamp) * 1000))
        if final_message_id:
            self.add_message_id(final_message_id)

        # 终态收尾：若无显式 error 则置为 success
        final_status = "error" if self.status == "error" else "success"
        chosen_message_id = self.first_message_id or final_message_id or self.message_id
        return TurnTraceEntity(
            id=self.trace_id,
            session_id=self.session_id,
            message_id=chosen_message_id,
            run_id=self.run_id,
            status=final_status,
            total_duration_ms=total_duration_ms,
            total_tokens=self.total_tokens["total"],
            prompt_tokens=self.total_tokens["prompt"],
            completion_tokens=self.total_tokens["completion"],
            model_name=self.model_name,
            tool_calls_count=self.tool_calls_count,
            reported_at=now,
            created_at=now,
            spans=list(self.spans),
        )


class TraceManager:
    """全局单例 Trace 管理器，遵循 DDD 规范，通过 Repository 实时增量持久化至数据库"""

    def __init__(self, repository: Optional[AbstractTraceRepository] = None):
        self._buffers: dict[str, RunTraceBuffer] = {}
        self._repository: AbstractTraceRepository = repository or SqlAlchemyTraceRepository()

    def get_or_create_buffer(
        self, run_id: str, session_id: str, message_id: Optional[str] = None
    ) -> RunTraceBuffer:
        is_new = run_id not in self._buffers
        if is_new:
            self._buffers[run_id] = RunTraceBuffer(run_id, session_id, message_id)
            # 实时增量落库：根任务首节点启动即建档
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._repository.init_trace(
                        trace_id=run_id,
                        session_id=session_id,
                        run_id=run_id,
                        message_id=message_id,
                    )
                )
            except RuntimeError:
                pass
        return self._buffers[run_id]

    def record_span(
        self,
        run_id: str,
        session_id: str,
        name: str,
        span_type: str,
        start_time: datetime,
        end_time: datetime,
        duration_ms: int,
        status: str = "success",
        tokens: Optional[dict] = None,
        input_data: Optional[dict] = None,
        output_data: Optional[dict] = None,
        error_message: Optional[str] = None,
        message_id: Optional[str] = None,
        parent_span_id: Optional[str] = None,
    ):
        buf = self.get_or_create_buffer(run_id, session_id, message_id)
        if message_id:
            buf.add_message_id(message_id)
        span_entity = buf.add_span(
            name=name,
            span_type=span_type,
            start_time=start_time,
            end_time=end_time,
            duration_ms=duration_ms,
            status=status,
            tokens=tokens,
            input_data=input_data,
            output_data=output_data,
            error_message=error_message,
            parent_span_id=parent_span_id,
        )

        # 实时增量落库：单步执行完毕即刻追加 Span
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._repository.append_span(
                    span_entity=span_entity,
                    tokens_delta=tokens,
                    is_tool=(span_type == "tool"),
                    duration_ms=duration_ms,
                )
            )
        except RuntimeError:
            pass

    async def finalize_and_flush(self, run_id: str, final_message_id: Optional[str] = None):
        """一次 Run 结束时，保存完整终态数据并通过 Repository ORM 封箱"""
        buf = self._buffers.pop(run_id, None)
        if not buf:
            return

        trace_entity = buf.to_entity(final_message_id)
        try:
            await self._repository.save_trace(trace_entity)
            logger.info(
                "[trace_manager] Successfully flushed trace via ORM: trace_id=%s, run_id=%s, spans=%d, tokens=%d",
                trace_entity.id,
                trace_entity.run_id,
                len(trace_entity.spans),
                trace_entity.total_tokens,
            )
        except Exception as e:
            logger.error("[trace_manager] Failed to flush trace via Repository: %s", str(e))


trace_manager = TraceManager()

