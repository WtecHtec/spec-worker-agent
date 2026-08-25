from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """工具执行结果"""
    output: str = Field(description="工具输出内容（字符串格式回填给 LLM）")
    is_error: bool = Field(default=False, description="是否为执行错误")
    metadata: dict[str, Any] = Field(default_factory=dict, description="额外执行元数据（如耗时、是否截断等）")

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "is_error": self.is_error,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """
    统一 Tool 抽象基类。
    所有工具（本地工具、沙箱工具、MCP工具、A2A工具）均需继承此类。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述，指导 LLM 何时及如何使用"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """符合 JSON Schema 规范的参数结构定义"""
        ...

    @abstractmethod
    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        """
        执行工具具体逻辑。
        :param ctx: 运行时上下文（包含 workspace_dir, task_id, user_id 等）
        :param kwargs: 大模型传入的具名参数
        """
        ...

    def to_openai_tool(self) -> dict[str, Any]:
        """转换为 OpenAI Function/Tool Schema 规范"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
