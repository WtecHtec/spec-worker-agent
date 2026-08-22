from typing import Any
import structlog
from .base import BaseTool, ToolResult
from .builtin import CalculatorTool, CurrentTimeTool, FetchWebpageTool
from .sandbox import SandboxRunCommandTool, SandboxReadFileTool, SandboxWriteFileTool

logger = structlog.get_logger()


class ToolRegistry:
    """
    统一工具注册中心：
    管理可用工具集合，支持动态将外部 MCP Server 工具与 Google A2A 外部智能体无缝注册为系统标准 Tool。
    """

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册一个工具"""
        if tool.name in self._tools:
            logger.warning("tool_already_registered_overwrite", tool_name=tool.name)
        self._tools[tool.name] = tool

    async def register_mcp_server(
        self,
        server_url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        transport: str = "sse",
        namespace: str = "mcp",
    ) -> int:
        """
        动态连接外部 MCP Server，支持三种官方传输模式：
          - stdio: 本地子进程（命令行）
          - sse: 远程 HTTP SSE 长连接
          - streamable_http: 远程 HTTP Streamable（官方最新推荐）
        """
        from src.infrastructure.mcp.client import McpClient
        from src.infrastructure.mcp.adapter import McpToolAdapter

        if command or transport == "stdio":
            client = McpClient(transport="stdio", command=command, args=args or [])
        elif server_url:
            # 明确传入的 transport 类型（sse / streamable_http）
            client = McpClient(transport=transport, server_url=server_url)
        else:
            raise ValueError("必须提供 server_url（sse/streamable_http）或 command（stdio）")

        tools = await client.list_tools()
        registered_count = 0
        mounted_tool_names = []
        for t_def in tools:
            adapter = McpToolAdapter(mcp_client=client, tool_def=t_def, namespace=namespace)
            self.register(adapter)
            mounted_tool_names.append(adapter.name)
            registered_count += 1
        logger.info(
            "mcp_server_tools_mounted",
            transport=transport,
            endpoint=server_url or command,
            count=registered_count,
            tool_names=mounted_tool_names,
        )
        return registered_count

    async def register_a2a_server(self, endpoint_url: str, namespace: str = "a2a") -> bool:
        """
        动态连接外部 Google A2A 专家服务，获取其 AgentCard 并挂载为系统工具
        """
        from src.infrastructure.a2a.client import A2AClientWrapper
        from src.infrastructure.a2a.adapter import A2AToolAdapter

        client = A2AClientWrapper(endpoint_url=endpoint_url)
        card = await client.get_agent_card()
        if card:
            adapter = A2AToolAdapter(card=card, client=client, namespace=namespace)
            self.register(adapter)
            logger.info(
                "a2a_agent_tool_mounted",
                agent_name=card.name,
                tool_name=adapter.name,
                skills=[s.name for s in card.skills],
            )
            return True
        return False

    def unregister_namespace(self, namespace: str) -> int:
        """根据命名空间批量卸载工具"""
        to_remove = [k for k in self._tools if k.startswith(f"{namespace}_")]
        for k in to_remove:
            del self._tools[k]
        return len(to_remove)

    def get(self, name: str) -> BaseTool | None:
        """根据名称获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """获取所有已注册工具"""
        return list(self._tools.values())

    def get_openai_tools(self) -> list[dict[str, Any]]:
        """获取符合 OpenAI Function Calling 规范的工具列表"""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def dispatch(self, name: str, arguments: dict[str, Any], ctx: dict[str, Any]) -> ToolResult:
        """
        分发并执行工具调用
        """
        tool = self.get(name)
        if not tool:
            return ToolResult(
                output=f"未找到对应工具 [{name}]，请检查工具名称是否正确",
                is_error=True,
            )

        log = logger.bind(tool_name=name, task_id=ctx.get("task_id"))
        log.info("dispatching_tool", arguments=arguments)

        try:
            result = await tool.execute(ctx, **arguments)
            return result
        except Exception as e:
            log.error("tool_execution_failed", error=str(e))
            return ToolResult(
                output=f"工具 [{name}] 执行异常: {str(e)}",
                is_error=True,
                metadata={"error": str(e)},
            )


def create_default_registry() -> ToolRegistry:
    """创建默认注册中心实例（包含纯内存内置工具与沙箱环境工具）"""
    registry = ToolRegistry()
    # 1. 纯内存本地内置工具 (Builtin Tools)
    registry.register(CalculatorTool())
    registry.register(CurrentTimeTool())
    registry.register(FetchWebpageTool())

    # 2. 隔离环境沙箱工具 (Sandbox Tools)
    registry.register(SandboxRunCommandTool())
    registry.register(SandboxReadFileTool())
    registry.register(SandboxWriteFileTool())
    return registry
