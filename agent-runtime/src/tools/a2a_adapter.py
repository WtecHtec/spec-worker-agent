from typing import Any
import re
import uuid
import httpx
from .base import BaseTool, ToolResult


class A2AClientWrapper:
    """Google A2A (Agent-to-Agent) 协议客户端封装"""

    def __init__(self, endpoint_url: str, headers: dict[str, str] | None = None, timeout: float = 30.0):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    async def get_agent_card(self) -> dict[str, Any] | None:
        """从远程 A2A 服务获取 AgentCard 元数据（兼容官方 SDK 与 REST 端点）"""
        try:
            # 1. 尝试使用 a2a SDK（如果环境已安装）
            try:
                from a2a.client import A2ACardResolver
                async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as hc:
                    resolver = A2ACardResolver(httpx_client=hc, base_url=self.endpoint_url)
                    card = await resolver.get_agent_card()
                    if card:
                        return {
                            "name": getattr(card, "name", "a2a_agent"),
                            "description": getattr(card, "description", ""),
                            "version": getattr(card, "version", "1.0.0"),
                            "skills": [
                                {"name": getattr(s, "name", ""), "description": getattr(s, "description", "")}
                                for s in getattr(card, "skills", [])
                            ],
                        }
            except ImportError:
                pass

            # 2. REST 回退探针：GET /.well-known/agent-card.json 或 GET /agent-card
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                for path in ["/.well-known/agent-card.json", "/agent-card", "/api/agent-card"]:
                    try:
                        resp = await client.get(f"{self.endpoint_url}{path}")
                        if resp.status_code == 200:
                            return resp.json()
                    except Exception:
                        continue
        except Exception as e:
            print(f"[agent-runtime] A2A get_agent_card failed for {self.endpoint_url}: {e}")
        return None

    async def send_task(self, message: str, context: dict[str, Any] | None = None) -> str:
        """向外部 A2A 专家发送任务并收集输出"""
        # 1. 优先尝试 a2a-sdk
        try:
            from a2a.client import create_client
            import a2a.types as a2a_types
            client = await create_client(self.endpoint_url)
            msg = a2a_types.Message(
                message_id=str(uuid.uuid4()),
                role=a2a_types.Role.ROLE_USER,
                parts=[a2a_types.Part(text=message)],
            )
            req = a2a_types.SendMessageRequest(message=msg)
            outputs = []
            async for event in client.send_message(req):
                if hasattr(event, "task") and getattr(event.task.status, "message", None):
                    for p in getattr(event.task.status.message, "parts", []):
                        if getattr(p, "text", None):
                            outputs.append(p.text)
            if outputs:
                return "\n".join(outputs)
        except ImportError:
            pass
        except Exception as e:
            print(f"[agent-runtime] A2A SDK call failed, falling back to HTTP: {e}")

        # 2. 通用 HTTP POST 协议回退
        try:
            async with httpx.AsyncClient(timeout=60.0, headers=self.headers) as client:
                payload = {
                    "message": message,
                    "context": context or {},
                    "task_id": str(uuid.uuid4()),
                }
                for endpoint in [f"{self.endpoint_url}/tasks/send", f"{self.endpoint_url}/execute", self.endpoint_url]:
                    try:
                        resp = await client.post(endpoint, json=payload)
                        if resp.status_code in (200, 201):
                            data = resp.json()
                            if isinstance(data, dict):
                                return data.get("output") or data.get("text") or data.get("result") or str(data)
                            return resp.text
                    except Exception:
                        continue
        except Exception as e:
            return f"A2A 请求异常: {str(e)}"

        return "A2A 服务未返回可用结果。"


class A2AToolAdapter(BaseTool):
    """将 A2A 远程智能体包装为 LangGraph 可调用的标准 BaseTool"""

    def __init__(self, card: dict[str, Any], client: A2AClientWrapper, namespace: str = "a2a"):
        self._card = card
        self._client = client
        raw_name = re.sub(r"[^a-zA-Z0-9_-]", "_", card.get("name", "agent")).lower().strip("_")
        self._name = f"{namespace}_{raw_name}" if namespace else raw_name

        skills = card.get("skills", [])
        skills_text = ""
        if skills:
            skills_list = [f"{s.get('name')}: {s.get('description')}" for s in skills if isinstance(s, dict) and s.get("name")]
            if skills_list:
                skills_text = f"（核心技能: {'; '.join(skills_list)}）"

        self._description = f"[Google A2A 外部专家智能体] {card.get('description', '')} {skills_text}".strip()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": f"派发给 {self._card.get('name')} 专家执行的明确任务指令与输入要求",
                }
            },
            "required": ["message"],
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        message = kwargs.get("message", "")
        output = await self._client.send_task(message=message, context=ctx)
        is_err = "错误" in output or "异常" in output
        return ToolResult(
            output=f"【A2A 外部专家 ({self._card.get('name')}) 执行结果】:\n{output}",
            is_error=is_err,
            metadata={"endpoint": self._client.endpoint_url, "agent_name": self._card.get("name")},
        )
