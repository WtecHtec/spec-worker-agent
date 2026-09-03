from typing import Any, Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import EcosystemConfigRepository
from src.infrastructure.mcp.client import McpClient
from src.infrastructure.a2a.client import A2AClientWrapper
from src.interface.middleware.auth import bearer_scheme
from src.application.auth.security import decode_token
from src.domain.services.tools.manager import user_tool_registry_manager

logger = structlog.get_logger()
router = APIRouter(prefix="/api/ecosystem", tags=["Ecosystem (MCP & A2A)"])


async def get_current_user_id_flexible(
    credentials=Depends(bearer_scheme),
    token: str | None = None,
) -> str:
    """获取当前用户 ID，未提供 token 时回退到默认本地用户"""
    raw_token = None
    if credentials and credentials.credentials:
        raw_token = credentials.credentials
    elif token:
        raw_token = token

    if raw_token:
        try:
            return decode_token(raw_token)
        except Exception:
            pass
    return "local_user"


class RegisterMcpRequest(BaseModel):
    name: str = Field(description="MCP 服务显示名称")
    transport: Literal["stdio", "sse", "https", "streamable_http"] = Field(default="sse")
    server_url: str | None = Field(default=None, description="SSE/HTTPS 服务端点")
    command: str | None = Field(default=None, description="stdio 可执行命令")
    args: list[str] = Field(default_factory=list, description="stdio 启动参数")
    namespace: str = Field(default="mcp", description="工具命名前缀")
    description: str = Field(default="", description="服务简要描述")


class TestMcpConnectionRequest(BaseModel):
    transport: Literal["stdio", "sse", "https", "streamable_http"] = "sse"
    server_url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)


class RegisterA2ARequest(BaseModel):
    name: str = Field(description="A2A 专家名称")
    endpoint_url: str = Field(description="A2A 独立微服务端点 (例如 http://localhost:8090)")
    namespace: str = Field(default="a2a", description="工具命名前缀")
    description: str = Field(default="")


class TestA2AConnectionRequest(BaseModel):
    endpoint_url: str = Field(description="A2A 独立微服务端点")


# ── MCP 端点 ──

