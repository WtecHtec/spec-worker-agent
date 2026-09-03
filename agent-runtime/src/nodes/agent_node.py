import os
import asyncio
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from src.state.state import AgentState
from src.prompts.system import build_system_prompt
from src.tools.manager import user_tool_registry_manager

# 加载 .env 配置
load_dotenv()

# 1. 优先读取 LLM_* 配置，兼容 OPENAI_* 配置
base_url = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("LLM_URL")
    or os.getenv("OPENAI_BASE_URL")
    or "https://api.deepseek.com"
)
model_name = (
    os.getenv("LLM_MODEL")
    or os.getenv("OPENAI_MODEL")
    or "deepseek-chat"
)
api_key = (
    os.getenv("LLM_API_KEY")
    or os.getenv("LLM_KEY")
    or os.getenv("OPENAI_API_KEY")
    or "EMPTY"
)

llm = ChatOpenAI(
    model=model_name,
    api_key=api_key,
    base_url=base_url,
    streaming=True,
)

# 2. Redis 监听器状态
_invalidation_listener_started = False

def ensure_invalidation_listener():
    global _invalidation_listener_started
    if not _invalidation_listener_started:
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(user_tool_registry_manager.start_invalidation_listener())
            _invalidation_listener_started = True
            print("[agent-runtime] Redis tool cache invalidation listener attached successfully.")
        except RuntimeError:
            pass


async def agent_node(state: AgentState, config: RunnableConfig | None = None):
    """
    ReAct 思考与决策节点（多租户按需绑定工具）：
    - 检查首条消息是否存在 SystemMessage，若无则自动注入规范的 ReAct 思考提示词；
    - 从上下文提取当前用户 ID；
    - 纯内存极速拉取专属 ToolRegistry（含内置、沙箱与该用户专属配置的 MCP/A2A 工具）；
    - 动态通过 bind_tools 绑定至 LLM 并执行推理。
    """
    ensure_invalidation_listener()
    configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    auth_user = configurable.get("langgraph_auth_user", {})
    user_id = auth_user.get("identity") if auth_user else "local_user"

    messages = list(state.get("messages", []))

    # 注入系统提示词（保证 ReAct 准则生效）
    if not messages or not isinstance(messages[0], SystemMessage):
        system_prompt = build_system_prompt(user_id=user_id)
        messages = [SystemMessage(content=system_prompt)] + messages

    # 多租户动态获取当前用户的专属可用工具
    registry = await user_tool_registry_manager.get_registry_for_user(user_id)
    openai_tools = registry.get_openai_tools()

    bound_llm = llm.bind_tools(openai_tools) if openai_tools else llm
    response = await bound_llm.ainvoke(messages, config=config)
    return {"messages": [response]}
