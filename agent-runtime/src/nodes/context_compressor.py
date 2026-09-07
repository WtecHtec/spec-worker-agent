import os
import json
import logging
from typing import Any
from dotenv import load_dotenv
from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
    SystemMessage,
)
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.state.state import AgentState
from src.prompts.memory import (
    MEMORY_COMPRESSION_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    build_memory_compression_user_prompt,
)


load_dotenv()
logger = logging.getLogger("context_compressor")

# 1. 尝试导入 tiktoken 进行精确 token 计数，降级时使用字符估算法
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
except Exception:
    _enc = None


def estimate_messages_tokens(messages: list[BaseMessage]) -> int:
    """
    估算消息列表消耗的 Token 总量：
    - 若 tiktoken 可用：计算 content 与 tool_calls 序列化字符串的真实 token 数；
    - 若不可用：按中文字符 1.5 字符/token、英文 4 字符/token + 15% 安全余量进行快速估算。
    """
    if not messages:
        return 0

    total_tokens = 0
    for msg in messages:
        raw_text = ""
        if isinstance(msg.content, str):
            raw_text = msg.content
        elif isinstance(msg.content, list):
            raw_text = json.dumps(msg.content, ensure_ascii=False)

        # 累计 tool_calls 序列化内容
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            raw_text += json.dumps(tool_calls, ensure_ascii=False)

        if _enc is not None:
            try:
                total_tokens += len(_enc.encode(raw_text)) + 4  # 每条消息的基础元数据开销
                continue
            except Exception:
                pass

        # 降级估算：中文等非 ascii 按 0.7 token/char，英文按 0.3 token/char
        non_ascii_count = sum(1 for ch in raw_text if ord(ch) > 127)
        ascii_count = len(raw_text) - non_ascii_count
        msg_token_est = int(non_ascii_count * 0.7 + ascii_count * 0.3) + 4
        total_tokens += msg_token_est

    return total_tokens


def find_safe_aimessage_cut_index(
    messages: list[BaseMessage],
    keep_recent: int = 6,
) -> int | None:
    """
    动态语义安全截断算法（Boundary Alignment）：
    寻找截断点 cut_index，满足：
    1. 保留近期至少 keep_recent 条消息作为当前活跃工作上下文；
    2. 被归档/压缩切片 `messages[0 : cut_index + 1]` 的最后一条必须是【无未决 tool_calls 的 AIMessage】；
    3. 严禁切断在 AIMessage(tool_calls) 与 ToolMessage 之间，杜绝 API 400 配对报错；
    4. 若在合法窗口内未发现符合条件的 AIMessage，返回 None（安全跳过截断）。

    返回：
        cut_index (int | None): 压缩切片的最后一条消息索引（包含此条）。
    """
    n = len(messages)
    if n <= keep_recent:
        return None

    # 从后往前寻找符合条件的 AIMessage 候选（从可截取的最大边界向左回溯）
    max_cut_candidate = n - keep_recent - 1

    for i in range(max_cut_candidate, -1, -1):
        msg = messages[i]
        is_ai = isinstance(msg, AIMessage) or getattr(msg, "type", "") in ("ai", "assistant")
        if not is_ai:
            continue

        # 关键校验：若此条 AIMessage 发起了 tool_calls，则属于中间动作，不能作为切片终点
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls and len(tool_calls) > 0:
            continue

        # 成功找到以纯文本/阶段性结论结尾的 AIMessage
        return i

    return None


def format_messages_for_summary(messages: list[BaseMessage]) -> str:
    """将待归档的消息切片格式化为便于 LLM 提取摘要的文本记录"""
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage) or getattr(msg, "type", "") in ("human", "user"):
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False)
            lines.append(f"【用户提问】: {content}")
        elif isinstance(msg, AIMessage) or getattr(msg, "type", "") in ("ai", "assistant"):
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False)
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                tc_names = [tc.get("name", "tool") for tc in tool_calls if isinstance(tc, dict)]
                lines.append(f"【Agent 决策】: 调用工具 {tc_names} | 说明: {content}")
            else:
                lines.append(f"【Agent 答复】: {content}")
        elif isinstance(msg, ToolMessage) or getattr(msg, "type", "") in ("tool",):
            tool_name = getattr(msg, "name", "tool")
            content = msg.content if isinstance(msg.content, str) else json.dumps(msg.content, ensure_ascii=False)
            # 工具结果若过长，做轻量提纯
            if len(content) > 500:
                content = content[:500] + "...(数据已折叠)"
            lines.append(f"【工具执行产物 ({tool_name})】: {content}")
    return "\n".join(lines)






