import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage

from src.state.state import AgentState
from src.nodes.context_compressor import (
    estimate_messages_tokens,
    find_safe_aimessage_cut_index,
    context_compressor_node,
)
from src.nodes.agent_node import agent_node
from agent import graph


def test_estimate_messages_tokens():
    messages = [
        HumanMessage(content="你好，请问你是谁？"),
        AIMessage(content="你好！我是你的智能助手。"),
    ]
    tokens = estimate_messages_tokens(messages)
    assert tokens > 10


def test_find_safe_aimessage_cut_index_short():
    # 消息条数小于等于 keep_recent 时，不截断返回 None
    messages = [
        HumanMessage(content="1"),
        AIMessage(content="2"),
        HumanMessage(content="3"),
    ]
    assert find_safe_aimessage_cut_index(messages, keep_recent=4) is None


def test_find_safe_aimessage_cut_index_text_chat():
    # 连续对话：保留最近 2 条 (索引 4, 5)，待选截断区为 0~3
    # 索引 0: User 1
    # 索引 1: AI 1 (合法 AIMessage)
    # 索引 2: User 2
    # 索引 3: AI 2 (合法 AIMessage) <- 应该被选为截断切片末尾
    # 索引 4: User 3 (近期保留)
    # 索引 5: AI 3 (近期保留)
    messages = [
        HumanMessage(content="User 1"),
        AIMessage(content="AI 1"),
        HumanMessage(content="User 2"),
        AIMessage(content="AI 2"),
        HumanMessage(content="User 3"),
        AIMessage(content="AI 3"),
    ]
    cut_idx = find_safe_aimessage_cut_index(messages, keep_recent=2)
    assert cut_idx == 3
    assert isinstance(messages[cut_idx], AIMessage)
    assert messages[cut_idx].content == "AI 2"


def test_find_safe_aimessage_cut_index_tool_call_safety():
    """
    测试工具调用场景下的语义安全性：
    绝不能把带有 tool_calls 的中间 AIMessage 选为截断点！
    """
    # 构造如下序列：
    # 0: User 1
    # 1: AI 1 (纯文本 final answer) -> 合法候选
    # 2: User 2
    # 3: AI 2 (发出 tool_calls, 尚未完成最终回答) -> 严禁切断于此！
    # 4: ToolMessage (工具执行结果)
    # 5: AI 2 final (工具执行完毕后的最终文本回答) -> 合法候选
    # 6: User 3 (近期保留)
    # 7: AI 3 (近期保留)
    # 8: User 4 (近期保留)
    ai_intermediate = AIMessage(content="正在调用搜索工具...")
    ai_intermediate.tool_calls = [{"name": "search", "args": {"query": "weather"}, "id": "call_1"}]

    messages = [
        HumanMessage(content="User 1"),
        AIMessage(content="AI 1 final"),
        HumanMessage(content="User 2"),
        ai_intermediate,
        ToolMessage(content="Sunny 25C", tool_call_id="call_1"),
        AIMessage(content="AI 2 final"),
        HumanMessage(content="User 3"),
        AIMessage(content="AI 3"),
        HumanMessage(content="User 4"),
    ]

    # 保留近期 3 条 (索引 6, 7, 8)，候选截断区为 0~5
    # 索引 5 是 AI 2 final（无 tool_calls），应精准匹配到 5
    cut_idx = find_safe_aimessage_cut_index(messages, keep_recent=3)
    assert cut_idx == 5
    assert messages[cut_idx].content == "AI 2 final"

    # 若保留近期 4 条 (索引 5, 6, 7, 8)，候选截断区为 0~4
    # 索引 4 是 ToolMessage, 索引 3 是含有 tool_calls 的 AIMessage (跳过),
    # 应该一路回退找到 索引 1 (AI 1 final)！
    cut_idx_earlier = find_safe_aimessage_cut_index(messages, keep_recent=4)
    assert cut_idx_earlier == 1
    assert messages[cut_idx_earlier].content == "AI 1 final"


@pytest.mark.asyncio
async def test_context_compressor_node_passthrough():
    """未超 Token 阈值时，纯 Pass-through 返回空字典"""
    state: AgentState = {
        "messages": [
            HumanMessage(content="Hi"),
            AIMessage(content="Hello"),
        ],
    }
    with patch.dict("os.environ", {"MEMORY_COMPRESSION_TOKEN_THRESHOLD": "1000"}):
        result = await context_compressor_node(state)
        assert result == {}


