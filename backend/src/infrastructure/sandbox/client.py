from typing import Any
import httpx
import structlog
from src.config.settings import get_settings

logger = structlog.get_logger()


class SandboxClient:
    """
    异步 Sandbox HTTP 客户端：
    负责与独立的 Go Sandbox Daemon（Docker 容器）进行通信。
    """

    def __init__(self, base_url: str | None = None, timeout: float = 60.0):
        settings = get_settings()
        self.base_url = (base_url or settings.sandbox_url).rstrip("/")
        self.timeout = timeout

    async def health_check(self) -> bool:
        """检查沙箱容器是否健康在线"""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/health")
                return res.status_code == 200
        except Exception as e:
            logger.debug("sandbox_health_check_failed", error=str(e))
            return False

    async def execute_command(
        self,
        command: str,
        cwd: str = "",
        timeout: int = 60,
        exec_id: str | None = None,
    ) -> dict[str, Any]:
        """
        在沙箱容器中执行 Bash 命令
        """
        payload: dict[str, Any] = {
            "command": command,
            "cwd": cwd,
            "timeout": timeout,
        }
        if exec_id:
            payload["exec_id"] = exec_id

        async with httpx.AsyncClient(timeout=float(timeout + 5)) as client:
            res = await client.post(f"{self.base_url}/exec", json=payload)
            if res.status_code != 200:
                return {
                    "is_error": True,
                    "exit_code": -1,
                    "combined": f"沙箱请求异常 ({res.status_code}): {res.text}",
                    "output": f"沙箱请求异常 ({res.status_code}): {res.text}",
                }
            data = res.json()
            data["output"] = data.get("combined") or data.get("stdout") or ""
            return data

    async def kill_execution(self, exec_id: str) -> bool:
        """发送强杀信号终止正在执行的沙箱命令"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(
                    f"{self.base_url}/exec/kill", json={"exec_id": exec_id}
                )
                return res.status_code == 200
        except Exception as e:
            logger.error("sandbox_kill_failed", exec_id=exec_id, error=str(e))
            return False

    async def read_file(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        """从沙箱容器读取文件"""
        payload: dict[str, Any] = {"file_path": file_path}
        if start_line is not None:
            payload["start_line"] = start_line
        if end_line is not None:
            payload["end_line"] = end_line

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/fs/read", json=payload)
            if res.status_code != 200:
                return {
                    "is_error": True,
                    "content": f"读取沙箱文件失败 ({res.status_code}): {res.text}",
                }
            return res.json()

    async def write_file(self, file_path: str, content: str) -> dict[str, Any]:
        """将内容写入沙箱容器"""
        payload = {
            "file_path": file_path,
            "content": content,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/fs/write", json=payload)
            if res.status_code != 200:
                return {
                    "is_error": True,
                    "message": f"写入沙箱文件失败 ({res.status_code}): {res.text}",
                }
            return res.json()

    async def list_files(self, dir_path: str = "") -> dict[str, Any]:
        """列出沙箱工作区目录文件"""
        payload = {"dir_path": dir_path}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/fs/list", json=payload)
            return res.json() if res.status_code == 200 else {"files": [], "error": res.text}


_default_client: SandboxClient | None = None


def get_sandbox_client() -> SandboxClient:
    global _default_client
    if _default_client is None:
        _default_client = SandboxClient()
    return _default_client
