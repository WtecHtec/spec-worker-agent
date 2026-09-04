import os
from typing import Any
import httpx
from .base import BaseTool, ToolResult

SANDBOX_URL = os.getenv("SANDBOX_DAEMON_URL", "http://localhost:5050").rstrip("/")


def _get_session_id(ctx: dict[str, Any], explicit_session_id: str | None = None) -> str:
    """
    获取浏览器实例会话标识（与沙箱会话生命周期对齐）：
    1. 优先使用 LLM 显式传入的 browser_instance_id
    2. 其次回退使用当前任务上下文的 thread_id / session_id / task_id
    3. 默认兜底 "default"
    """
    if explicit_session_id and str(explicit_session_id).strip():
        return str(explicit_session_id).strip()
    return str(ctx.get("thread_id") or ctx.get("session_id") or ctx.get("task_id") or "default")


class BrowserOpenPageTool(BaseTool):
    """浏览器打开网页工具"""

    def __init__(self, sandbox_url: str | None = None):
        self.sandbox_url = (sandbox_url or SANDBOX_URL).rstrip("/")

    @property
    def name(self) -> str:
        return "browser_open_page"

    @property
    def description(self) -> str:
        return (
            "在沙箱浏览器中打开指定的 URL 网址，并自动返回加载完成后的已编号页面结构快照与浏览器实例标识。"
            "每个可交互按钮（包括 div/span 伪按钮）、输入框、链接均带有唯一的 [数字编号]，供后续点击。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要打开的网页完整地址（需包含 http:// 或 https://）",
                },
                "timeout_sec": {
                    "type": "integer",
                    "description": "可选的页面加载超时时间（秒），默认 30",
                },
                "browser_instance_id": {
                    "type": "string",
                    "description": "可选的目标浏览器实例标识（默认为空，自动绑定当前会话）",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        ctx: dict[str, Any],
        url: str,
        timeout_sec: int = 30,
        browser_instance_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        session_id = _get_session_id(ctx, browser_instance_id)
        payload = {"url": url, "session_id": session_id, "timeout_sec": timeout_sec}
        try:
            async with httpx.AsyncClient(timeout=float(timeout_sec + 5)) as client:
                resp = await client.post(f"{self.sandbox_url}/tools/browser/open", json=payload)
                if resp.status_code != 200:
                    return ToolResult(output=f"打开网页失败 ({resp.status_code}): {resp.text}", is_error=True)
                res = resp.json()
        except Exception as e:
            return ToolResult(output=f"请求沙箱浏览器异常: {str(e)}", is_error=True)

        if not res.get("success"):
            return ToolResult(output=f"打开网页失败: {res.get('error')}", is_error=True)

        raw_output = res.get("output", "页面已打开")
        output_with_instance = f"【当前浏览器实例 ID】: {session_id}\n\n{raw_output}"

        return ToolResult(
            output=output_with_instance,
            metadata={"url": res.get("url"), "title": res.get("title"), "browser_instance_id": session_id},
        )


class BrowserClosePageTool(BaseTool):
    """浏览器关闭页面工具"""

    def __init__(self, sandbox_url: str | None = None):
        self.sandbox_url = (sandbox_url or SANDBOX_URL).rstrip("/")

    @property
    def name(self) -> str:
        return "browser_close_page"

    @property
    def description(self) -> str:
        return "关闭沙箱中当前打开的浏览器页面并销毁会话资源，完成任务后调用以释放内存。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "browser_instance_id": {
                    "type": "string",
                    "description": "可选的目标浏览器实例标识（默认为空，自动关闭当前会话实例）",
                }
            },
        }

    async def execute(
        self,
        ctx: dict[str, Any],
        browser_instance_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        session_id = _get_session_id(ctx, browser_instance_id)
        payload = {"session_id": session_id}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(f"{self.sandbox_url}/tools/browser/close", json=payload)
                if resp.status_code != 200:
                    return ToolResult(output=f"关闭网页失败 ({resp.status_code}): {resp.text}", is_error=True)
                res = resp.json()
        except Exception as e:
            return ToolResult(output=f"请求沙箱浏览器异常: {str(e)}", is_error=True)

        if not res.get("success"):
            return ToolResult(output=f"关闭网页失败: {res.get('error')}", is_error=True)

        return ToolResult(output=res.get("output", "浏览器页面已关闭。"))


class BrowserGetSnapshotTool(BaseTool):
    """获取页面快照工具"""

    def __init__(self, sandbox_url: str | None = None):
        self.sandbox_url = (sandbox_url or SANDBOX_URL).rstrip("/")

    @property
    def name(self) -> str:
        return "browser_get_snapshot"

    @property
    def description(self) -> str:
        return (
            "重新感知并提取当前网页视口内所有已编号的交互元素结构（按钮、div、输入框）。"
            "常用于页面滚动、异步数据加载完成后重新获取最新编号。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "include_screenshot": {
                    "type": "boolean",
                    "description": "是否同时获取当前视口的截图（可选，默认 false）",
                },
                "browser_instance_id": {
                    "type": "string",
                    "description": "可选的目标浏览器实例标识（默认为空，自动绑定当前会话）",
                },
            },
        }

    async def execute(
        self,
        ctx: dict[str, Any],
        include_screenshot: bool = False,
        browser_instance_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        session_id = _get_session_id(ctx, browser_instance_id)
        payload = {"session_id": session_id, "include_screenshot": include_screenshot}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.sandbox_url}/tools/browser/snapshot", json=payload)
                if resp.status_code != 200:
                    return ToolResult(output=f"获取快照失败 ({resp.status_code}): {resp.text}", is_error=True)
                res = resp.json()
        except Exception as e:
            return ToolResult(output=f"请求沙箱浏览器异常: {str(e)}", is_error=True)

        if not res.get("success"):
            return ToolResult(output=f"获取页面快照失败: {res.get('error')}", is_error=True)

        meta = {"url": res.get("url"), "title": res.get("title"), "browser_instance_id": session_id}
        if res.get("screenshot_base64"):
            meta["screenshot_base64"] = res.get("screenshot_base64")

        return ToolResult(output=res.get("output", ""), metadata=meta)


