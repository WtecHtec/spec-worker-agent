import pytest
from unittest.mock import AsyncMock
from src.domain.services.tools.registry import create_default_registry, ToolRegistry
from src.domain.services.tools.browser import (
    BrowserOpenPageTool,
    BrowserClosePageTool,
    BrowserGetSnapshotTool,
    BrowserClickTool,
    BrowserScreenshotTool,
)
from src.infrastructure.sandbox.client import SandboxClient


def test_browser_tools_schema():
    """验证 5 大浏览器工具的 OpenAI Schema 定义合规"""
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
    """验证默认注册中心已包含 5 大浏览器工具"""
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


@pytest.mark.asyncio
async def test_browser_tools_dispatch_flow():
    """测试多轮 ReAct 工具分发调度闭环"""
    mock_client = AsyncMock(spec=SandboxClient)
    mock_client.base_url = "http://localhost:5050"

    # 1. 模拟 open 响应
    mock_client.browser_open.return_value = {
        "success": True,
        "title": "测试商城",
        "url": "http://example.com",
        "output": "页面状态: 测试商城\n\n- [1] (DIV) \"加入购物车\"",
    }

    # 2. 模拟 click 响应
    mock_client.browser_click.return_value = {
        "success": True,
        "title": "测试商城",
        "url": "http://example.com",
        "output": "已成功点击编号 [1] 元素！\n\n点击后的最新页面状态：\n- [1] (DIV) \"已加入\"",
    }

    # 3. 模拟 snapshot 响应
    mock_client.browser_get_snapshot.return_value = {
        "success": True,
        "title": "测试商城",
        "url": "http://example.com",
        "output": "最新快照...",
        "screenshot_base64": "mock_base64_string",
    }

    # 4. 模拟 screenshot 响应
    mock_client.browser_screenshot.return_value = {
        "success": True,
        "output": "页面截图已成功保存至沙箱文件: screenshots/home.png",
        "file_path": "screenshots/home.png",
        "preview_url": "/fs/raw?path=screenshots/home.png",
        "screenshot_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
    }

    # 5. 模拟 close 响应
    mock_client.browser_close.return_value = {
        "success": True,
        "output": "浏览器页面已关闭。",
    }

    registry = ToolRegistry()
    registry.register(BrowserOpenPageTool(sandbox_client=mock_client))
    registry.register(BrowserClosePageTool(sandbox_client=mock_client))
    registry.register(BrowserGetSnapshotTool(sandbox_client=mock_client))
    registry.register(BrowserClickTool(sandbox_client=mock_client))
    registry.register(BrowserScreenshotTool(sandbox_client=mock_client))

    ctx = {"task_id": "test-task-1001"}

    # 步骤 1: Open
    res_open = await registry.dispatch("browser_open_page", {"url": "http://example.com"}, ctx)
    assert not res_open.is_error
    assert "测试商城" in res_open.output
    mock_client.browser_open.assert_awaited_once_with(url="http://example.com", session_id="test-task-1001", timeout_sec=30)

    # 步骤 2: Click
    res_click = await registry.dispatch("browser_click", {"element_id": 1}, ctx)
    assert not res_click.is_error
    assert "已成功点击编号 [1]" in res_click.output
    mock_client.browser_click.assert_awaited_once_with(element_id=1, session_id="test-task-1001")

    # 步骤 3: Snapshot
    res_snapshot = await registry.dispatch("browser_get_snapshot", {"include_screenshot": True}, ctx)
    assert not res_snapshot.is_error
    assert res_snapshot.metadata.get("screenshot_base64") == "mock_base64_string"

    # 步骤 4: Screenshot
    res_screenshot = await registry.dispatch("browser_screenshot", {"full_page": False, "save_path": "screenshots/home.png"}, ctx)
    assert not res_screenshot.is_error
    assert len(res_screenshot.metadata.get("screenshot_base64")) > 0
    assert res_screenshot.metadata.get("file_path") == "screenshots/home.png"
    assert "/fs/raw?path=" in res_screenshot.metadata.get("preview_url")

    # 步骤 5: Close
    res_close = await registry.dispatch("browser_close_page", {}, ctx)
    assert not res_close.is_error
    assert "已关闭" in res_close.output
    mock_client.browser_close.assert_awaited_once_with(session_id="test-task-1001")


@pytest.mark.asyncio
async def test_browser_tool_error_handling():
    """测试沙箱异常时的错误处理与语义回传"""
    mock_client = AsyncMock(spec=SandboxClient)
    mock_client.browser_open.return_value = {
        "success": False,
        "error": "connection refused: 127.0.0.1:9222",
    }

    registry = ToolRegistry()
    registry.register(BrowserOpenPageTool(sandbox_client=mock_client))

    ctx = {"task_id": "test-task-err"}
    res = await registry.dispatch("browser_open_page", {"url": "http://invalid-url"}, ctx)
    assert res.is_error is True
    assert "connection refused" in res.output
