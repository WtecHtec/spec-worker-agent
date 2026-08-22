from abc import ABC, abstractmethod
from typing import AsyncGenerator


class AgentExecutor(ABC):
    """
    Agent 执行器抽象基类。
    Worker 只依赖此接口，不关心底层是 Mock 还是真实 LLM。

    切换方式：
        AGENT_MODE=mock  → MockAgentExecutor
        AGENT_MODE=llm   → LlmAgentExecutor（待实现）
    """

    @abstractmethod
    async def run(self) -> AsyncGenerator[dict, None]:
        """
        异步 generator，每次 yield 一个步骤 dict。

        步骤结构：
        {
            "step_index":    int,   # 步骤序号，从 1 开始
            "type":          str,   # THINKING / TOOL_CALL / TOOL_RESULT / HITL_REQUEST / FINAL
            "content":       dict,  # 步骤具体内容，按 type 不同结构不同
            "wait_for_human": bool, # True 表示需要人工介入，yield 后 Worker 应暂停
        }
        """
        ...
        yield  # 使 Python 识别这是 AsyncGenerator

    @abstractmethod
    def get_result(self) -> dict:
        """
        任务完成后的最终结果摘要。
        在 run() 耗尽后调用。
        """
        ...
