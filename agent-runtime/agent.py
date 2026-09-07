"""
LangGraph P2 ReAct Agent 入口定义：
模块化装配 state、nodes、edges，遵循官方 Human-in-the-loop (interrupt) 规范。
"""

from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END

load_dotenv()

from src.state import AgentState
from src.nodes import agent_node, tools_node, context_compressor_node
from src.edges import should_continue

# 1. 初始化状态图
builder = StateGraph(AgentState)

# 2. 注册图节点
builder.add_node("context_compressor", context_compressor_node)
builder.add_node("agent_node", agent_node)
builder.add_node("tools_node", tools_node)

# 3. 编排图拓扑（经典健壮的 ReAct 闭环 + 显式上下文治理）：
# START -> context_compressor -> agent_node -> should_continue -> (tools_node -> agent_node) / END
builder.add_edge(START, "context_compressor")
builder.add_edge("context_compressor", "agent_node")
builder.add_conditional_edges(
    "agent_node",
    should_continue,
    {
        "tools_node": "tools_node",
        END: END,
    },
)
builder.add_edge("tools_node", "agent_node")

from src.tracing.callback import TurnTraceCallbackHandler

# 4. 编译图并接入标准生命周期回调（Trace 日志与甘特图上报）
graph = builder.compile().with_config({
    "callbacks": [TurnTraceCallbackHandler()],
})
