from typing import Any
from .base import BaseTool, ToolResult
from .builtin import CalculatorTool, CurrentTimeTool, FetchWebpageTool
from .sandbox import SandboxRunCommandTool, SandboxReadFileTool, SandboxWriteFileTool
from .mcp_adapter import McpClient, McpToolAdapter
from .a2a_adapter import A2AClientWrapper, A2AToolAdapter
from .hitl import HitlRequestTool


class ToolRegistry:
    """工具注册中心（实例级别，支持多租户独立隔离）"""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    async def register_mcp_server(
        self,
        server_url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        transport: str = "sse",
        namespace: str = "mcp",
    ) -> int:
        client = McpClient(
            transport=transport,
            server_url=server_url,
            command=command,
            args=args or [],
        )
        tools = await client.list_tools()
        count = 0
        for t_def in tools:
            adapter = McpToolAdapter(mcp_client=client, tool_def=t_def, namespace=namespace)
            self.register(adapter)
            count += 1
        return count

    async def register_a2a_server(self, endpoint_url: str, namespace: str = "a2a") -> bool:
        """动态挂载 Google A2A 外部智能体专家服务"""
        client = A2AClientWrapper(endpoint_url=endpoint_url)
        card = await client.get_agent_card()
        if card:
            adapter = A2AToolAdapter(card=card, client=client, namespace=namespace)
            self.register(adapter)
            return True
        return False

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_openai_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict[str, Any], ctx: dict[str, Any]) -> ToolResult:
        tool = self.get(name)
        if not tool:
            return ToolResult(output=f"未找到对应工具 [{name}]", is_error=True)
        try:
            return await tool.execute(ctx, **arguments)
        except Exception as e:
            return ToolResult(output=f"工具 [{name}] 执行异常: {str(e)}", is_error=True)


def create_default_registry() -> ToolRegistry:
    """初始化基础工具集合（内置数学/时间/网络 + 沙箱执行与文件操作）"""
    reg = ToolRegistry()
    reg.register(CalculatorTool())
    reg.register(CurrentTimeTool())
    reg.register(FetchWebpageTool())
    reg.register(SandboxRunCommandTool())
    reg.register(SandboxReadFileTool())
    reg.register(SandboxWriteFileTool())
    reg.register(HitlRequestTool())
    return reg