@pytest.mark.asyncio
async def test_context_compressor_node_triggers_compression():
    """超过 Token 阈值时，触发增量压缩并更新 summary 与 active_cut_index，绝不返回 messages 键"""
    messages = [
        HumanMessage(content="Question 1"),
        AIMessage(content="Answer 1"),
        HumanMessage(content="Question 2"),
        AIMessage(content="Answer 2"),
        HumanMessage(content="Question 3"),
        AIMessage(content="Answer 3"),
    ]
    state: AgentState = {
        "messages": messages,
        "summary": "旧摘要：用户进行了问候",
        "active_cut_index": 0,
    }

    mock_llm_response = MagicMock()
    mock_llm_response.content = "新提炼摘要：用户连续提出了 2 个关键问题并得到了解答。"

    with patch.dict("os.environ", {
        "MEMORY_COMPRESSION_TOKEN_THRESHOLD": "10",  # 极低阈值强制触发
        "MEMORY_KEEP_RECENT_MESSAGES": "2",          # 保留近 2 条 (索引 4, 5)
    }):
        with patch("src.nodes.context_compressor._get_summary_llm") as mock_get_llm:
            mock_llm = MagicMock()
            mock_llm.ainvoke = AsyncMock(return_value=mock_llm_response)
            mock_get_llm.return_value = mock_llm

            result = await context_compressor_node(state)

            # 核心断言：
            # 1. 绝对不包含 messages 键（确保 PostgreSQL Checkpoint 里的全量历史不被覆盖或删除）
            assert "messages" not in result
            # 2. 包含 summary
            assert result["summary"] == "新提炼摘要：用户连续提出了 2 个关键问题并得到了解答。"
            # 3. active_cut_index 指向切片末尾索引 3 的下一条 (索引 4)
            assert result["active_cut_index"] == 4


@pytest.mark.asyncio
async def test_agent_node_slices_messages_and_injects_summary():
    """测试 agent_node 结合 active_cut_index 提取近期切片并将 summary 注入 Prompt"""
    all_messages = [
        HumanMessage(content="Old Question 1"),
        AIMessage(content="Old Answer 1"),
        HumanMessage(content="Recent Question"),
    ]
    state: AgentState = {
        "messages": all_messages,
        "summary": "前置对话沉淀的背景知识",
        "active_cut_index": 2,  # 仅保留索引 2 往后的消息
    }

    mock_response = AIMessage(content="我是处理近期提问的回答")

    with patch("src.nodes.agent_node.llm") as mock_llm:
        mock_bound_llm = MagicMock()
        mock_bound_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm.bind_tools.return_value = mock_bound_llm

        result = await agent_node(state)

        # 检查传给 ainvoke 的参数
        call_args = mock_bound_llm.ainvoke.call_args[0][0]
        # 第一条必须是注入了 summary 的 SystemMessage
        assert isinstance(call_args[0], SystemMessage)
        assert "前置对话沉淀的背景知识" in call_args[0].content
        # 剩下的只有 Recent Question，Old Question 1 / Old Answer 1 不在 LLM 的输入中
        assert len(call_args) == 2
        assert call_args[1].content == "Recent Question"

        # 结果只返回自身的新 AIMessage，不碰全局其他历史
        assert result == {"messages": [mock_response]}


def test_graph_topology():
    """验证 LangGraph 拓扑结构正确编排了 context_compressor 节点"""
    nodes = graph.nodes
    assert "context_compressor" in nodes
    assert "agent_node" in nodes
    assert "tools_node" in nodes


def test_summary_prompt_sections():
    """验证独立提示词模块中严格包含 6 个核心结构化二级标题及组装函数"""
    from src.prompts.memory import (
        MEMORY_COMPRESSION_SYSTEM_PROMPT,
        build_memory_compression_user_prompt,
    )

    required_sections = [
        "## Goal",
        "## Constraints & Preferences",
        "## Progress",
        "## Key Decisions",
        "## Next Steps",
        "## Critical Context",
    ]
    for sec in required_sections:
        assert sec in MEMORY_COMPRESSION_SYSTEM_PROMPT, f"Missing required section {sec} in MEMORY_COMPRESSION_SYSTEM_PROMPT"

    # 测试用户提示词组装函数
    user_prompt = build_memory_compression_user_prompt("旧摘要内容", "新增对话")
    assert "旧摘要内容" in user_prompt
    assert "新增对话" in user_prompt


def test_quick_char_pass_through_filter():
    """验证字符粗筛能在短文本场景下微秒级短路放行"""
    from src.nodes.context_compressor import quick_char_pass_through_filter

    short_messages = [
        HumanMessage(content="Hello"),
        AIMessage(content="Hi there!"),
    ]
    # 总字符数远小于 4000，必须返回 True（放行短路）
    assert quick_char_pass_through_filter(short_messages, token_threshold=4000) is True

    long_messages = [
        HumanMessage(content="A" * 5000),
    ]
    # 字符数超过阈值，返回 False（需进入精确计算）
    assert quick_char_pass_through_filter(long_messages, token_threshold=4000) is False


@pytest.mark.asyncio
async def test_cursor_safeguard_no_new_slice():
    """验证游标防逆流：若自上次压缩后未产生新的合法 AIMessage 结论，幂等跳过不调用 LLM"""
    messages = [
        HumanMessage(content="Q1"),
        AIMessage(content="A1"),
        HumanMessage(content="Q2"),
        AIMessage(content="A2"),
    ]
    # 假设上一次已经压缩到了索引 3 的后一条（active_cut_index = 4）
    state: AgentState = {
        "messages": messages,
        "summary": "已有完整摘要",
        "active_cut_index": 4,
    }

    with patch.dict("os.environ", {
        "MEMORY_COMPRESSION_TOKEN_THRESHOLD": "1",  # 强制超标
        "MEMORY_KEEP_RECENT_MESSAGES": "1",
    }):
        with patch("src.nodes.context_compressor._get_summary_llm") as mock_get_llm:
            result = await context_compressor_node(state)
            # 安全防逆流触发，直接返回空字典，且决不调用 LLM
            assert result == {}
            mock_get_llm.assert_not_called()



