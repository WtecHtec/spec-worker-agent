import os
import json
import asyncio
from typing import Any
import psycopg
import redis.asyncio as aioredis
from .registry import ToolRegistry, create_default_registry


class UserToolRegistryManager:
    """
    多租户工具注册中心管理器（agent-runtime 内置独立运行）：
    - 内存热缓存（零数据库/网络 IO 开销）：用户多次对话时复用纯内存中的 ToolRegistry。
    - 跨进程精准热失效：订阅 Redis 广播 'sys:tool_cache_invalidation'。
      当用户在前端增删改查 MCP/A2A 时，毫秒级收到广播并剔除该用户的缓存，下一次提问直接拉取最新配置。
    - 完全内聚独立：不依赖 backend 目录，自包含运行。
    """

    INVALIDATION_CHANNEL = "sys:tool_cache_invalidation"

    def __init__(self):
        self._user_registries: dict[str, ToolRegistry] = {}
        self._listener_task: asyncio.Task | None = None
        self._db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/app").replace("+asyncpg", "")
        self._redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    async def get_registry_for_user(self, user_id: str, force_reload: bool = False) -> ToolRegistry:
        """获取当前用户可用的 ToolRegistry（优先纯内存秒级命中）"""
        if not force_reload and user_id in self._user_registries:
            return self._user_registries[user_id]

        print(f"[agent-runtime] Warming up ToolRegistry for user [{user_id}] from database...")
        registry = create_default_registry()

        # 从数据库加载该用户已启用的生态配置 (MCP)
        try:
            async with await psycopg.AsyncConnection.connect(self._db_url) as conn:
                async with conn.cursor() as cur:
                    query = """
                        SELECT type, name, transport, server_url, command, args, namespace, enabled
                        FROM ecosystem_configs
                        WHERE user_id = %s AND enabled = TRUE
                        ORDER BY created_at DESC
                    """
                    await cur.execute(query, (user_id,))
                    rows = await cur.fetchall()

                    for r in rows:
                        cfg_type, name, transport, server_url, command, args, namespace, enabled = r
                        if not enabled:
                            continue
                        try:
                            if cfg_type == "mcp":
                                parsed_args = args if isinstance(args, list) else (json.loads(args) if args else [])
                                if transport == "stdio" and command:
                                    await registry.register_mcp_server(
                                        command=command,
                                        args=parsed_args,
                                        transport="stdio",
                                        namespace=namespace,
                                    )
                                elif server_url:
                                    await registry.register_mcp_server(
                                        server_url=server_url,
                                        transport=transport,
                                        namespace=namespace,
                                    )
                            elif cfg_type == "a2a" and server_url:
                                await registry.register_a2a_server(
                                    endpoint_url=server_url,
                                    namespace=namespace,
                                )
                        except Exception as mcp_err:
                            print(f"[agent-runtime] Failed to mount ecosystem config [{name}] for user [{user_id}]: {mcp_err}")
        except Exception as db_err:
            print(f"[agent-runtime] Database connection notice while loading tools for user [{user_id}]: {db_err}")

        # 写入用户内存热缓存
        self._user_registries[user_id] = registry
        tools = registry.list_tools()
        print(f"[agent-runtime] User [{user_id}] ToolRegistry loaded with {len(tools)} tools: {[t.name for t in tools]}")
        return registry

    def invalidate_cache(self, user_id: str) -> None:
        """从本地内存中剔除指定用户的 ToolRegistry 缓存"""
        if user_id in self._user_registries:
            del self._user_registries[user_id]
            print(f"[agent-runtime] Local ToolRegistry cache invalidated for user [{user_id}]")

    async def start_invalidation_listener(self) -> None:
        """常驻协程：监听 Redis 跨进程工具失效广播，实现零延迟定向热失效"""
        print(f"[agent-runtime] Starting Redis tool cache invalidation listener on channel [{self.INVALIDATION_CHANNEL}]...")
        try:
            client = aioredis.from_url(self._redis_url)
            pubsub = client.pubsub()
            await pubsub.subscribe(self.INVALIDATION_CHANNEL)

            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    try:
                        raw_data = msg.get("data")
                        if raw_data:
                            data = json.loads(raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data)
                            target_user = data.get("user_id")
                            if target_user:
                                self.invalidate_cache(target_user)
                    except Exception as parse_err:
                        print(f"[agent-runtime] Error parsing invalidation broadcast: {parse_err}")
        except asyncio.CancelledError:
            print("[agent-runtime] Invalidation listener cancelled.")
        except Exception as e:
            print(f"[agent-runtime] Invalidation listener encountered error: {e}")


# 运行时单例
user_tool_registry_manager = UserToolRegistryManager()
