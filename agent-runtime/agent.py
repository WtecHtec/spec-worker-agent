import os
from typing import Annotated
from typing_extensions import TypedDict
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

# 加载 .env 配置
load_dotenv()

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

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
    or ""
)

# 2. 数据库与 Redis 配置读取（支持外部容器网络与本地）
database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL", "")
redis_url = os.getenv("REDIS_URL", "")

print(f"[agent-runtime] Initializing with BaseURL: {base_url}, Model: {model_name}")
if database_url:
    print(f"[agent-runtime] PostgreSQL configured: {database_url.split('@')[-1]}")
if redis_url:
    print(f"[agent-runtime] Redis configured: {redis_url.split('@')[-1]}")

# 3. 初始化 LLM Client
llm = ChatOpenAI(
    model=model_name,
    api_key=api_key,
    base_url=base_url,
    streaming=True,
)

from langchain_core.runnables import RunnableConfig

async def llm_node(state: AgentState, config: RunnableConfig | None = None):
    """P0 单节点：直接调用模型，支持原生异步流式输出与取消中断"""
    configurable = (config or {}).get("configurable", {}) if isinstance(config, dict) else {}
    auth_user = configurable.get("langgraph_auth_user", {})
    if auth_user:
        print(f"[agent-runtime] Executing for user: {auth_user.get('identity')}")
    
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}

# 4. 构建图
builder = StateGraph(AgentState)
builder.add_node("llm_node", llm_node)
builder.add_edge(START, "llm_node")
builder.add_edge("llm_node", END)

# 5. Checkpointer（如果配置了 PostgreSQL，可挂载 PostgresSaver）
checkpointer = None
if database_url and database_url.startswith("postgres"):
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
        # 预留可插拔 checkpointer
    except Exception as e:
        print(f"[agent-runtime] Postgres checkpointer optional init notice: {e}")

graph = builder.compile(checkpointer=checkpointer)
