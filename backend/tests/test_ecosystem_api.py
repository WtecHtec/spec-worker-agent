import pytest
from httpx import AsyncClient, ASGITransport
from api_main import app
from src.infrastructure.mcp.client import McpClient


@pytest.mark.asyncio
async def test_mcp_stdio_real_server_execution():
    """测试真实的 stdio 模式 SQLite MCP 服务端执行"""
    client = McpClient(
        transport="stdio",
        command="python",
        args=["mcp-servers/sqlite_server/server.py"],
    )

    # 1. 发现工具
    tools = await client.list_tools()
    tool_names = [t.name for t in tools]
    assert "read_query" in tool_names
    assert "list_tables" in tool_names

    # 2. 执行 read_query
    res = await client.call_tool("read_query", {"query": "SELECT * FROM demo_users"})
    assert not res.is_error
    assert "Alice" in res.content[0].text


@pytest.mark.asyncio
async def test_ecosystem_rest_endpoints():
    """测试生态管理 REST 接口"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. 查询 MCP 服务列表
        mcp_res = await ac.get("/api/ecosystem/mcp")
        assert mcp_res.status_code == 200
        mcp_data = mcp_res.json()
        assert mcp_data["success"] is True
        assert len(mcp_data["servers"]) >= 1

        # 2. 测试 MCP 连通性测试接口 (stdio)
        test_res = await ac.post(
            "/api/ecosystem/mcp/test",
            json={
                "transport": "stdio",
                "command": "python",
                "args": ["mcp-servers/sqlite_server/server.py"],
            },
        )
        assert test_res.status_code == 200
        test_data = test_res.json()
        assert test_data["connected"] is True
        assert test_data["tools_count"] == 2

        # 3. 查询 A2A 专家列表
        a2a_res = await ac.get("/api/ecosystem/a2a")
        assert a2a_res.status_code == 200
        a2a_data = a2a_res.json()
        assert a2a_data["success"] is True
        assert len(a2a_data["agents"]) >= 1


@pytest.mark.asyncio
async def test_user_tool_registry_broadcast_invalidation():
    """测试 Redis 跨进程广播缓存失效机制"""
    from src.domain.services.tools.manager import user_tool_registry_manager
    from src.domain.services.tools.registry import ToolRegistry

    user_id = "test_invalidation_user"
    # 1. 模拟本地已有缓存
    user_tool_registry_manager._user_registries[user_id] = ToolRegistry()
    assert user_id in user_tool_registry_manager._user_registries

    # 2. 触发跨进程广播失效
    await user_tool_registry_manager.broadcast_invalidation(user_id)

    # 3. 验证本地已立即清除
    assert user_id not in user_tool_registry_manager._user_registries
