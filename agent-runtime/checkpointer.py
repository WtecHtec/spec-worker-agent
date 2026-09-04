"""
LangGraph Checkpointer 工厂模块：
支持通过环境变量 POSTGRES_URI 动态在 PostgreSQL 持久化与内存模式之间无缝切换。
- 当 POSTGRES_URI 存在且以 postgres 开头时：直连 PostgreSQL，自动对齐表结构并持久化快照。
- 当未配置 POSTGRES_URI 或留空时：平滑回退到 InMemorySaver，适用于纯本地离线单测与轻量调试。
"""

import os
import logging
from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger("langgraph_checkpointer")


@asynccontextmanager
async def get_checkpointer():
    postgres_uri = os.getenv("POSTGRES_URI", "").strip()

    if postgres_uri.startswith("postgres"):
        logger.info("Connecting to PostgreSQL checkpointer: %s", postgres_uri.split("@")[-1])
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(postgres_uri) as checkpointer:
            # 自动创建或迁移 checkpoints / checkpoint_blobs / checkpoint_writes 表
            await checkpointer.setup()
            yield checkpointer
    else:
        logger.info("POSTGRES_URI not configured. Using in-memory checkpointer (InMemorySaver).")
        yield MemorySaver()
