import hashlib
import json
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, TYPE_CHECKING
from openai import AsyncOpenAI
import structlog

from src.config.settings import get_settings, Settings
from src.infrastructure.prompts.prompt_manager import get_prompt_manager, PromptManager

if TYPE_CHECKING:
    from src.domain.services.tools.registry import ToolRegistry

logger = structlog.get_logger()


class BaseAgent(ABC):
    """
    Agent 抽象基类（模板方法模式）：
    - 统一封装 LLM 调用、消息上下文维护、Token 统计。
    - 统管通用的执行主循环 (run)、步骤事件发射、动作指纹计算与死循环拦截。
    - 子类（如 ReActAgent、PlannerAgent）仅需声明差异化配置（如系统提示词、持有工具集等）。
    """

    def __init__(
        self,
        tool_registry: Any = None,
        settings: Settings | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_steps: int | None = None,
        prompt_manager: PromptManager | None = None,
    ):
        self.settings = settings or get_settings()
        if tool_registry is None:
            from src.domain.services.tools.registry import create_default_registry
            self.tool_registry = create_default_registry()
        else:
            self.tool_registry = tool_registry
        self.prompt_manager = prompt_manager or get_prompt_manager()

        # 优先级：显式传入 > settings 配置 > 默认兜底
        self.base_url = base_url or self.settings.llm_base_url
        self.api_key = api_key or self.settings.llm_api_key or "dummy_key_for_local"
        self.model = model or self.settings.llm_model
        self.temperature = (
            temperature if temperature is not None else self.settings.llm_temperature
        )
        self.max_steps = max_steps or self.settings.llm_max_steps

        self.client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
            timeout=float(self.settings.llm_timeout),
            max_retries=self.settings.llm_max_retries,
        )

        self.messages: list[dict[str, Any]] = []
        self._action_history: list[str] = []

    @abstractmethod
    def get_system_prompt(self, ctx: dict[str, Any]) -> str:
        """子类必须实现的钩子方法：返回专属于该 Agent 角色的系统提示词"""
        ...

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """获取工具 Schema，默认从关联的 tool_registry 导出"""
        return self.tool_registry.get_openai_tools()

    def format_tools_catalog(self) -> str:
        """
        将所有已注册工具（含 MCP、A2A 动态工具）格式化为清晰的 Schema 文本，
        显式注入给 LLM 的系统提示词中，增强中小型模型（如 8B）的工具感知与参数对齐能力。
        """
        tools = self.tool_registry.list_tools()
        if not tools:
            return "暂无可用的外部工具。"

        lines = []
        for t in tools:
            param_str = json.dumps(t.parameters.get("properties", {}), ensure_ascii=False)
            required = t.parameters.get("required", [])
            lines.append(
                f"- **`{t.name}`**: {t.description}\n"
                f"  - 参数模式: `{param_str}` (必填: {required})"
            )
        return "\n".join(lines)

    def _compute_action_fingerprint(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """计算动作参数的唯一哈希特征，用于检测重复死循环"""
        canonical_json = json.dumps(arguments, sort_keys=True)
        raw = f"{tool_name}:{canonical_json}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    async def run(
        self, instruction: str, ctx: dict[str, Any]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        通用的 Agent 执行主循环（模板方法）：
        驱动 Prompt 装配 -> LLM 推理 -> 思考/工具解析 -> 执行与回填 -> 死循环拦截。
        """
        task_id = ctx.get("task_id", "unknown")
        resume_from_step = ctx.get("resume_from_step", 0)
        agent_name = self.__class__.__name__

        log = logger.bind(task_id=task_id, agent=agent_name, model=self.model)
        log.info("starting_agent_run", instruction=instruction)

        # 1. 组装 System Prompt 与初始消息（附带最近 10 条会话历史）
        system_prompt = self.get_system_prompt(ctx)
        history_messages = ctx.get("history_messages", [])
        self.messages = [{"role": "system", "content": system_prompt}]
        for hm in history_messages:
            self.messages.append({"role": hm["role"], "content": hm["content"]})
        self.messages.append({"role": "user", "content": instruction})

        step_index = resume_from_step
        tools_schema = self.get_tools_schema()
        log.info(
            "agent_tools_schema_loaded_for_llm",
            tools_count=len(tools_schema) if tools_schema else 0,
            tool_names=[t["function"]["name"] for t in tools_schema] if tools_schema else [],
        )
        loop_counter = 0

        while loop_counter < self.max_steps:
            loop_counter += 1
            log.info("agent_step_start", loop_counter=loop_counter, messages_count=len(self.messages))

            # 2. 调用 LLM API
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=self.messages,  # type: ignore
                    tools=tools_schema if tools_schema else None,
                    temperature=self.temperature,
                )
            except Exception as e:
                log.error("llm_call_failed", error=str(e))
                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "FINAL",
                    "content": {"text": f"任务执行中断：LLM API 调用失败 - {str(e)}"},
                    "wait_for_human": False,
                }
                return

            choice = response.choices[0]
            message = choice.message
            content = message.content or ""
            tool_calls = message.tool_calls or []

            # 3. 如果伴随 Tool Calls，产出推理思考（THINKING 步骤）
            if tool_calls:
                think_text = content.strip() if content.strip() else f"🧠 正在调用工具 [{tool_calls[0].function.name}] 执行具体操作..."
                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "THINKING",
                    "content": {"text": think_text},
                    "wait_for_human": False,
                }

            # 4. 如果没有 Tool Call，说明 Agent 已经得出最终结论，直接生成 FINAL 步骤
            if not tool_calls:
                log.info("agent_completed_no_tool_calls")
                final_text = content.strip() if content.strip() else "任务已完成（未生成额外文本说明）。"
                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "FINAL",
                    "content": {"text": final_text},
                    "wait_for_human": False,
                }
                return

            # 5. 处理 Tool Calls
            assistant_msg_dict: dict[str, Any] = {
                "role": "assistant",
                "content": content if content else None,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ],
            }
            self.messages.append(assistant_msg_dict)

            # 逐个执行 Tool Call
            for tool_call in tool_calls:
                tool_name = tool_call.function.name
                raw_args = tool_call.function.arguments

                try:
                    parsed_args = json.loads(raw_args) if raw_args else {}
                except Exception:
                    parsed_args = {"raw_input": raw_args}

                # 5.1 死循环严格熔断检测 (Action Fingerprinting)
                fp = self._compute_action_fingerprint(tool_name, parsed_args)
                self._action_history.append(fp)
                same_action_count = self._action_history.count(fp)

                if same_action_count >= 2:
                    log.warning("loop_detector_halted_action", tool_name=tool_name, count=same_action_count)
                    step_index += 1
                    yield {
                        "step_index": step_index,
                        "type": "FINAL",
                        "content": {
                            "text": f"系统死循环熔断保护：检测到重复调用相同参数的工具 [{tool_name}]，已自动收敛终止。"
                        },
                        "wait_for_human": False,
                    }
                    return

                # 5.2 产生 TOOL_CALL 步骤
                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "TOOL_CALL",
                    "content": {
                        "tool_name": tool_name,
                        "arguments": parsed_args,
                        "call_id": tool_call.id,
                    },
                    "wait_for_human": False,
                }

                # 5.3 分发执行工具
                start_time = time.time()
                tool_result = await self.tool_registry.dispatch(tool_name, parsed_args, ctx)
                duration_ms = int((time.time() - start_time) * 1000)

                # 5.4 产生 TOOL_RESULT 步骤
                step_index += 1
                yield {
                    "step_index": step_index,
                    "type": "TOOL_RESULT",
                    "content": {
                        "tool_name": tool_name,
                        "output": tool_result.output,
                        "is_error": tool_result.is_error,
                        "duration_ms": duration_ms,
                    },
                    "wait_for_human": False,
                }

                # 5.5 将 tool observation 回填进 messages
                tool_output_content = tool_result.output
                if same_action_count == 3:
                    tool_output_content += (
                        "\n\n【系统警报】：你已经连续 3 次使用相同参数调用该工具，请立即反思错误原因并更换全新策略，避免死循环！"
                    )

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output_content,
                    }
                )

        # 6. 超出最大步数硬熔断
        log.warning("agent_exceeded_max_steps", max_steps=self.max_steps)
        step_index += 1
        yield {
            "step_index": step_index,
            "type": "FINAL",
            "content": {
                "text": f"任务已达到最大步数限制（{self.max_steps} 步），已自动中止执行。"
            },
            "wait_for_human": False,
        }
