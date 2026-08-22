import json
import re
from typing import Any, Literal
from pydantic import BaseModel, Field
import structlog
from .base import BaseAgent

logger = structlog.get_logger()


class PlanStepModel(BaseModel):
    id: int = Field(description="步骤序号（1-based 连续递增）")
    title: str = Field(description="步骤简要标题")
    description: str = Field(description="步骤详细执行要求与产出目标")
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = Field(
        default="pending", description="步骤执行状态"
    )
    result_summary: str | None = Field(default=None, description="步骤执行完成后的核心成果摘要")


class PlanModel(BaseModel):
    analysis: str | None = Field(default=None, description="Planner 对任务目标的思考分析")
    goal: str = Field(description="任务总体目标")
    steps: list[PlanStepModel] = Field(description="子任务步骤列表")
    current_step_id: int = Field(default=1, description="当前待执行的步骤 ID")
    is_replan: bool = Field(default=False, description="是否为动态重规划生成的计划")


def _extract_json_from_llm_response(text: str) -> dict[str, Any]:
    """从 LLM 返回文本中安全提取 JSON 块（支持带 markdown ```json 格式）"""
    cleaned = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if match:
        cleaned = match.group(1).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试寻找最外层大括号
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


class PlannerAgent(BaseAgent):
    """
    独立规划 Agent（Planner Paradigm）：
    负责任务目标分析、步骤拆解与动态重规划（Re-planning）。
    """

    def get_system_prompt(self, ctx: dict[str, Any]) -> str:
        return self.prompt_manager.render(
            "system/planner.md",
            workspace_dir=ctx.get("workspace_dir", self.settings.llm_workspace_dir),
            tools_description=self.format_tools_catalog(),
        )

    def get_tools_schema(self) -> list[dict[str, Any]]:
        # Planner 为纯规划思考的大脑，不直接调用沙箱工具
        return []

    async def create_plan(self, goal: str, ctx: dict[str, Any]) -> PlanModel:
        """
        根据用户宏观目标生成初始结构化计划
        """
        system_prompt = self.get_system_prompt(ctx)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"请为以下任务目标制定详细的执行计划（输出标准 JSON 格式）：\n\n【任务目标】：{goal}",
            },
        ]

        logger.info("planner_generating_initial_plan", goal=goal)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore
            temperature=0.3,
        )

        raw_text = response.choices[0].message.content or "{}"
        try:
            plan_dict = _extract_json_from_llm_response(raw_text)
            plan = PlanModel.model_validate(plan_dict)
            plan.is_replan = False
            return plan
        except Exception as e:
            logger.warning("planner_json_parse_fallback", error=str(e), raw=raw_text)
            # 优雅降级构建单步计划
            return PlanModel(
                goal=goal,
                steps=[
                    PlanStepModel(
                        id=1,
                        title="执行任务核心目标",
                        description=goal,
                        status="pending",
                    )
                ],
                current_step_id=1,
                is_replan=False,
            )

    async def replan(
        self,
        goal: str,
        current_plan: PlanModel,
        failed_step_id: int,
        reason: str,
        ctx: dict[str, Any],
    ) -> PlanModel:
        """
        当子任务失败或遇到阻碍时，评估当前进展并动态重规划后续步骤
        """
        system_prompt = self.get_system_prompt(ctx)
        plan_summary = json.dumps(current_plan.model_dump(), ensure_ascii=False, indent=2)

        prompt = (
            f"原任务目标：{goal}\n\n"
            f"当前执行进度计划：\n{plan_summary}\n\n"
            f"【遇到问题】：步骤 {failed_step_id} 执行遇到错误/阻碍：\n{reason}\n\n"
            f"请根据最新情况，重新评估并调整后续未完成的计划步骤（输出更新后的标准 JSON 格式，保留已完成步骤的状态）："
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        logger.info("planner_executing_replan", goal=goal, failed_step_id=failed_step_id)
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,  # type: ignore
            temperature=0.3,
        )

        raw_text = response.choices[0].message.content or "{}"
        try:
            plan_dict = _extract_json_from_llm_response(raw_text)
            updated_plan = PlanModel.model_validate(plan_dict)
            updated_plan.is_replan = True
            return updated_plan
        except Exception as e:
            logger.warning("replan_parse_failed_retaining_existing", error=str(e))
            # 重规划解析失败时，标记失败步骤并尝试推进
            for s in current_plan.steps:
                if s.id == failed_step_id:
                    s.status = "failed"
                    s.result_summary = f"执行受阻: {reason[:100]}"
            current_plan.is_replan = True
            return current_plan
