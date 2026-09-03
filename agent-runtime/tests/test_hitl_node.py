import pytest
from langchain_core.messages import AIMessage
from src.tools.hitl import HitlRequestTool
from src.nodes.hitl_node import hitl_node
from src.edges.router import should_continue
from src.state.state import AgentState


def test_hitl_tool_schema():
    tool = HitlRequestTool()
    schema = tool.to_openai_tool()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "request_human_interaction"
    props = schema["function"]["parameters"]["properties"]
    assert "title" in props
    assert "description" in props
    assert "form_fields" in props
    assert "risk_level" in props


def test_router_branching():
    # 1. 遇到常规计算器工具 -> 路由至 tools_node
    ai_msg_tool = AIMessage(
        content="",
        tool_calls=[{"name": "calculator", "args": {"expression": "1+1"}, "id": "call_1"}],
    )
    state_normal: AgentState = {"messages": [ai_msg_tool]}
    assert should_continue(state_normal) == "tools_node"

    # 2. 遇到 HITL 交互请求 -> 同样路由至 tools_node（在 tools_node 内统一审查并触发 interrupt 挂起）
    ai_msg_hitl = AIMessage(
        content="",
        tool_calls=[{
            "name": "request_human_interaction",
            "args": {
                "title": "删除确认",
                "description": "危险操作",
                "risk_level": "high",
                "form_fields": [{"field_id": "confirm", "label": "是否同意", "type": "confirm"}],
            },
            "id": "call_hitl_1",
        }],
    )
    state_hitl: AgentState = {"messages": [ai_msg_hitl]}
    assert should_continue(state_hitl) == "tools_node"

    # 3. 普通文本消息 -> 路由至 __end__
    ai_msg_text = AIMessage(content="你好，任务已完成！")
    state_end: AgentState = {"messages": [ai_msg_text]}
    assert should_continue(state_end) == "__end__"


@pytest.mark.asyncio
async def test_hitl_node_execution():
    ai_msg = AIMessage(
        content="",
        tool_calls=[{
            "name": "request_human_interaction",
            "args": {
                "title": "高危数据库迁移审批",
                "description": "即将执行重建表结构操作",
                "risk_level": "critical",
                "form_fields": [
                    {
                        "field_id": "choice",
                        "label": "审批结果",
                        "type": "single_select",
                        "options": ["批准执行", "拒绝取消"],
                    },
                    {
                        "field_id": "remark",
                        "label": "备注说明",
                        "type": "text_input",
                    },
                ],
            },
            "id": "call_hitl_test",
        }],
    )
    state: AgentState = {"messages": [ai_msg]}
    result = await hitl_node(state)

    messages = result.get("messages", [])
    assert len(messages) == 1
    tool_msg = messages[0]
    assert tool_msg.tool_call_id == "call_hitl_test"
    assert "高危数据库迁移审批" in tool_msg.content
    assert "CRITICAL" in tool_msg.content

    pending = result.get("pending_hitl")
    assert pending is not None
    assert pending["title"] == "高危数据库迁移审批"
    assert pending["risk_level"] == "critical"
    assert len(pending["form_fields"]) == 2
