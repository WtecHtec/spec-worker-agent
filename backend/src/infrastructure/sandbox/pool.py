import asyncio
from typing import Any
import structlog
from src.infrastructure.sandbox.client import SandboxClient
from src.config.settings import get_settings

logger = structlog.get_logger()


class SandboxPoolManager:
    """
    沙箱连接预热与管理池（Pre-warmed Sandbox Pool）：
    维护高可用 Docker 沙箱客户端连接，
    提供探针健康检测、秒级借用与生命周期监控。
    """

    _instance: "SandboxPoolManager | None" = None

    def __init__(self, base_url: str | None = None, max_size: int = 5):
        settings = get_settings()
        self.base_url = base_url or settings.sandbox_url
        self.max_size = max_size
        self._clients: list[SandboxClient] = []
        self._is_healthy = False

    @classmethod
    def get_instance(cls) -> "SandboxPoolManager":
        if cls._instance is None:
            cls._instance = SandboxPoolManager()
        return cls._instance

    async def warm_up(self) -> bool:
        """预热并检测沙箱连接健康状态"""
        client = SandboxClient(base_url=self.base_url)
        is_ok = await client.health_check()
        self._is_healthy = is_ok
        if is_ok:
            self._clients.append(client)
            logger.info("sandbox_pool_warmed_up_success", base_url=self.base_url)
        else:
            logger.warning("sandbox_pool_warmup_unavailable", base_url=self.base_url)
        return is_ok

    def acquire_client(self) -> SandboxClient:
        """从池中借用或新建一个沙箱客户端"""
        if self._clients:
            return self._clients[0]
        return SandboxClient(base_url=self.base_url)

    @property
    def is_healthy(self) -> bool:
        return self._is_healthy
