from src.config.settings import get_settings
from src.infrastructure.executor.base import AgentExecutor

settings = get_settings()


def create_executor(task_input: dict, resume_from_step: int = 0) -> AgentExecutor:
    """
    执行器工厂函数。
    根据 AGENT_MODE 环境变量自动选择实现：
        mock → MockAgentExecutor
        llm  → LlmAgentExecutor

    Worker 调用示例：
        executor = create_executor(task.input, resume_from_step=3)
        async for step in executor.run():
            ...
    """
    if settings.agent_mode == "llm":
        from src.infrastructure.executor.llm_executor import LlmAgentExecutor
        return LlmAgentExecutor(task_input, resume_from_step)

    from src.infrastructure.executor.mock_executor import MockAgentExecutor
    return MockAgentExecutor(task_input, resume_from_step)
