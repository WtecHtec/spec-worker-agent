from abc import ABC, abstractmethod
from typing import Any
from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """工具统一执行结果"""
    output: Any = Field(description="工具输出内容（通常为文本或结构化数据）")
    is_error: bool = Field(default=False, description="是否执行出错")
    metadata: dict[str, Any] = Field(default_factory=dict, description="执行元数据")


class BaseTool(ABC):
    """工具抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识名称"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """工具能力详细描述（供 LLM 推理判定意图）"""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """遵循 JSON Schema 规范的入参定义"""
        pass

    @abstractmethod
    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        """异步执行工具调用"""
        pass

    def to_openai_tool(self) -> dict[str, Any]:
        """转换为 OpenAI Function Calling 标准格式字典"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
