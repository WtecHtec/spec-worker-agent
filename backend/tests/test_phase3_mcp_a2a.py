import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import mcp.types as mcp_types
import a2a.types as a2a_types
from src.infrastructure.mcp.client import McpClient
from src.infrastructure.mcp.adapter import McpToolAdapter
from src.infrastructure.a2a.client import A2AClient
from src.infrastructure.a2a.adapter import A2AToolAdapter
from src.domain.services.tools.registry import ToolRegistry
from src.domain.services.memory.episodic_memory import EpisodicMemoryManager
from src.infrastructure.sandbox.pool import SandboxPoolManager


@pytest.mark.asyncio
async def test_official_mcp_sdk_client_and_adapter():
    client = McpClient(server_url="http://localhost:8000/sse")

    mock_tool = mcp_types.Tool(
        name="github_search_issues",
        description="搜索 GitHub Issues",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )

    mock_call_result = mcp_types.CallToolResult(
        content=[mcp_types.TextContent(type="text", text="Found 3 open issues matching query")],
        is_error=False,
    )

    with patch.object(client, "list_tools", new_callable=AsyncMock) as mock_list, \
         patch.object(client, "call_tool", new_callable=AsyncMock) as mock_call:

        mock_list.return_value = [mock_tool]
        mock_call.return_value = mock_call_result

        # 1. 验证获取工具列表
        tools = await client.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "github_search_issues"

        # 2. 验证适配器挂载与执行
        adapter = McpToolAdapter(mcp_client=client, tool_def=tools[0], namespace="github")
        assert adapter.name == "github_github_search_issues"
        assert "[官方 MCP 生态工具]" in adapter.description
        assert "query" in adapter.parameters["properties"]

        res = await adapter.execute({}, query="bug fix")
        assert not res.is_error
        assert "Found 3 open issues" in res.output


@pytest.mark.asyncio
async def test_mcp_registry_mounting():
    reg = ToolRegistry()
    mock_tools = [
        mcp_types.Tool(name="postgres_query", description="SQL 查询", inputSchema={}),
        mcp_types.Tool(name="postgres_explain", description="SQL Explain", inputSchema={}),
    ]

    with patch("src.infrastructure.mcp.client.McpClient.list_tools", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = mock_tools

        count = await reg.register_mcp_server("http://localhost:5432/mcp", namespace="db")
        assert count == 2
        assert reg.get("db_postgres_query") is not None
        assert reg.get("db_postgres_explain") is not None


@pytest.mark.asyncio
async def test_a2a_tool_adapter_execution():
    """验证 A2A Agent 作为标准 BaseTool 的封装与执行"""
    from src.infrastructure.a2a.client import A2AClientWrapper
    client = A2AClientWrapper(endpoint_url="http://localhost:8090")
    card = a2a_types.AgentCard(
        name="researcher_specialist",
        description="外部调研专家智能体",
        version="1.0.0",
        skills=[a2a_types.AgentSkill(name="web_scraping", description="网页抽取")],
    )

    adapter = A2AToolAdapter(card=card, client=client, namespace="a2a")
    assert adapter.name == "a2a_researcher_specialist"
    assert "[Google A2A 外部专家智能体]" in adapter.description
    assert "message" in adapter.parameters["properties"]

    with patch.object(client, "send_task", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = "已完成调研报告。"
        res = await adapter.execute({}, message="调研最新技术动态")
        assert not res.is_error
        assert "已完成调研报告" in res.output


@pytest.mark.asyncio
async def test_a2a_registry_mounting():
    """验证 ToolRegistry 动态挂载 A2A 外部智能体为标准 Tool"""
    from src.infrastructure.a2a.client import A2AClientWrapper
    reg = ToolRegistry()
    card = a2a_types.AgentCard(
        name="coder_specialist",
        description="外部编码专家智能体",
        version="1.0.0",
        skills=[a2a_types.AgentSkill(name="coding", description="沙箱编程")],
    )

    with patch.object(A2AClientWrapper, "get_agent_card", new_callable=AsyncMock) as mock_get_card:
        mock_get_card.return_value = card
        success = await reg.register_a2a_server("http://localhost:8091", namespace="a2a")
        assert success is True
        tool = reg.get("a2a_coder_specialist")
        assert tool is not None
        assert "外部编码专家" in tool.description


def test_episodic_memory_reflection_and_retrieval():
    mem = EpisodicMemoryManager()
    mem.reflect_and_store(
        task_id="t_100",
        goal="抓取博客文章并生成 Markdown 报告",
        steps_summary=[{"title": "读取网页"}, {"title": "清洗正文"}],
        final_text="完成",
        success=True,
    )

    memories = mem.retrieve_relevant_experiences("请帮我抓取技术文章")
    assert len(memories) >= 1
    assert "成功经验" in memories[0]


@pytest.mark.asyncio
async def test_sandbox_pool_manager():
    pool = SandboxPoolManager(base_url="http://localhost:5050")
    with patch("src.infrastructure.sandbox.client.SandboxClient.health_check", return_value=True):
        ok = await pool.warm_up()
        assert ok is True
        assert pool.is_healthy is True

        client = pool.acquire_client()
        assert client.base_url == "http://localhost:5050"
