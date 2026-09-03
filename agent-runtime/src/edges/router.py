from typing import Literal
from langgraph.graph import END
from src.state.state import AgentState


def should_continue(state: AgentState) -> Literal["tools_node", "__end__"]:
    """
    ReAct 条件路由边：
    - 若上一条 AI 消息包含 tool_calls，流转至 'tools_node'（内置高危审查与 HITL 中断）；
    - 若无 tool_calls，流转至 END。
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    last_message = messages[-1]
    tool_calls = getattr(last_message, "tool_calls", None)
    if tool_calls and len(tool_calls) > 0:
        return "tools_node"

    return END
