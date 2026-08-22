from typing import Any
from .base import BaseAgent


class ReActAgent(BaseAgent):
    """
    ReAct 模式执行 Agent：
    继承 BaseAgent 通用运行循环，专注于提供 ReAct 专属的系统提示词与执行策略。
    """

    def get_system_prompt(self, ctx: dict[str, Any]) -> str:
        """从模板渲染 ReAct 角色指令（包含全部已挂载工具及其详细 Schema）"""
        from datetime import datetime
        workspace_dir = ctx.get("workspace_dir", self.settings.llm_workspace_dir)
        return self.prompt_manager.render(
            "system/react_worker.md",
            workspace_dir=workspace_dir,
            current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tools_description=self.format_tools_catalog(),
        )
