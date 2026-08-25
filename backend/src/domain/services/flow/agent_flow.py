from typing import Any, AsyncGenerator
import structlog
from src.domain.services.agents.planner import PlannerAgent, PlanModel, PlanStepModel
from src.domain.services.agents.react import ReActAgent
from src.domain.services.memory.memory_manager import MemoryManager
from src.domain.services.memory.episodic_memory import EpisodicMemoryManager
from src.domain.services.tools.registry import ToolRegistry, create_default_registry

logger = structlog.get_logger()


class PlanAndExecuteFlow:
    """
    Agent Flow 编排管道（Plan-and-Execute Paradigm）：
    负责连接 PlannerAgent（宏观规划大脑）与 ReActAgent（局部执行小脑），
    管理计划生命周期、分层记忆传递、子任务步进、动态重规划反思与经验沉淀。
    """

    def __init__(
        self,
        planner: PlannerAgent | None = None,
        tool_registry: ToolRegistry | None = None,
        max_replans: int = 3,
    ):
        self.tool_registry = tool_registry or create_default_registry()
        self.planner = planner or PlannerAgent(tool_registry=self.tool_registry)
        self.memory_manager = MemoryManager()
        self.episodic_memory = EpisodicMemoryManager()
        self.max_replans = max_replans

    async def run(
        self, instruction: str, ctx: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        task_id = ctx.get("task_id", "unknown")
        log = logger.bind(task_id=task_id, flow="PlanAndExecuteFlow")
        log.info("starting_plan_and_execute_flow", instruction=instruction)

        step_index = ctx.get("resume_from_step", 0)

        # ── 1. Planner 规划阶段 ──
        plan: PlanModel = await self.planner.create_plan(instruction, ctx)
        log.info("initial_plan_created", steps_count=len(plan.steps))

        # 产出深度思考分析内容（由 Planner LLM 生成的真实分析推理）
        think_text = plan.analysis or f"已深入分析任务目标：{instruction}，正在按最优路径分解执行步骤。"
        step_index += 1
        yield {
            "step_index": step_index,
            "type": "THINKING",
            "content": {"text": f"💡 【任务剖析与解题思路】\n{think_text}"},
            "wait_for_human": False,
        }

        # 产出计划生成事件
        step_index += 1
        plan_dict = plan.model_dump()
        yield {
            "step_index": step_index,
            "type": "PLAN_GENERATED",
            "content": plan_dict,
            "wait_for_human": False,
        }

        # ── 2. 执行与重规划循环 ──
        completed_steps: list[PlanStepModel] = []
        replan_count = 0

        i = 0
        while i < len(plan.steps):
            current_step = plan.steps[i]
            current_step.status = "in_progress"

            # 2.1 同步更新计划状态（步骤进行中）
            step_index += 1
            yield {
                "step_index": step_index,
                "type": "PLAN_UPDATED",
                "content": plan.model_dump(),
                "wait_for_human": False,
            }

            # 2.2 组装子任务指令与记忆上下文
            self.memory_manager.compact_memory_if_needed()
            sub_instruction = self.memory_manager.build_step_instruction(
                instruction, current_step, completed_steps
            )

            # 2.3 派发给 ReActAgent 攻坚
            worker = ReActAgent(tool_registry=self.tool_registry)
            sub_final_text = ""
            has_error = False
            last_tool_is_error = False
            has_success_tool = False

            sub_ctx = dict(ctx)
            sub_ctx["resume_from_step"] = step_index

            async for event in worker.run(sub_instruction, sub_ctx):
                event_type = event.get("type")
                step_index = event["step_index"]

                if event_type == "TOOL_RESULT":
                    if event["content"].get("is_error"):
                        last_tool_is_error = True
                    else:
                        has_success_tool = True
                        last_tool_is_error = False
                    yield event
                elif event_type == "FINAL":
                    sub_final_text = event["content"].get("text", "")
                    # 仅在系统安全熔断、显式中断或全部工具调用失败且无有效结果时判定为执行阻碍
                    if (
                        "系统安全熔断" in sub_final_text
                        or "任务执行中断" in sub_final_text
                        or (last_tool_is_error and not has_success_tool and len(sub_final_text.strip()) < 30)
                    ):
                        has_error = True
                else:
                    # 向上透传 THINKING, TOOL_CALL 等即时过程
                    yield event

            # 2.4 评估子任务执行结果与动态重规划
            if has_error and replan_count < self.max_replans:
                replan_count += 1
                log.warning("step_failed_triggering_replan", step_id=current_step.id, replan_count=replan_count)

                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "THINKING",
                    "content": {
                        "text": f"步骤 {current_step.id} 执行受阻，Planner 正在评估并动态重规划后续步骤（第 {replan_count} 次）..."
                    },
                    "wait_for_human": False,
                }

                # 动态重规划
                new_plan = await self.planner.replan(
                    instruction, plan, current_step.id, sub_final_text, ctx
                )
                plan = new_plan

                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "PLAN_UPDATED",
                    "content": plan.model_dump(),
                    "wait_for_human": False,
                }

                # 重新定位到未完成步骤
                remaining = [s for s in plan.steps if s.status == "pending"]
                if remaining:
                    i = plan.steps.index(remaining[0])
                    continue
                else:
                    break

            # 2.5 步骤顺利完成，更新状态并产出最新的计划更新事件
            current_step.status = "completed"
            current_step.result_summary = sub_final_text or "已顺利完成"
            self.memory_manager.record_step_result(current_step, sub_final_text)
            completed_steps.append(current_step)

            step_index += 1
            yield {
                "step_index": step_index,
                "type": "PLAN_UPDATED",
                "content": plan.model_dump(),
                "wait_for_human": False,
            }
            i += 1

            # 全局最大步数防失控硬熔断
            if step_index >= 20:
                log.warning("flow_exceeded_global_step_limit", step_index=step_index)
                break

        # ── 3. 全局总结收敛与经验沉淀 ──
        log.info("plan_and_execute_flow_finished", total_completed=len(completed_steps))
        step_index += 1

        # 若为单步简单任务，直接以子步骤产出为最终回复
        if len(plan.steps) == 1 and completed_steps:
            final_output = completed_steps[0].result_summary or "任务已完成。"
        else:
            summary_parts = [
                f"### 🎉 任务已全部规划并执行完成！\n",
                f"**任务目标**：{instruction}\n",
                f"**规划步骤执行汇总**：",
            ]
            for s in completed_steps:
                summary_parts.append(f"- ✅ **步骤 {s.id} ({s.title})**：{s.result_summary}")

            if replan_count > 0:
                summary_parts.append(f"\n*(本次任务执行过程中自适应触发了 {replan_count} 次动态重规划)*")
            final_output = "\n".join(summary_parts)

        # 沉淀至 Episodic Memory
        self.episodic_memory.reflect_and_store(
            task_id=task_id,
            goal=instruction,
            steps_summary=[s.model_dump() for s in completed_steps],
            final_text=final_output,
            success=True,
        )

        yield {
            "step_index": step_index,
            "type": "FINAL",
            "content": {"text": final_output},
            "wait_for_human": False,
        }
