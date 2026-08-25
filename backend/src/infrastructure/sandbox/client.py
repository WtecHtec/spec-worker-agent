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

    # ─── CDP Browser Automation APIs ───

    async def browser_open(
        self,
        url: str,
        session_id: str = "default",
        timeout_sec: int = 30,
    ) -> dict[str, Any]:
        """打开指定 URL 网页"""
        payload = {"url": url, "session_id": session_id, "timeout_sec": timeout_sec}
        async with httpx.AsyncClient(timeout=float(timeout_sec + 5)) as client:
            res = await client.post(f"{self.base_url}/tools/browser/open", json=payload)
            if res.status_code != 200:
                return {"success": False, "error": f"打开网页失败 ({res.status_code}): {res.text}"}
            return res.json()

    async def browser_close(self, session_id: str = "default") -> dict[str, Any]:
        """关闭网页并销毁会话资源"""
        payload = {"session_id": session_id}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/tools/browser/close", json=payload)
            if res.status_code != 200:
                return {"success": False, "error": f"关闭网页失败 ({res.status_code}): {res.text}"}
            return res.json()

    async def browser_get_snapshot(
        self,
        session_id: str = "default",
        include_screenshot: bool = False,
    ) -> dict[str, Any]:
        """获取当前视口已编号结构与页面快照"""
        payload = {"session_id": session_id, "include_screenshot": include_screenshot}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/tools/browser/snapshot", json=payload)
            if res.status_code != 200:
                return {"success": False, "error": f"获取快照失败 ({res.status_code}): {res.text}"}
            return res.json()

    async def browser_click(
        self,
        element_id: int,
        session_id: str = "default",
    ) -> dict[str, Any]:
        """根据已分配的编号点击元素"""
        payload = {"element_id": element_id, "session_id": session_id}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/tools/browser/click", json=payload)
            if res.status_code != 200:
                return {"success": False, "error": f"点击元素失败 ({res.status_code}): {res.text}"}
            return res.json()

    async def browser_screenshot(
        self,
        full_page: bool = False,
        save_path: str | None = None,
        session_id: str = "default",
    ) -> dict[str, Any]:
        """获取页面截图并落地保存到沙箱工作区"""
        payload: dict[str, Any] = {"full_page": full_page, "session_id": session_id}
        if save_path:
            payload["save_path"] = save_path

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/tools/browser/screenshot", json=payload)
            if res.status_code != 200:
                return {"success": False, "error": f"截图失败 ({res.status_code}): {res.text}"}
            return res.json()

    async def browser_execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        session_id: str = "default",
    ) -> dict[str, Any]:
        """通用浏览器工具分发入口"""
        payload = {
            "tool_name": tool_name,
            "arguments": arguments,
            "session_id": session_id,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            res = await client.post(f"{self.base_url}/tools/browser/execute", json=payload)
            if res.status_code != 200:
                return {"success": False, "error": f"执行工具失败 ({res.status_code}): {res.text}"}
            return res.json()


_default_client: SandboxClient | None = None


def get_sandbox_client() -> SandboxClient:
    global _default_client
    if _default_client is None:
        _default_client = SandboxClient()
    return _default_client
