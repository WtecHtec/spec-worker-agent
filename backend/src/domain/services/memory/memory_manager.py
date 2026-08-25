from typing import Any
import structlog
from src.domain.services.agents.planner import PlanStepModel

logger = structlog.get_logger()


class MemoryManager:
    """
    三层记忆与上下文管理体系（Three-tier Memory Hierarchy）：
    1. Short-term Working Memory: 单个 ReAct 循环内的即时消息。
    2. Middle-term Task Memory: 跨步骤执行进度、已产出关键成果与滚动压缩摘要（Checkpoint 融合）。
    3. Long-term Profile Memory: 会话级与用户级通用偏好。
    """

    def __init__(self, max_working_messages: int = 12):
        self.max_working_messages = max_working_messages
        self.step_summaries: list[dict[str, str]] = []
        self.compacted_summary: str = ""

    def record_step_result(self, step: PlanStepModel, raw_output: str):
        """记录子任务的执行产物与摘要"""
        summary = step.result_summary or (
            raw_output[:300] + "..." if len(raw_output) > 300 else raw_output
        )
        self.step_summaries.append(
            {
                "step_id": str(step.id),
                "title": step.title,
                "summary": summary,
            }
        )

    def compact_memory_if_needed(self) -> str:
        """
        当步骤较多时，自动触发滑动窗口压缩（Working Memory Compaction），
        生成结构化的 context_summary 避免上下文溢出。
        """
        if len(self.step_summaries) <= 3:
            return ""

        # 压缩更早的步骤成果
        earlier_steps = self.step_summaries[:-2]
        lines = ["【历史阶段成果摘要】:"]
        for s in earlier_steps:
            lines.append(f"- 步骤 {s['step_id']} ({s['title']}): {s['summary']}")

        self.compacted_summary = "\n".join(lines)
        return self.compacted_summary

    def build_step_instruction(
        self,
        overall_goal: str,
        current_step: PlanStepModel,
        completed_steps: list[PlanStepModel],
    ) -> str:
        """
        为 ReActWorker 组装包含前置产物上下文与当前子目标的紧凑指令
        """
        prompt_parts = [
            f"【宏观总体目标】: {overall_goal}",
        ]

        if self.compacted_summary:
            prompt_parts.append(self.compacted_summary)
        elif completed_steps:
            prompt_parts.append("【前置步骤已完成成果】:")
            for s in completed_steps:
                res = s.result_summary or "已完成"
                prompt_parts.append(f"- 步骤 {s.id} ({s.title}): {res}")

        prompt_parts.append(
            f"\n【当前你要执行的单一子任务（步骤 {current_step.id}）】: {current_step.title}\n"
            f"【具体要求】: {current_step.description}\n\n"
            f"请聚焦完成本步骤的具体要求，合理调用工具完成，并在 Final Answer 中简要总结本步骤的实际产出成果。"
        )

        return "\n".join(prompt_parts)
