from typing import Any, Literal
from contextlib import asynccontextmanager
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
import mcp.types as mcp_types
from .base import BaseTool, ToolResult


class McpClient:
    """官方 MCP 统一客户端（支持 stdio / sse / streamable_http）"""

    def __init__(
        self,
        transport: Literal["stdio", "sse", "streamable_http", "https"] = "sse",
        server_url: str | None = None,
        headers: dict[str, str] | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
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
                raise ValueError("MCP stdio 模式必须提供 command")
            params = StdioServerParameters(
                command=self.command,
                args=self.args,
                env=self.env,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        elif self.transport == "sse":
            if not self.server_url:
                raise ValueError("MCP sse 模式必须提供 server_url")
            async with sse_client(self.server_url, headers=self.headers, timeout=self.timeout) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        elif self.transport == "streamable_http":
            if not self.server_url:
                raise ValueError("MCP streamable_http 模式必须提供 server_url")
            async with streamable_http_client(self.server_url, headers=self.headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        else:
            raise ValueError(f"不支持的 MCP 传输协议: {self.transport}")

    async def list_tools(self) -> list[mcp_types.Tool]:
        async with self.create_session() as session:
            result = await session.list_tools()
            return result.tools

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> mcp_types.CallToolResult:
        async with self.create_session() as session:
            return await session.call_tool(name, arguments or {})


class McpToolAdapter(BaseTool):
    """将 MCP 工具接入系统 BaseTool 规范"""

    def __init__(self, mcp_client: McpClient, tool_def: mcp_types.Tool | dict[str, Any], namespace: str = "mcp"):
        self._client = mcp_client
        if isinstance(tool_def, dict):
            tool_def = mcp_types.Tool.model_validate(tool_def)
        self._tool_def = tool_def
        self._raw_name = tool_def.name
        self._name = f"{namespace}_{self._raw_name}" if namespace else self._raw_name
        self._description = tool_def.description or f"MCP 外部工具: {self._raw_name}"

        params = getattr(tool_def, "input_schema", None) or getattr(tool_def, "inputSchema", None)
        if params is None and isinstance(tool_def, dict):
            params = tool_def.get("inputSchema") or tool_def.get("input_schema")
        self._parameters = params or {"type": "object", "properties": {}}

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"[官方 MCP 生态工具] {self._description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        try:
            call_result = await self._client.call_tool(self._raw_name, kwargs)
            texts = []
            for item in call_result.content:
                if isinstance(item, mcp_types.TextContent):
                    texts.append(item.text)
                elif hasattr(item, "text") and getattr(item, "text"):
                    texts.append(str(getattr(item, "text")))
                else:
                    texts.append(str(item))
            out = "\n".join(texts) if texts else "执行成功（无文本输出）。"
            is_err = getattr(call_result, "is_error", False) or getattr(call_result, "isError", False)
            return ToolResult(output=out, is_error=bool(is_err))
        except Exception as e:
            return ToolResult(output=f"MCP 工具执行异常: {str(e)}", is_error=True)
