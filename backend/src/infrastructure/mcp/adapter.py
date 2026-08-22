from typing import Any
import mcp.types as mcp_types
from src.domain.services.tools.base import BaseTool, ToolResult
from .client import McpClient


class McpToolAdapter(BaseTool):
    """
    官方 MCP (Model Context Protocol) 动态工具适配器：
    基于官方 mcp Python SDK 类型体系 (mcp.types.Tool)，将外部 MCP 服务工具无缝接入系统 BaseTool 体系。
    """

    def __init__(self, mcp_client: McpClient, tool_def: mcp_types.Tool | dict[str, Any], namespace: str = "mcp"):
        self._client = mcp_client
        if isinstance(tool_def, dict):
            tool_def = mcp_types.Tool.model_validate(tool_def)
        self._tool_def = tool_def
        self._raw_name = tool_def.name
        self._name = f"{namespace}_{self._raw_name}" if namespace else self._raw_name
        self._description = tool_def.description or f"MCP 外部工具: {self._raw_name}"

        # 提取 input_schema (官方 mcp.types.Tool 属性)
        params = getattr(tool_def, "input_schema", None) or getattr(tool_def, "inputSchema", None)
        if params is None and isinstance(tool_def, dict):
            params = tool_def.get("inputSchema") or tool_def.get("input_schema")
        self._parameters = params or {
            "type": "object",
            "properties": {},
        }

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
        # 通过官方 McpClient SDK 发起 tools/call
        call_result: mcp_types.CallToolResult = await self._client.call_tool(self._raw_name, kwargs)

        output_texts = []
        for item in call_result.content:
            if isinstance(item, mcp_types.TextContent):
                output_texts.append(item.text)
            elif hasattr(item, "text") and getattr(item, "text"):
                output_texts.append(str(getattr(item, "text")))
            else:
                output_texts.append(str(item))

        final_output = "\n".join(output_texts) if output_texts else "MCP 工具执行成功（无文本输出）。"

        is_err = getattr(call_result, "is_error", False)
        if not is_err and hasattr(call_result, "isError"):
            is_err = getattr(call_result, "isError", False)

        return ToolResult(
            output=final_output,
            is_error=bool(is_err),
            metadata={
                "mcp_server": self._client.server_url,
                "raw_tool_name": self._raw_name,
                "content_items_count": len(call_result.content),
            },
        )
