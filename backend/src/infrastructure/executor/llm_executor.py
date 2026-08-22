from typing import AsyncGenerator
from src.infrastructure.executor.base import AgentExecutor


class LlmAgentExecutor(AgentExecutor):
    """
    真实 LLM 执行器（占位，AGENT_MODE=llm 时启用）。

    TODO 接入步骤：
    1. 将 Checkpoint.recent_messages 重建为 LLM messages 列表
    2. 调用 LLM API（openai / anthropic，流式）
    3. 解析流式响应：thinking / tool_call / tool_result / final
    4. 每解析出一个完整步骤，yield 给 Worker

    切换方式：
        修改 .env：AGENT_MODE=llm
        修改 .env：LLM_API_KEY=your-key
        Worker 中通过工厂函数自动选择此类
    """

    def __init__(self, task_input: dict, resume_from_step: int = 0):
        self.task_input = task_input
        self.resume_from_step = resume_from_step
        self._result: dict = {}

    async def run(self) -> AsyncGenerator[dict, None]:
        # TODO: 实现真实 LLM 调用逻辑
        raise NotImplementedError(
            "LlmAgentExecutor 尚未实现，请设置 AGENT_MODE=mock 或实现此类"
        )
        yield  # 保持 AsyncGenerator 类型

    def get_result(self) -> dict:
        return self._result
