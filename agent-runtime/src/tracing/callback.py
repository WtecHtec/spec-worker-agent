import time
import logging
from datetime import datetime
from typing import Any, Optional, Union
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from src.tracing.trace_manager import trace_manager, TZ_SHANGHAI

logger = logging.getLogger("turn_trace_callback")


class TurnTraceCallbackHandler(AsyncCallbackHandler):
    """
    LangGraph / LangChain 标准异步回调处理器：
    用于图和节点的执行日志统一拦截、耗时测量、Token 汇总与持久化入库。
    遵循 graph.invoke(input, config={"callbacks": [handler]}) 规范。
    """

    def __init__(self, run_id: Optional[str] = None, session_id: Optional[str] = None):
        super().__init__()
        self._custom_run_id = run_id
        self._custom_session_id = session_id
        # 记录父子依赖有向拓扑：child_run_id -> parent_run_id，杜绝单一跨请求标量，100% 并发安全
        self._parents: dict[str, Optional[str]] = {}
        self._start_times: dict[str, tuple[datetime, float]] = {}
        self._node_inputs: dict[str, Any] = {}
        self._node_names: dict[str, str] = {}

    def _get_root_run_id(self, current_id: str) -> str:
        if self._custom_run_id:
            return self._custom_run_id
        curr = current_id
        visited = set()
        # 沿拓扑树向上纯函数回溯至祖先根节点（parent_run_id 为 None 或不再有 parent 的节点）
        while curr in self._parents and self._parents[curr] and curr not in visited:
            visited.add(curr)
            curr = str(self._parents[curr])
        return curr

    def _resolve_run_and_session(
        self,
        current_run_id: Union[UUID, str],
        parent_run_id: Optional[Union[UUID, str]],
        metadata: Optional[dict[str, Any]],
    ) -> tuple[str, str]:
        s_id = str(current_run_id)
        if parent_run_id:
            self._parents[s_id] = str(parent_run_id)
        elif s_id not in self._parents:
            self._parents[s_id] = None  # 标记为本调用链路的根节点

        # 从当前节点动态回溯至当前请求真实的 root_run_id，绝不与其他用户/请求产生任何交叉
        top_run_id = self._custom_run_id or self._get_root_run_id(s_id)
        meta = metadata or {}
        session_id = str(
            self._custom_session_id
            or meta.get("thread_id")
            or meta.get("session_id")
            or "default_session"
        )
        return top_run_id, session_id

    def _cleanup_tree(self, root_id: str) -> None:
        """整条链执行完毕后垃圾回收，杜绝多用户长期运行下的内存泄漏"""
        to_del = {k for k, v in self._parents.items() if v == root_id or k == root_id}
        for k in to_del:
            self._parents.pop(k, None)
            self._start_times.pop(k, None)
            self._node_inputs.pop(k, None)
            self._node_names.pop(k, None)

    async def on_chain_start(
        self,
        serialized: Optional[dict[str, Any]],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """当一个节点或者整张图开始执行时触发"""
        s_id = str(run_id)
        self._start_times[s_id] = (datetime.now(TZ_SHANGHAI), time.time())
        self._node_inputs[s_id] = inputs
        node_name = (metadata or {}).get("langgraph_node")
        if node_name:
            self._node_names[s_id] = node_name

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)
        trace_manager.get_or_create_buffer(run_id=top_run_id, session_id=session_id)

    async def on_chain_end(
        self,
        outputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """当节点或整张图执行完成时触发"""
        s_id = str(run_id)
        start_info = self._start_times.pop(s_id, None)
        self._node_inputs.pop(s_id, None)
        node_name = self._node_names.pop(s_id, None) or (metadata or {}).get("langgraph_node")

        start_dt, start_ts = start_info if start_info else (datetime.now(TZ_SHANGHAI), time.time())
        end_dt = datetime.now(TZ_SHANGHAI)
        duration_ms = max(1, int((time.time() - start_ts) * 1000))

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)

        # 1. 如果是子节点（例如 context_compressor, agent_node, tools_node）
        if node_name:
            # 过滤 LangChain 内部 RunnableBinding 产生的重复/幽灵 <=2ms 碎片 Span（无业务 output_data）
            if node_name == "agent_node" and duration_ms <= 2 and not outputs:
                logger.debug(
                    "[callback] Filtered out duplicate inner RunnableBinding span for agent_node: duration=%dms",
                    duration_ms,
                )
                return

            output_data: dict[str, Any] = {}
            span_name = node_name
            span_type = "node"

            if isinstance(outputs, dict):
                # 针对 context_compressor：区分是否真正触发了记忆压缩
                if node_name == "context_compressor":
                    if "summary" in outputs:
                        output_data["summary"] = outputs["summary"]
                        output_data["action"] = "COMPRESSED"
                        span_name = "context_compressor (提炼中期记忆)"
                        span_type = "memory"
                    else:
                        output_data["action"] = "PASS_THROUGH"
                        span_name = "context_compressor (未超阈值跳过)"
                    if "active_cut_index" in outputs:
                        output_data["active_cut_index"] = outputs["active_cut_index"]

                # 针对 tools_node：提取真实调用的工具名称与执行摘要
                elif node_name == "tools_node":
                    span_type = "tool"
                    tool_names: list[str] = []
                    previews: list[str] = []
                    if "messages" in outputs and isinstance(outputs["messages"], list):
                        output_data["messages_count"] = len(outputs["messages"])
                        for m in outputs["messages"]:
                            t_name = getattr(m, "name", None)
                            if t_name and t_name not in tool_names:
                                tool_names.append(t_name)
                            c = getattr(m, "content", None)
                            if c:
                                previews.append(str(c)[:200])
                    if tool_names:
                        span_name = f"tool: {', '.join(tool_names)}"
                        output_data["tools"] = tool_names
                        if previews:
                            output_data["result_preview"] = "\n".join(previews)
                    else:
                        span_name = "tool_execution"

                # 针对 agent_node 的 messages 输出
                elif node_name == "agent_node":
                    if "messages" in outputs and isinstance(outputs["messages"], list):
                        output_data["messages_count"] = len(outputs["messages"])
                        last_m = outputs["messages"][-1] if outputs["messages"] else None
                        if last_m:
                            tool_calls = getattr(last_m, "tool_calls", None)
                            if tool_calls:
                                output_data["decision"] = "TOOL_CALL"
                                output_data["tool_calls"] = [tc.get("name") for tc in tool_calls]
                            elif getattr(last_m, "content", None):
                                output_data["decision"] = "FINAL_ANSWER"
                                output_data["content_preview"] = str(last_m.content)[:200]

            trace_manager.record_span(
                run_id=top_run_id,
                session_id=session_id,
                name=span_name,
                span_type=span_type,
                start_time=start_dt,
                end_time=end_dt,
                duration_ms=duration_ms,
                status="success",
                output_data=output_data if output_data else None,
                parent_span_id=str(parent_run_id) if parent_run_id else None,
            )
        elif parent_run_id is None:
            # 2. 如果是整张图执行完毕（Parent 根图结束）
            final_msg_id = None
            if isinstance(outputs, dict) and "messages" in outputs and isinstance(outputs["messages"], list):
                buf = trace_manager.get_or_create_buffer(run_id=top_run_id, session_id=session_id)
                for m in outputs["messages"]:
                    mid = getattr(m, "id", None)
                    if mid:
                        buf.add_message_id(str(mid))
                for m in reversed(outputs["messages"]):
                    mid = getattr(m, "id", None)
                    if mid:
                        final_msg_id = str(mid)
                        break
            await trace_manager.finalize_and_flush(run_id=top_run_id, final_message_id=final_msg_id)
            self._cleanup_tree(top_run_id)

    async def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """节点或图异常"""
        s_id = str(run_id)
        start_info = self._start_times.pop(s_id, None)
        self._node_inputs.pop(s_id, None)
        node_name = self._node_names.pop(s_id, None) or (metadata or {}).get("langgraph_node", "graph")

        start_dt, start_ts = start_info if start_info else (datetime.now(TZ_SHANGHAI), time.time())
        duration_ms = max(1, int((time.time() - start_ts) * 1000))

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)

        trace_manager.record_span(
            run_id=top_run_id,
            session_id=session_id,
            name=node_name,
            span_type="node",
            start_time=start_dt,
            end_time=datetime.now(TZ_SHANGHAI),
            duration_ms=duration_ms,
            status="error",
            error_message=str(error),
            parent_span_id=str(parent_run_id) if parent_run_id else None,
        )
        if parent_run_id is None:
            await trace_manager.finalize_and_flush(run_id=top_run_id)
            self._cleanup_tree(top_run_id)

    async def on_chat_model_start(
        self,
        serialized: Optional[dict[str, Any]],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 推理调用开始"""
        s_id = str(run_id)
        self._start_times[s_id] = (datetime.now(TZ_SHANGHAI), time.time())
        if parent_run_id:
            self._parents[s_id] = str(parent_run_id)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 推理调用结束，提取 Token 消耗与决策"""
        s_id = str(run_id)
        start_info = self._start_times.pop(s_id, None)
        start_dt, start_ts = start_info if start_info else (datetime.now(TZ_SHANGHAI), time.time())
        duration_ms = max(1, int((time.time() - start_ts) * 1000))

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)

        # 提取 tokens
        tokens = None
        if response.llm_output and "token_usage" in response.llm_output:
            tokens = response.llm_output["token_usage"]

        # 提取生成的消息内容和 tool_calls
        output_data: dict[str, Any] = {}
        message_id = None
        has_tool_calls = False
        tool_names = []

        if response.generations and response.generations[0]:
            first_gen = response.generations[0][0]
            gen_msg = getattr(first_gen, "message", None)
            if gen_msg:
                message_id = getattr(gen_msg, "id", None)
                if getattr(gen_msg, "tool_calls", None):
                    has_tool_calls = True
                    tool_names = [tc.get("name") for tc in gen_msg.tool_calls]
                if getattr(gen_msg, "content", None):
                    output_data["content_preview"] = str(gen_msg.content)[:200]
                if not tokens and getattr(gen_msg, "usage_metadata", None):
                    tokens = gen_msg.usage_metadata

        if message_id:
            output_data["message_id"] = str(message_id)
            buf = trace_manager.get_or_create_buffer(run_id=top_run_id, session_id=session_id)
            buf.add_message_id(str(message_id))

        output_data["decision"] = "TOOL_CALL" if has_tool_calls else "FINAL_ANSWER"
        if tool_names:
            output_data["tool_calls"] = tool_names

        span_name = f"llm_call ({'调用工具' if has_tool_calls else '输出回答'})"

        trace_manager.record_span(
            run_id=top_run_id,
            session_id=session_id,
            name=span_name,
            span_type="llm",
            start_time=start_dt,
            end_time=datetime.now(TZ_SHANGHAI),
            duration_ms=duration_ms,
            status="success",
            tokens=tokens,
            output_data=output_data,
            message_id=message_id,
            parent_span_id=str(parent_run_id) if parent_run_id else None,
        )

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用报错"""
        s_id = str(run_id)
        start_info = self._start_times.pop(s_id, None)
        start_dt, start_ts = start_info if start_info else (datetime.now(TZ_SHANGHAI), time.time())
        duration_ms = max(1, int((time.time() - start_ts) * 1000))

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)
        trace_manager.record_span(
            run_id=top_run_id,
            session_id=session_id,
            name="llm_call",
            span_type="llm",
            start_time=start_dt,
            end_time=datetime.now(TZ_SHANGHAI),
            duration_ms=duration_ms,
            status="error",
            error_message=str(error),
            parent_span_id=str(parent_run_id) if parent_run_id else None,
        )

    async def on_tool_start(
        self,
        serialized: Optional[dict[str, Any]],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        inputs: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """工具开始执行"""
        s_id = str(run_id)
        self._start_times[s_id] = (datetime.now(TZ_SHANGHAI), time.time())
        self._node_inputs[s_id] = inputs or input_str
        t_name = (
            (serialized or {}).get("name")
            or kwargs.get("name")
            or (metadata or {}).get("tool_name")
            or (metadata or {}).get("langgraph_node")
            or "tool"
        )
        self._node_names[s_id] = t_name
        if parent_run_id:
            self._parents[s_id] = str(parent_run_id)

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """工具执行完毕"""
        s_id = str(run_id)
        start_info = self._start_times.pop(s_id, None)
        input_data = self._node_inputs.pop(s_id, None)
        saved_tool_name = self._node_names.pop(s_id, None)
        start_dt, start_ts = start_info if start_info else (datetime.now(TZ_SHANGHAI), time.time())
        duration_ms = max(1, int((time.time() - start_ts) * 1000))

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)
        tool_name = (
            saved_tool_name
            or (metadata or {}).get("tool_name")
            or kwargs.get("name")
            or "tool"
        )

        out_preview = str(output)[:300] if output is not None else ""
        trace_manager.record_span(
            run_id=top_run_id,
            session_id=session_id,
            name=f"tool: {tool_name}",
            span_type="tool",
            start_time=start_dt,
            end_time=datetime.now(TZ_SHANGHAI),
            duration_ms=duration_ms,
            status="success",
            input_data={"arguments": input_data} if input_data else None,
            output_data={"result_preview": out_preview},
            parent_span_id=str(parent_run_id) if parent_run_id else None,
        )

    async def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        """工具执行异常"""
        s_id = str(run_id)
        start_info = self._start_times.pop(s_id, None)
        input_data = self._node_inputs.pop(s_id, None)
        saved_tool_name = self._node_names.pop(s_id, None)
        start_dt, start_ts = start_info if start_info else (datetime.now(TZ_SHANGHAI), time.time())
        duration_ms = max(1, int((time.time() - start_ts) * 1000))

        top_run_id, session_id = self._resolve_run_and_session(run_id, parent_run_id, metadata)
        tool_name = (
            saved_tool_name
            or (metadata or {}).get("tool_name")
            or kwargs.get("name")
            or "tool"
        )

        trace_manager.record_span(
            run_id=top_run_id,
            session_id=session_id,
            name=f"tool: {tool_name}",
            span_type="tool",
            start_time=start_dt,
            end_time=datetime.now(TZ_SHANGHAI),
            duration_ms=duration_ms,
            status="error",
            input_data={"arguments": input_data} if input_data else None,
            error_message=str(error),
            parent_span_id=str(parent_run_id) if parent_run_id else None,
        )
