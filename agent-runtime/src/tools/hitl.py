from typing import Any
from .base import BaseTool, ToolResult


class HitlRequestTool(BaseTool):
    """
    人机协同 (Human-In-The-Loop) 交互工具：
    - 支持 LLM 主动向用户发起表单交互（单选、多选、文本输入、操作确认）。
    - 针对写文件、执行系统 Shell 命令、数据库删改等高危或不可逆操作，强制由人类介入审批。
    """

    @property
    def name(self) -> str:
        return "request_human_interaction"

    @property
    def description(self) -> str:
        return (
            "【人机协同与高危操作审批工具】"
            "当需要用户决策选型、收集用户偏好表单（单选/多选/文本输入），"
            "或即将执行高危、不安全、不可逆操作（如覆盖/删除重要文件、执行破坏性 Shell 脚本、修改数据库配置等）时，"
            "必须调用本工具向用户展示交互审批表单，获取用户的明确指令与授权后再继续推进。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "本次交互表单的简明标题（例如：'高危 Shell 命令执行审批' 或 '技术方案多选确认'）",
                },
                "description": {
                    "type": "string",
                    "description": "详细说明发起本次人机交互的原因、操作背景以及潜在风险详情",
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "操作风险等级。凡涉及写文件、执行 Shell 命令行等操作，必须标记为 'high' 或 'critical'",
                },
                "form_fields": {
                    "type": "array",
                    "description": "请求用户操作或填写的表单字段集合",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_id": {
                                "type": "string",
                                "description": "字段唯一 Key，如 'approval_decision', 'framework_choice', 'backup_path'",
                            },
                            "label": {
                                "type": "string",
                                "description": "字段标题显示文本",
                            },
                            "type": {
                                "type": "string",
                                "enum": ["confirm", "single_select", "multi_select", "text_input"],
                                "description": "控件类型：confirm(确认批准/拒绝), single_select(单选), multi_select(多选), text_input(文本输入)",
                            },
                            "options": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "单选或多选控件的可选条目列表，例如 ['批准并执行', '拒绝此操作', '使用备用方案']",
                            },
                            "default_value": {
                                "type": "string",
                                "description": "默认填充值",
                            },
                            "required": {
                                "type": "boolean",
                                "description": "是否为必填项",
                                "default": True,
                            },
                        },
                        "required": ["field_id", "label", "type"],
                    },
                },
            },
            "required": ["title", "description", "form_fields"],
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        title = kwargs.get("title", "人机协同交互确认")
        desc = kwargs.get("description", "")
        risk_level = kwargs.get("risk_level", "medium")
        form_fields = kwargs.get("form_fields", [])

        payload = {
            "hitl_type": "interactive_form",
            "title": title,
            "description": desc,
            "risk_level": risk_level,
            "form_fields": form_fields,
            "status": "WAITING_HUMAN_INPUT",
        }

        # 格式化为人性化的观察提示
        summary_lines = [
            f"【已成功发起人机协同请求 (HITL)】",
            f"标题: {title}",
            f"风险等级: {risk_level.upper()}",
            f"说明: {desc}",
            f"待填写表单字段: {[f.get('label') for f in form_fields]}",
            "系统已暂停等待用户在前端界面中完成填写与确认提交。",
        ]

        return ToolResult(
            output="\n".join(summary_lines),
            metadata=payload,
        )
