from typing import Any, AsyncGenerator
import structlog
from src.infrastructure.executor.base import AgentExecutor
from src.domain.services.flow.agent_flow import PlanAndExecuteFlow
from src.config.settings import get_settings

logger = structlog.get_logger()


class LlmAgentExecutor(AgentExecutor):
    """
    真实 LLM 执行器：
    当 AGENT_MODE=llm 时由工厂创建，通过 AgentFlow（PlanAndExecuteFlow）编排 Planner 与 ReAct 协同执行。
    """

    def __init__(self, task_input: dict[str, Any], resume_from_step: int = 0):
        self.task_input = task_input
        self.resume_from_step = resume_from_step
        self.settings = get_settings()
        self._result: dict[str, Any] = {}

    async def run(self) -> AsyncGenerator[dict[str, Any], None]:
        # 1. 提取指令文本
        instruction = (
            self.task_input.get("instruction")
            or self.task_input.get("content")
            or self.task_input.get("text")
            or self.task_input.get("prompt")
            or str(self.task_input)
        )

        # 2. 构造上下文
        user_id = self.task_input.get("user_id", "local_user")
        ctx = {
            "task_id": self.task_input.get("task_id", "local_task"),
            "session_id": self.task_input.get("session_id", "default"),
            "user_id": user_id,
            "workspace_dir": self.settings.llm_workspace_dir,
            "resume_from_step": self.resume_from_step,
            "history_messages": self.task_input.get("history_messages", []),
        }

        # 3. 获取用户级 ToolRegistry（优先命中内存热缓存，仅首次或配置变更时挂载）
        from src.domain.services.tools.manager import user_tool_registry_manager
        tool_registry = await user_tool_registry_manager.get_registry_for_user(user_id)
        logger.info(
            "llm_agent_executor_mounted_tools",
            user_id=user_id,
            total_tools=len(tool_registry.list_tools()),
            tool_names=[t.name for t in tool_registry.list_tools()],
        )

        # 4. 构造 PlanAndExecuteFlow 管道
        flow = PlanAndExecuteFlow(tool_registry=tool_registry)

        # 5. 执行 Flow 并将每一步 yield 给 Worker
        async for step in flow.run(instruction, ctx):
            if step.get("type") == "FINAL":
                self._result = {
                    "summary": step.get("content", {}).get("text", "任务完成"),
                    "total_steps": step.get("step_index", 0),
                }
            yield step


    def get_result(self) -> dict[str, Any]:
        return self._result
