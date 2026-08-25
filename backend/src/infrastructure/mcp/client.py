from typing import Any, Literal
from contextlib import asynccontextmanager
import structlog
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
import mcp.types as mcp_types

logger = structlog.get_logger()


class McpClient:
    """
    官方 MCP (Model Context Protocol) 统一客户端：
    全面支持三种标准传输模式：
      - stdio       本地子进程（命令行）
      - sse         远程 HTTP SSE 长连接
      - streamable_http  远程 HTTP Streamable（最新官方推荐，支持 POST 流式响应）
    """

    def __init__(
        self,
        transport: Literal["stdio", "sse", "streamable_http", "https"] = "sse",
        # SSE / HTTP 模式参数
        server_url: str | None = None,
        headers: dict[str, str] | None = None,
        # stdio 模式参数
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        # 兼容旧的 "https" 别名 -> streamable_http
        if transport == "https":
            transport = "streamable_http"
        self.transport = transport
        self.server_url = (server_url or "").rstrip("/")
        self.headers = headers or {}
        self.command = command
        self.args = args or []
        self.env = env
        self.timeout = timeout

    @asynccontextmanager
    async def create_session(self):
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("MCP stdio 模式必须提供可执行 command")
            from pathlib import Path
            project_root = Path(__file__).resolve().parents[4]
            resolved_args = []
            for arg in self.args:
                p = project_root / arg
                if p.exists():
                    resolved_args.append(str(p))
                else:
                    resolved_args.append(arg)

            params = StdioServerParameters(
                command=self.command,
                args=resolved_args,
                env=self.env,
            )
            async with stdio_client(params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

        elif self.transport == "sse":
            if not self.server_url:
                raise ValueError("MCP sse 模式必须提供有效 server_url")
            async with sse_client(
                self.server_url,
                headers=self.headers or None,
                timeout=self.timeout,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

        elif self.transport == "streamable_http":
            if not self.server_url:
                raise ValueError("MCP streamable_http 模式必须提供有效 server_url")
            import httpx2
            # 如有请求头则手动构造 httpx2.AsyncClient
            if self.headers:
                http_client = httpx2.AsyncClient(headers=self.headers, timeout=self.timeout)
            else:
                http_client = None
            # streamable_http_client 只 yield (read_stream, write_stream) 两个值
            async with streamable_http_client(
                self.server_url,
                http_client=http_client,
            ) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    yield session

        else:
            raise ValueError(f"不支持的 MCP transport 类型: {self.transport}")

    async def list_tools(self) -> list[mcp_types.Tool]:
        """
        获取 MCP 服务提供的可用工具列表
        """
        log = logger.bind(transport=self.transport, endpoint=self.server_url or self.command)
        log.info("mcp_client_listing_tools")

        try:
            async with self.create_session() as session:
                result = await session.list_tools()
                log.info("mcp_client_tools_discovered", count=len(result.tools))
                return result.tools
        except Exception as e:
            log.warning("mcp_client_list_tools_failed", error=str(e))
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> mcp_types.CallToolResult:
        """
        执行 MCP 远程工具调用
        """
        log = logger.bind(transport=self.transport, tool_name=name)
        log.info("mcp_client_calling_tool", arguments=arguments)

        try:
            async with self.create_session() as session:
                result = await session.call_tool(name=name, arguments=arguments or {})
                return result
        except Exception as e:
            log.error("mcp_client_call_tool_failed", error=str(e))
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(type="text", text=f"MCP 调用异常: {str(e)}")],
                is_error=True,
            )
