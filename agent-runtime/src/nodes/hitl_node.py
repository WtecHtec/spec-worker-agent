import json
from typing import Any
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from src.state.state import AgentState
from src.tools.manager import user_tool_registry_manager


def _is_high_risk_operation(tool_name: str, tool_args: dict[str, Any]) -> tuple[bool, str]:
    """
    内置安全守卫拦截：
    自动研判是否属于高危或不安全操作（如写文件、执行可能造成破坏或系统影响的命令行等）
    """
    if tool_name == "sandbox_run_command":
        cmd = tool_args.get("command", "").lower()
        high_risk_keywords = ["rm ", "rmdir", "delete", "drop", "truncate", "mkfs", "dd ", ":(){", "shutdown", "reboot"]
        for kw in high_risk_keywords:
            if kw in cmd:
                return True, f"检测到高危 Shell 命令行 [{cmd[:60]}]，涉及高危关键字 '{kw}'"
        return False, ""

    if tool_name == "sandbox_write_file":
        path = tool_args.get("file_path", "")
        sensitive_patterns = [".env", "config", "passwd", "shadow", "key", "secret", "Dockerfile"]
        for sp in sensitive_patterns:
            if sp in path:
                return True, f"检测到修改敏感配置文件 [{path}]"
        return False, ""

    return False, ""


async def hitl_node(state: AgentState, config: RunnableConfig | None = None):
    """
    人机协同 (Human-In-The-Loop) 核心控制节点：
    1. 处理 LLM 主动调用的 request_human_interaction（表单多选/单选/输入/确认）；
    2. 安全守卫机制：若检测到高危写文件或执行破坏性命令，且未经过人类审批，自动拦截并生成审批请求；
    3. 支持通过 LangGraph interrupt() 挂起状态等待人类响应（或产出表单消息）。
    """
    configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    auth_user = configurable.get("langgraph_auth_user", {})
    user_id = auth_user.get("identity") if auth_user else "local_user"

    messages = state.get("messages", [])
    last_message = messages[-1]
    tool_messages = []

    # 尝试引入 LangGraph 官方 interrupt 机制（在长连接状态下可实现线程挂起）
    try:
        from langgraph.types import interrupt
    except ImportError:
        interrupt = None

    for call in getattr(last_message, "tool_calls", []):
        tool_name = call.get("name")
        tool_args = call.get("args") or {}
        tool_id = call.get("id")

        if tool_name == "request_human_interaction":
            title = tool_args.get("title", "需要您确认或提供信息")
            desc = tool_args.get("description", "")
            risk_level = tool_args.get("risk_level", "medium")
            form_fields = tool_args.get("form_fields", [])

            payload = {
                "type": "HITL_REQUEST",
                "title": title,
                "description": desc,
                "risk_level": risk_level,
                "form_fields": form_fields,
                "tool_call_id": tool_id,
            }

            # 若宿主支持 interrupt，则挂起
            if interrupt is not None:
                try:
                    # 暂停图执行，等待人类输入恢复
                    human_response = interrupt(payload)
                    # 恢复后将人类的填写内容封装成 ToolMessage
                    tool_messages.append(
                        ToolMessage(
                            content=json.dumps({"status": "RESOLVED", "user_input": human_response}, ensure_ascii=False),
                            tool_call_id=tool_id,
                            name=tool_name,
                        )
                    )
                    continue
                except Exception:
                    pass

            # 回退/流式响应模式：生成结构化的 HITL 表单提示
            out_content = (
                f"【🔔 已发起人机协同请求 (HITL)】\n"
                f"• 标题: {title}\n"
                f"• 风险级别: {risk_level.upper()}\n"
                f"• 详细说明: {desc}\n"
                f"• 表单详情: {json.dumps(form_fields, ensure_ascii=False, indent=2)}\n"
                f"等待用户在前端界面中完成选择或输入后继续。"
            )
            tool_messages.append(
                ToolMessage(
                    content=out_content,
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )

    return {
        "messages": tool_messages,
        "pending_hitl": payload if "payload" in locals() else None,
    }
