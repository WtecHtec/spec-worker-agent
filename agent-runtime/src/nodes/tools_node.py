import json
from typing import Any
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from src.state.state import AgentState
from src.tools.manager import user_tool_registry_manager


def _is_high_risk_call(tool_name: str, tool_args: dict[str, Any]) -> tuple[bool, str, str, list[dict[str, Any]]]:
    """
    内置高危操作研判与拦截：
    自动识别写文件、覆盖配置、执行高危系统命令行等破坏性行为，
    构造标准化的人机协同表单（包含标题、说明、单选/确认等控件）。
    """
    if tool_name == "sandbox_run_command":
        cmd = tool_args.get("command", "")
        cmd_lower = cmd.lower()
        high_risk_keywords = ["rm ", "rmdir", "delete", "drop", "truncate", "mkfs", "dd ", ":(){", "shutdown", "reboot"]
        for kw in high_risk_keywords:
            if kw in cmd_lower:
                title = "高危命令行执行审批"
                desc = f"检测到即将执行包含敏感关键字 '{kw}' 的命令: `{cmd[:80]}`，可能对环境产生破坏性影响。"
                form_fields = [
                    {
                        "field_id": "approval",
                        "label": "操作授权确认",
                        "type": "confirm",
                        "required": True,
                    },
                    {
                        "field_id": "remark",
                        "label": "审批备注或参数修改建议",
                        "type": "text_input",
                        "required": False,
                    },
                ]
                return True, title, desc, form_fields

    if tool_name == "sandbox_write_file":
        path = tool_args.get("file_path", "")
        # 写文件一律需要人类确认，防止覆盖未备份的代码或配置
        title = f"写文件审批: {path}"
        desc = f"即将向沙箱路径 `{path}` 写入或覆盖文件内容（约 {len(tool_args.get('content', ''))} 字符）。"
        form_fields = [
            {
                "field_id": "approval",
                "label": "文件写入授权确认",
                "type": "confirm",
                "required": True,
            },
            {
                "field_id": "remark",
                "label": "审批备注",
                "type": "text_input",
                "required": False,
            },
        ]
        return True, title, desc, form_fields

    return False, "", "", []


async def tools_node(state: AgentState, config: RunnableConfig | None = None):
    """
    工具分发与执行节点（内置官方 HITL 中断审查）：
    - 针对普通安全工具：直接分发执行并返回 ToolMessage；
    - 针对 request_human_interaction 或高危操作（写文件/执行破坏性Shell）：
      调用官方 interrupt({"action_requests": [...]})，安全挂起图运行；
    - 当用户在前端完成表单填写并 resume 恢复时：
      interrupt() 函数无缝返回用户的表单决策；根据用户选择决定执行或中止。
    """
    configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    auth_user = configurable.get("langgraph_auth_user", {})
    user_id = auth_user.get("identity") if auth_user else "local_user"

    registry = await user_tool_registry_manager.get_registry_for_user(user_id)
    messages = state.get("messages", [])
    last_message = messages[-1]

    tool_messages = []
    for call in getattr(last_message, "tool_calls", []):
        tool_name = call.get("name")
        tool_args = call.get("args") or {}
        tool_id = call.get("id")

        ctx = {
            "user_id": user_id,
            "thread_id": configurable.get("thread_id"),
        }

        # 1. 检查是否为主动发起的 HITL 表单工具
        if tool_name == "request_human_interaction":
            title = tool_args.get("title", "需要您确认或提供信息")
            desc = tool_args.get("description", "")
            risk_level = tool_args.get("risk_level", "medium")
            form_fields = tool_args.get("form_fields", [])

            # 调用官方标准 interrupt，挂起图并将 action_requests 推送至前端 stream.interrupt
            hitl_payload = {
                "action_requests": [{
                    "id": tool_id,
                    "name": tool_name,
                    "title": title,
                    "description": desc,
                    "risk_level": risk_level,
                    "form_fields": form_fields,
                }]
            }
            print(f"[agent-runtime] Triggering LangGraph interrupt for tool [{tool_name}]: {title}")
            user_decision = interrupt(hitl_payload)

            # 用户 resume 恢复后继续执行，将审批结果结构化留痕入库
            decision_text = json.dumps(user_decision, ensure_ascii=False) if isinstance(user_decision, (dict, list)) else str(user_decision)
            tool_messages.append(
                ToolMessage(
                    content=f"【HITL人机协同审批记录】\n- 审批主题: {title}\n- 人类决策/表单提交: {decision_text}\n- 状态: 已确认授权并完成录入",
                    tool_call_id=tool_id,
                    name=tool_name,
                )
            )
            continue

        # 2. 检查是否命中高危安全守卫拦截（写文件、高危命令行）
        is_high_risk, hr_title, hr_desc, hr_fields = _is_high_risk_call(tool_name, tool_args)
        if is_high_risk:
            hitl_payload = {
                "action_requests": [{
                    "id": tool_id,
                    "name": tool_name,
                    "title": hr_title,
                    "description": hr_desc,
                    "risk_level": "high",
                    "form_fields": hr_fields,
                    "tool_args": tool_args,
                }]
            }
            print(f"[agent-runtime] High-risk operation intercepted! Triggering LangGraph interrupt: {hr_title}")
            user_decision = interrupt(hitl_payload)

            # 判断用户决策
            approved = True
            if isinstance(user_decision, dict):
                decision_val = user_decision.get("approval") or user_decision.get("decision") or ""
                if str(decision_val).lower() in ("reject", "refuse", "cancel", "deny", "false"):
                    approved = False
            elif str(user_decision).lower() in ("reject", "refuse", "cancel", "deny"):
                approved = False

            if not approved:
                tool_messages.append(
                    ToolMessage(
                        content=f"【HITL安全拦截审计留痕】\n- 拦截操作: {tool_name}\n- 人类审计决策: 拒绝授权（REJECTED）\n- 决策原因/补充: {user_decision}\n请分析用户拒绝原因，给出替代安全方案或向用户致歉并结束操作。",
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )
                continue

            print(f"[agent-runtime] User approved high-risk operation [{tool_name}]. Proceeding...")

        # 3. 常规分发执行
        print(f"[agent-runtime] Executing tool [{tool_name}] for user [{user_id}] with args: {tool_args}")
        result = await registry.dispatch(tool_name, tool_args, ctx)
        output_str = result.output if isinstance(result.output, str) else str(result.output)
        
        # 若是高危操作，在工具返回中显式包含人类授权审计留痕
        if is_high_risk:
            output_str = f"【HITL安全审计留痕: 人类已批准高危操作授权】\n- 授权事项: {hr_title}\n- 执行结果:\n{output_str}"

        tool_messages.append(
            ToolMessage(content=output_str, tool_call_id=tool_id, name=tool_name)
        )

    return {"messages": tool_messages}