@router.get("/mcp")
async def list_mcp_servers(
    user_id: str = Depends(get_current_user_id_flexible),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户已持久化配置的 MCP 服务列表"""
    repo = EcosystemConfigRepository(db)
    configs = await repo.list_by_user(user_id=user_id, type="mcp")

    # 如果该用户初次访问且暂无配置，初始化默认示例配置
    if not configs:
        default_cfg = await repo.create(
            user_id=user_id,
            type="mcp",
            name="SQLite MCP (stdio 示例)",
            transport="stdio",
            command="python",
            args=["mcp-servers/sqlite_server/server.py"],
            namespace="sqlite",
            description="本地内存 SQLite 查询与表结构自省服务",
            cached_tools=[
                {"name": "read_query", "description": "执行只读 SQL 查询并返回格式化结果"},
                {"name": "list_tables", "description": "列出数据库中所有的表名"},
            ],
        )
        configs = [default_cfg]

    return {
        "success": True,
        "servers": [
            {
                "id": c.id,
                "name": c.name,
                "transport": c.transport,
                "server_url": c.server_url,
                "command": c.command,
                "args": c.args,
                "namespace": c.namespace,
                "description": c.description,
                "status": "active" if c.enabled else "disabled",
                "tools_count": len(c.cached_tools),
                "tools": c.cached_tools,
            }
            for c in configs
        ],
    }


@router.post("/mcp/test")
async def test_mcp_connection(req: TestMcpConnectionRequest):
    """在线测试 MCP Server 连通性并获取其工具列表"""
    try:
        client = McpClient(
            transport=req.transport,
            server_url=req.server_url,
            command=req.command,
            args=req.args,
            timeout=10.0,
        )
        tools = await client.list_tools()
        formatted_tools = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": getattr(t, "input_schema", None) or getattr(t, "inputSchema", {}),
            }
            for t in tools
        ]
        return {
            "success": True,
            "connected": True,
            "tools_count": len(tools),
            "tools": formatted_tools,
        }
    except Exception as e:
        logger.warning("mcp_test_connection_failed", error=str(e))
        return {"success": False, "connected": False, "error": str(e), "tools": []}


@router.post("/mcp")
async def register_mcp_server(
    req: RegisterMcpRequest,
    user_id: str = Depends(get_current_user_id_flexible),
    db: AsyncSession = Depends(get_db),
):
    """动态添加并持久化配置一个新的 MCP 服务（入库并失效旧缓存）"""
    client = McpClient(
        transport=req.transport,
        server_url=req.server_url,
        command=req.command,
        args=req.args,
        timeout=10.0,
    )
    tools = await client.list_tools()
    cached_tools = [{"name": t.name, "description": t.description} for t in tools]

    repo = EcosystemConfigRepository(db)
    model = await repo.create(
        user_id=user_id,
        type="mcp",
        name=req.name,
        transport=req.transport,
        server_url=req.server_url,
        command=req.command,
        args=req.args,
        namespace=req.namespace,
        description=req.description,
        cached_tools=cached_tools,
    )

    # 触发用户级跨进程缓存失效广播（使 Worker 与所有 API 进程自动热重载）
    await user_tool_registry_manager.broadcast_invalidation(user_id)

    return {
        "success": True,
        "server": {
            "id": model.id,
            "name": model.name,
            "transport": model.transport,
            "server_url": model.server_url,
            "command": model.command,
            "args": model.args,
            "namespace": model.namespace,
            "description": model.description,
            "status": "active",
            "tools_count": len(cached_tools),
            "tools": cached_tools,
        },
    }


@router.delete("/mcp/{config_id}")
async def delete_mcp_server(
    config_id: str,
    user_id: str = Depends(get_current_user_id_flexible),
    db: AsyncSession = Depends(get_db),
):
    """卸载并从数据库中删除指定的 MCP 服务"""
    repo = EcosystemConfigRepository(db)
    success = await repo.delete(config_id=config_id, user_id=user_id)
    if success:
        await user_tool_registry_manager.broadcast_invalidation(user_id)
    return {
        "success": success,
        "message": "MCP 服务已成功移除。" if success else "未找到对应服务或无权限。",
    }


# ── A2A 端点 ──

@router.get("/a2a")
async def list_a2a_agents(
    user_id: str = Depends(get_current_user_id_flexible),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户已持久化配置的 Google A2A 外部智能体微服务列表"""
    repo = EcosystemConfigRepository(db)
    configs = await repo.list_by_user(user_id=user_id, type="a2a")

    if not configs:
        default_a2a = await repo.create(
            user_id=user_id,
            type="a2a",
            name="Researcher Specialist",
            server_url="http://localhost:8090",
            namespace="a2a",
            description="专注于公开互联网情报检索、技术文献深入阅读与事实查证的外部 A2A 专家智能体",
            cached_tools=[
                {"name": "web_scraping", "description": "从公开互联网结构化提取关键事实"},
                {"name": "fact_checking", "description": "跨来源数据交叉核验与事实考证"},
                {"name": "report_generation", "description": "生成高结构化专业技术研报"},
            ],
        )
        configs = [default_a2a]

    return {
        "success": True,
        "agents": [
            {
                "id": c.id,
                "name": c.name,
                "endpoint_url": c.server_url,
                "namespace": c.namespace,
                "status": "active" if c.enabled else "disabled",
                "description": c.description,
                "skills": c.cached_tools,
            }
            for c in configs
        ],
    }


@router.post("/a2a/test")
async def test_a2a_connection(req: TestA2AConnectionRequest):
    """测试外部 A2A 服务的连通性并拉取其官方 AgentCard"""
    client = A2AClientWrapper(endpoint_url=req.endpoint_url, timeout=5.0)
    card = await client.get_agent_card()
    if card:
        return {
            "success": True,
            "connected": True,
            "agent_card": {
                "name": card.name,
                "description": card.description,
                "version": card.version,
                "skills": [{"name": s.name, "description": s.description} for s in card.skills],
            },
        }
    return {
        "success": False,
        "connected": False,
        "error": "无法从指定端点获取 /.well-known/agent-card.json",
    }


@router.post("/a2a")
async def register_a2a_agent(
    req: RegisterA2ARequest,
    user_id: str = Depends(get_current_user_id_flexible),
    db: AsyncSession = Depends(get_db),
):
    """动态添加并持久化外部 A2A 智能体服务配置（入库并失效旧缓存）"""
    client = A2AClientWrapper(endpoint_url=req.endpoint_url, timeout=5.0)
    card = await client.get_agent_card()
    cached_skills = (
        [{"name": s.name, "description": s.description} for s in card.skills] if card else []
    )

    repo = EcosystemConfigRepository(db)
    model = await repo.create(
        user_id=user_id,
        type="a2a",
        name=card.name if card else req.name,
        server_url=req.endpoint_url,
        namespace=req.namespace,
        description=card.description if card else req.description,
        cached_tools=cached_skills,
    )

    # 触发用户级跨进程缓存失效广播
    await user_tool_registry_manager.broadcast_invalidation(user_id)

    return {
        "success": True,
        "agent": {
            "id": model.id,
            "name": model.name,
            "endpoint_url": model.server_url,
            "namespace": model.namespace,
            "status": "active",
            "description": model.description,
            "skills": cached_skills,
        },
    }


@router.delete("/a2a/{config_id}")
async def delete_a2a_agent(
    config_id: str,
    user_id: str = Depends(get_current_user_id_flexible),
    db: AsyncSession = Depends(get_db),
):
    """卸载并从数据库中删除指定的 A2A 外部服务"""
    repo = EcosystemConfigRepository(db)
    success = await repo.delete(config_id=config_id, user_id=user_id)
    if success:
        await user_tool_registry_manager.broadcast_invalidation(user_id)
    return {
        "success": success,
        "message": "A2A 服务已成功移除。" if success else "未找到对应服务或无权限。",
    }


@router.get("/active-tools")
async def get_active_tools(
    user_id: str = Depends(get_current_user_id_flexible),
):
    """
    多租户工具查询：获取当前登录用户当前生效的所有工具列表
    （包含系统内置、Docker沙箱、CDP浏览器，以及该用户专属启用的 MCP 和 A2A 工具）
    """
    registry = await user_tool_registry_manager.get_registry_for_user(user_id)
    tool_items = []
    for t in registry.list_tools():
        name = t.name
        if name.startswith("mcp_"):
            category = "mcp"
        elif name.startswith("a2a_"):
            category = "a2a"
        elif name.startswith("sandbox_"):
            category = "sandbox"
        elif name.startswith("browser_"):
            category = "browser"
        else:
            category = "builtin"

        tool_items.append({
            "name": name,
            "description": t.description,
            "parameters": t.parameters,
            "category": category,
        })

    return {
        "user_id": user_id,
        "total_count": len(tool_items),
        "tools": tool_items,
    }