class BrowserClickTool(BaseTool):
    """浏览器点击元素工具"""

    def __init__(self, sandbox_url: str | None = None):
        self.sandbox_url = (sandbox_url or SANDBOX_URL).rstrip("/")

    @property
    def name(self) -> str:
        return "browser_click"

    @property
    def description(self) -> str:
        return (
            "根据页面快照中分配的 [数字编号] 触发真实物理点击（支持 div 伪按钮、普通按钮、超链接等）。"
            "【注意】：element_id 必须严格来自上一轮 browser_open_page 或 browser_get_snapshot 快照中分配的数字编号，严禁盲猜。"
            "点击完成后会自动等待页面稳定，并直接返回点击后的最新已编号页面结构与当前活动 Tab 状态。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "element_id": {
                    "type": "integer",
                    "description": "上一轮快照列表中目标元素对应的具体数字编号（例如 1, 2, 3...）",
                },
                "browser_instance_id": {
                    "type": "string",
                    "description": "可选的目标浏览器实例标识（默认为空，自动绑定当前会话）",
                },
            },
            "required": ["element_id"],
        }

    async def execute(
        self,
        ctx: dict[str, Any],
        element_id: Any = None,
        browser_instance_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        if element_id is None:
            return ToolResult(output="点击失败: 缺少必需参数 element_id（元素编号）", is_error=True)

        try:
            parsed_id = int(str(element_id).strip())
        except (ValueError, TypeError):
            return ToolResult(output=f"点击失败: 传入的 element_id [{element_id}] 不是有效的数字编号", is_error=True)

        session_id = _get_session_id(ctx, browser_instance_id)
        payload = {"element_id": parsed_id, "session_id": session_id}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.sandbox_url}/tools/browser/click", json=payload)
                if resp.status_code != 200:
                    return ToolResult(output=f"点击元素失败 ({resp.status_code}): {resp.text}", is_error=True)
                res = resp.json()
        except Exception as e:
            return ToolResult(output=f"请求沙箱浏览器异常: {str(e)}", is_error=True)

        if not res.get("success"):
            return ToolResult(output=f"点击编号 [{parsed_id}] 失败: {res.get('error')}", is_error=True)

        return ToolResult(
            output=res.get("output", f"已成功点击元素 [{parsed_id}]"),
            metadata={"url": res.get("url"), "title": res.get("title"), "browser_instance_id": session_id},
        )


class BrowserScreenshotTool(BaseTool):
    """浏览器截屏工具"""

    def __init__(self, sandbox_url: str | None = None):
        self.sandbox_url = (sandbox_url or SANDBOX_URL).rstrip("/")

    @property
    def name(self) -> str:
        return "browser_screenshot"

    @property
    def description(self) -> str:
        return "对当前浏览器页面进行截图并自动保存为沙箱文件，支持指定目录，返回文件路径与在线预览链接供用户或多模态 Agent 访问。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "full_page": {
                    "type": "boolean",
                    "description": "是否截取整页滚动长图（默认 false 仅截取当前视口）",
                },
                "save_path": {
                    "type": "string",
                    "description": "可选的图片保存相对路径（如 screenshots/home.png），默认为空时自动保存在 screenshots/ 目录下",
                },
                "browser_instance_id": {
                    "type": "string",
                    "description": "可选的目标浏览器实例标识（默认为空，自动绑定当前会话）",
                },
            },
        }

    async def execute(
        self,
        ctx: dict[str, Any],
        full_page: bool = False,
        save_path: str | None = None,
        browser_instance_id: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        session_id = _get_session_id(ctx, browser_instance_id)
        payload: dict[str, Any] = {"full_page": full_page, "session_id": session_id}
        if save_path:
            payload["save_path"] = save_path

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(f"{self.sandbox_url}/tools/browser/screenshot", json=payload)
                if resp.status_code != 200:
                    return ToolResult(output=f"截图失败 ({resp.status_code}): {resp.text}", is_error=True)
                res = resp.json()
        except Exception as e:
            return ToolResult(output=f"请求沙箱浏览器异常: {str(e)}", is_error=True)

        if not res.get("success"):
            return ToolResult(output=f"截图失败: {res.get('error')}", is_error=True)

        base64_img = res.get("screenshot_base64", "")
        file_path = res.get("file_path", "")
        preview_url = res.get("preview_url", "")
        if preview_url and not preview_url.startswith("http"):
            preview_url = f"{self.sandbox_url}{preview_url}"

        output_text = res.get(
            "output",
            f"页面截图已成功保存至沙箱文件: {file_path}\n在线预览链接: {preview_url}",
        )

        return ToolResult(
            output=output_text,
            metadata={
                "screenshot_base64": base64_img,
                "file_path": file_path,
                "preview_url": preview_url,
                "full_page": full_page,
                "browser_instance_id": session_id,
            },
        )
