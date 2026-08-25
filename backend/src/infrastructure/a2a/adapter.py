from typing import Any
import re
import a2a.types as a2a_types
from src.domain.services.tools.base import BaseTool, ToolResult
from .client import A2AClientWrapper


class A2AToolAdapter(BaseTool):
    """
    Google A2A 协议外部智能体工具适配器：
    将外部独立的 A2A Agent（及其 AgentCard）包装为符合系统标准接口的 BaseTool。
    让主 Agent（Planner / ReAct）能通过标准 Function Calling 向远程专家 Agent 委派任务。
    """

    def __init__(self, card: a2a_types.AgentCard, client: A2AClientWrapper, namespace: str = "a2a"):
        self._card = card
        self._client = client
        # 清理非法字符以符合 OpenAI Function Calling name 规范
        raw_name = re.sub(r"[^a-zA-Z0-9_-]", "_", card.name).lower().strip("_")
        self._name = f"{namespace}_{raw_name}" if namespace else raw_name

        skills_list = [f"{s.name}: {s.description}" for s in card.skills if s.name]
        skills_text = f"（核心技能: {'; '.join(skills_list)}）" if skills_list else ""
        self._description = f"[Google A2A 外部专家智能体] {card.description} {skills_text}".strip()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": f"派发给 {self._card.name} 专家执行的明确任务指令与交付要求",
                }
            },
            "required": ["message"],
        }

    async def execute(self, ctx: dict[str, Any], message: str) -> ToolResult:
        output_text = await self._client.send_task(message=message, context=ctx)
        is_err = "错误" in output_text or "异常" in output_text or "HTTP" in output_text

        return ToolResult(
            output=f"【A2A 外部专家 ({self._card.name}) 执行报告】:\n{output_text}",
            is_error=is_err,
            metadata={
                "agent_name": self._card.name,
                "agent_version": self._card.version,
                "endpoint": self._client.endpoint_url,
            },
        )
