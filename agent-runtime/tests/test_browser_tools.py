import pytest
from unittest.mock import patch, AsyncMock
import httpx
from src.tools.registry import create_default_registry, ToolRegistry
from src.tools.browser import (
    BrowserOpenPageTool,
    BrowserClosePageTool,
    BrowserGetSnapshotTool,
    BrowserClickTool,
    BrowserScreenshotTool,
)


def test_browser_tools_schema():
    """验证 5 大 CDP 浏览器工具的 OpenAI Schema 定义合规"""
    tools = [
        BrowserOpenPageTool(),
        BrowserClosePageTool(),
        BrowserGetSnapshotTool(),
        BrowserClickTool(),
        BrowserScreenshotTool(),
    ]

    expected_names = [
        "browser_open_page",
        "browser_close_page",
        "browser_get_snapshot",
        "browser_click",
        "browser_screenshot",
    ]

    for tool, name in zip(tools, expected_names):
        assert tool.name == name
        assert len(tool.description) > 0
        schema = tool.to_openai_tool()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == name
        assert "parameters" in schema["function"]


def test_browser_tools_in_default_registry():
    """验证 agent-runtime 默认注册中心已包含 5 大 CDP 浏览器工具"""
    registry = create_default_registry()
    tool_names = [t.name for t in registry.list_tools()]

    assert "browser_open_page" in tool_names
    assert "browser_close_page" in tool_names
    assert "browser_get_snapshot" in tool_names
    assert "browser_click" in tool_names
    assert "browser_screenshot" in tool_names

    openai_tools = registry.get_openai_tools()
    openai_tool_names = [t["function"]["name"] for t in openai_tools]
    assert "browser_open_page" in openai_tool_names
    assert "browser_click" in openai_tool_names
    assert "browser_get_snapshot" in openai_tool_names
    assert "browser_screenshot" in openai_tool_names
    assert "browser_close_page" in openai_tool_names


@pytest.mark.asyncio
async def test_browser_tools_dispatch_flow():
    """测试 agent-runtime 中 CDP 浏览器工具调用与分发全闭环"""

    def mock_handler(request: httpx.Request) -> httpx.Response:
        url_path = request.url.path
        if url_path.endswith("/tools/browser/open"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "title": "测试商城",
                    "url": "http://example.com",
                    "output": "页面状态: 测试商城\n\n- [1] (BUTTON) '立即购买'",
                },
            )
        elif url_path.endswith("/tools/browser/click"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "title": "测试商城",
                    "url": "http://example.com",
                    "output": "已成功点击编号 [1] 元素！\n- [1] (BUTTON) '已加入购物车'",
                },
            )
        elif url_path.endswith("/tools/browser/snapshot"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "title": "测试商城",
                    "url": "http://example.com",
                    "output": "页面最新 DOM 结构快照",
                    "screenshot_base64": "mock_base64_snapshot",
                },
            )
        elif url_path.endswith("/tools/browser/screenshot"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "output": "页面截图已成功保存至沙箱文件: screenshots/home.png",
                    "file_path": "screenshots/home.png",
                    "preview_url": "/fs/raw?path=screenshots/home.png",
                    "screenshot_base64": "mock_base64_img",
                },
            )
        elif url_path.endswith("/tools/browser/close"):
            return httpx.Response(
                200,
                json={"success": True, "output": "浏览器页面已关闭。"},
            )
        return httpx.Response(404, json={"error": "not found"})

    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(mock_handler)
    mock_client_factory = lambda **kwargs: original_client(transport=transport)

    with patch("httpx.AsyncClient", side_effect=mock_client_factory):
        registry = create_default_registry()
        ctx = {"thread_id": "thread-test-123", "user_id": "user-456"}

        # 1. 测试打开网页
        res_open = await registry.dispatch(
            "browser_open_page",
            {"url": "http://example.com"},
            ctx,
        )
        assert not res_open.is_error
        assert "thread-test-123" in res_open.output
        assert "测试商城" in res_open.output
        assert res_open.metadata.get("browser_instance_id") == "thread-test-123"

        # 2. 测试点击元素
        res_click = await registry.dispatch(
            "browser_click",
            {"element_id": 1},
            ctx,
        )
        assert not res_click.is_error
        assert "已成功点击" in res_click.output
        assert "[1]" in res_click.output

        # 3. 测试获取快照
        res_snap = await registry.dispatch(
            "browser_get_snapshot",
            {"include_screenshot": True},
            ctx,
        )
        assert not res_snap.is_error
        assert res_snap.metadata.get("screenshot_base64") == "mock_base64_snapshot"

        # 4. 测试截屏
        res_shot = await registry.dispatch(
            "browser_screenshot",
            {"full_page": False, "save_path": "screenshots/home.png"},
            ctx,
        )
        assert not res_shot.is_error
        assert "screenshots/home.png" in res_shot.output
        assert res_shot.metadata.get("preview_url").startswith("http")

        # 5. 测试关闭网页
        res_close = await registry.dispatch(
            "browser_close_page",
            {},
            ctx,
        )
        assert not res_close.is_error
        assert "浏览器页面已关闭" in res_close.output


@pytest.mark.asyncio
async def test_browser_click_invalid_element_id():
    """测试点击工具缺少或传入无效编号时的优雅错误捕获"""
    tool = BrowserClickTool()
    ctx = {"thread_id": "thread-test"}

    # 缺少 element_id
    res_missing = await tool.execute(ctx)
    assert res_missing.is_error
    assert "缺少必需参数" in res_missing.output

    # 传入非数字
    res_invalid = await tool.execute(ctx, element_id="invalid-id")
    assert res_invalid.is_error
    assert "不是有效的数字编号" in res_invalid.output
