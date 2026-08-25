import asyncio
import json
from typing import Any
import structlog
from src.domain.services.tools.registry import ToolRegistry, create_default_registry
from src.infrastructure.db.database import AsyncSessionLocal
from src.infrastructure.db.repositories import EcosystemConfigRepository

logger = structlog.get_logger()


class UserToolRegistryManager:
    """
    用户级工具注册中心单例管理器（纯内存热缓存 + Redis 跨进程广播精准失效）：
    - 性能极致：执行时 100% 纯内存直接返回（0ms DB 开销，0 网络 IO），避免 LLM 推理循环中每次都查询数据库。
    - 跨进程强一致：当用户在前端或 API 端增删改查 MCP/A2A 服务时，通过 Redis Pub/Sub 广播失效事件，
      Worker 调度进程与其他 API 实例毫秒级收到广播并自动剔除旧缓存，保证对话与任务调度始终使用最新工具。
    """

    INVALIDATION_CHANNEL = "sys:tool_cache_invalidation"

    def __init__(self):
        self._user_registries: dict[str, ToolRegistry] = {}
        self._listener_task: asyncio.Task | None = None

    async def get_registry_for_user(self, user_id: str, force_reload: bool = False) -> ToolRegistry:
        """
        获取指定用户的 ToolRegistry（优先纯内存秒级命中，零 DB 查询）
        """
        # 1. 内存热缓存直接命中（0ms，不查数据库）
        if not force_reload and user_id in self._user_registries:
            logger.debug("user_tool_registry_memory_cache_hit", user_id=user_id)
            return self._user_registries[user_id]

        # 2. 缓存未命中或被主动失效：从数据库读取配置并进行工具挂载（仅执行一次）
        logger.info(
            "user_tool_registry_warming_up_from_db",
            user_id=user_id,
            reason="cold_start" if user_id not in self._user_registries else "force_reload_or_invalidated",
        )
        registry = create_default_registry()

        try:
            async with AsyncSessionLocal() as db:
                repo = EcosystemConfigRepository(db)
                configs = await repo.list_by_user(user_id)

                for cfg in configs:
                    if not cfg.enabled:
                        continue
                    try:
                        if cfg.type == "mcp":
                            if cfg.transport == "stdio" and cfg.command:
                                await registry.register_mcp_server(
                                    command=cfg.command,
                                    args=cfg.args,
                                    transport="stdio",
                                    namespace=cfg.namespace,
                                )
                            elif cfg.server_url:
                                # 支持 sse / streamable_http 模式
                                await registry.register_mcp_server(
                                    server_url=cfg.server_url,
                                    transport=cfg.transport,  # "sse" 或 "streamable_http"
                                    namespace=cfg.namespace,
                                )
                        elif cfg.type == "a2a" and cfg.server_url:
                            await registry.register_a2a_server(
                                endpoint_url=cfg.server_url,
                                namespace=cfg.namespace,
                            )
                    except Exception as e:
                        logger.warning(
                            "failed_mounting_user_ecosystem_config",
                            user_id=user_id,
                            config_name=cfg.name,
                            error=str(e),
                        )
        except Exception as e:
            logger.error("error_loading_user_ecosystem_configs", user_id=user_id, error=str(e))

        # 3. 存入内存单例缓存
        self._user_registries[user_id] = registry
        logger.info(
            "user_tool_registry_warmed_up_successfully",
            user_id=user_id,
            total_tools=len(registry.list_tools()),
            tool_names=[t.name for t in registry.list_tools()],
        )
        return registry

    def invalidate_cache(self, user_id: str) -> None:
        """本地内存缓存失效"""
        if user_id in self._user_registries:
            del self._user_registries[user_id]
            logger.info("user_tool_registry_local_cache_invalidated", user_id=user_id)

    async def broadcast_invalidation(self, user_id: str) -> None:
        """
        跨进程广播缓存失效：
        1. 立即清除本进程本地内存缓存；
        2. 向 Redis 广播失效事件，使所有 Worker 和 API 进程同步失效。
        """
        self.invalidate_cache(user_id)
        try:
            from src.infrastructure.redis.client import get_redis
            redis = await get_redis()
            payload = json.dumps({"user_id": user_id, "action": "invalidate_tool_cache"})
            await redis.publish(self.INVALIDATION_CHANNEL, payload)
            logger.info("tool_cache_invalidation_broadcasted_to_redis", user_id=user_id)
        except Exception as e:
            logger.warning("broadcast_tool_cache_invalidation_failed", user_id=user_id, error=str(e))

    async def start_invalidation_listener(self) -> None:
        """
        常驻后台协程：订阅 Redis 广播，接收跨进程缓存失效消息
        """
        from src.infrastructure.redis.client import get_redis
        logger.info("starting_tool_cache_invalidation_listener", channel=self.INVALIDATION_CHANNEL)
        try:
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(self.INVALIDATION_CHANNEL)

            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    try:
                        raw_data = msg.get("data")
                        if raw_data:
                            data = json.loads(raw_data)
                            target_user = data.get("user_id")
                            if target_user:
                                self.invalidate_cache(target_user)
                                logger.info(
                                    "tool_cache_invalidated_by_redis_broadcast",
                                    user_id=target_user,
                                )
                    except Exception as parse_err:
                        logger.warning("error_parsing_invalidation_broadcast", error=str(parse_err))
        except asyncio.CancelledError:
            logger.info("tool_cache_invalidation_listener_cancelled")
        except Exception as e:
            logger.error("tool_cache_invalidation_listener_failed", error=str(e))


# 全局单例
user_tool_registry_manager = UserToolRegistryManager()