def _get_summary_llm() -> ChatOpenAI:
    """获取专用于记忆压缩的 LLM 实例（优先读取 SUMMARY_LLM_MODEL，兼容主模型配置）"""
    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("LLM_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.deepseek.com"
    )
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("LLM_KEY")
        or os.getenv("OPENAI_API_KEY")
        or "EMPTY"
    )
    model_name = (
        os.getenv("SUMMARY_LLM_MODEL")
        or os.getenv("LLM_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "deepseek-chat"
    )

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        streaming=False,
        temperature=0.2,
    )


def quick_char_pass_through_filter(messages: list[BaseMessage], token_threshold: int) -> bool:
    """
    极轻量 O(N) 字符粗筛短路：
    1 token 至少对应 1 个字符（中文通常 1.5~2 字符/token，英文 3~4 字符/token）。
    若全量文本字符总数直接小于 token_threshold，则其 token 数绝无可能超标。
    返回 True 表示确定未超标（可极速短路放行），False 表示可能超标（需进入精细计算）。
    """
    total_len = 0
    for m in messages:
        if isinstance(m.content, str):
            total_len += len(m.content)
        elif isinstance(m.content, list):
            total_len += sum(len(str(item)) for item in m.content)
        if total_len >= token_threshold:
            return False
    return total_len < token_threshold


async def context_compressor_node(
    state: AgentState,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """
    LangGraph 中期记忆压缩节点（形态 A 显式独立编排）：
    1. 极速字符粗筛短路 + 计算 messages 总 Token，与环境变量阈值对比；
    2. 未超阈值直接 Pass-through 返回 {}；
    3. 超出阈值时，运行动态语义边界对齐算法定位合法截断点（最后一条必须为最终 AIMessage）；
    4. 增量提炼并更新 summary，调整 active_cut_index 游标（带防逆流与幂等保护）；
    5. 【关键保障】：绝不修改或删除 state["messages"]，保证 PostgreSQL 通道与前端渲染 100% 完整。
    """
    messages = list(state.get("messages", []))
    if not messages:
        return {}

    # 读取配置参数
    token_threshold = int(os.getenv("MEMORY_COMPRESSION_TOKEN_THRESHOLD", "4000"))
    keep_recent = int(os.getenv("MEMORY_KEEP_RECENT_MESSAGES", "6"))

    # 1. 极轻量字符粗筛快速短路（CPU 消耗近乎为 0）
    if quick_char_pass_through_filter(messages, token_threshold):
        return {}

    # 2. 精细估算全量 Token
    total_tokens = estimate_messages_tokens(messages)
    if total_tokens <= token_threshold:
        logger.debug(
            "[context_compressor] Token count %d <= threshold %d. Skipping compression.",
            total_tokens,
            token_threshold,
        )
        return {}

    # 3. 达到阈值，寻找安全语义边界
    safe_cut_index = find_safe_aimessage_cut_index(messages, keep_recent=keep_recent)
    if safe_cut_index is None:
        logger.info(
            "[context_compressor] Token count %d exceeded %d, but no valid AIMessage cut boundary found. Pass-through safely.",
            total_tokens,
            token_threshold,
        )
        return {}

    # 4. 提取从上一次游标到当前 safe_cut_index 的增量切片（带防逆流保护）
    current_cut_index = state.get("active_cut_index", 0)
    if safe_cut_index < current_cut_index:
        logger.debug(
            "[context_compressor] safe_cut_index (%d) < current_cut_index (%d). No new slice to compress.",
            safe_cut_index,
            current_cut_index,
        )
        return {}

    slice_to_compress = messages[current_cut_index : safe_cut_index + 1]
    if not slice_to_compress:
        return {}

    # 4. 执行增量总结
    existing_summary = state.get("summary", "")
    new_slice_text = format_messages_for_summary(slice_to_compress)

    user_prompt_content = build_memory_compression_user_prompt(
        existing_summary=existing_summary,
        new_slice_text=new_slice_text,
    )

    summary_llm = _get_summary_llm()
    prompt_messages = [
        SystemMessage(content=MEMORY_COMPRESSION_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt_content),
    ]

    try:
        response = await summary_llm.ainvoke(prompt_messages, config=config)
        new_summary = response.content if isinstance(response.content, str) else str(response.content)
        new_summary = new_summary.strip()
        logger.info(
            "[context_compressor] Successfully compressed context. Original tokens: %d, cut_index: %d, new_active_cut_index: %d",
            total_tokens,
            safe_cut_index,
            safe_cut_index + 1,
        )
        # 仅返回更新后的 summary 与切分游标，保证 messages 键绝不被触碰
        return {
            "summary": new_summary,
            "active_cut_index": safe_cut_index + 1,
        }
    except Exception as e:
        logger.error("[context_compressor] Failed to generate summary: %s. Continuing safely without compression.", str(e))
        return {}


