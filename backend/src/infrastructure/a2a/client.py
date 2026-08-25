from typing import Any
import uuid
import httpx
import structlog
import a2a.types as a2a_types
from a2a.client import A2ACardResolver, create_client, Client as A2AClient

logger = structlog.get_logger()

# 显式导出官方客户端类
__all__ = ["A2ACardResolver", "A2AClient", "A2AClientWrapper"]


class A2AClientWrapper:
    """
    Google A2A (Agent-to-Agent) 官方 SDK 客户端封装：
    基于官方 `from a2a.client import A2ACardResolver, create_client, Client as A2AClient` 实现，
    负责远程智能体 AgentCard 解析与基于官方协议标准的任务委派交互。
    """

    def __init__(
        self,
        endpoint_url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self._client: A2AClient | None = None

    async def get_agent_card(self) -> a2a_types.AgentCard | None:
        """
        使用官方 A2ACardResolver 获取远程 A2A 服务的 AgentCard 元数据
        """
        log = logger.bind(endpoint=self.endpoint_url)
        log.info("a2a_resolving_agent_card_via_sdk")
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as hc:
                resolver = A2ACardResolver(httpx_client=hc, base_url=self.endpoint_url)
                card = await resolver.get_agent_card()
                return card
        except Exception as e:
            log.warning("a2a_resolve_agent_card_failed", error=str(e))
        return None

    async def _ensure_client(self) -> A2AClient:
        if self._client is None:
            self._client = await create_client(self.endpoint_url)
        return self._client

    async def send_task(self, message: str, context: dict[str, Any] | None = None) -> str:
        """
        使用官方 A2AClient 发送结构化任务消息并收集响应
        """
        log = logger.bind(endpoint=self.endpoint_url)
        log.info("a2a_sending_task_via_sdk", message_preview=message[:60])

        try:
            client = await self._ensure_client()
            msg = a2a_types.Message(
                message_id=str(uuid.uuid4()),
                role=a2a_types.Role.ROLE_USER,
                parts=[a2a_types.Part(text=message)],
            )
            req = a2a_types.SendMessageRequest(message=msg)

            output_texts = []
            async for event in client.send_message(req):
                if event.HasField("task") and event.task.status.message:
                    for part in event.task.status.message.parts:
                        if part.text:
                            output_texts.append(part.text)
                elif event.HasField("message"):
                    for part in event.message.parts:
                        if part.text:
                            output_texts.append(part.text)

            if output_texts:
                return "\n".join(output_texts)
            return "【Google A2A 任务执行完成（无文本输出）】"
        except Exception as e:
            log.error("a2a_send_task_sdk_failed", error=str(e))
            return f"A2A 远程服务调用异常: {str(e)}"
