import asyncio
import pytest
from src.tools.base import ToolResult
from src.tools.builtin import CalculatorTool, CurrentTimeTool
from src.tools.registry import create_default_registry, ToolRegistry
from src.tools.manager import UserToolRegistryManager


@pytest.mark.asyncio
async def test_calculator_tool_execution():
    calc = CalculatorTool()
    ctx = {"user_id": "test_user"}
    res = await calc.execute(ctx, expression="100 * 2 + 50")
    assert not res.is_error
    assert res.output == "250"


@pytest.mark.asyncio
async def test_default_registry():
    reg = create_default_registry()
    tools = reg.list_tools()
    tool_names = [t.name for t in tools]
    assert "calculator" in tool_names
    assert "get_current_time" in tool_names
    assert "sandbox_run_command" in tool_names

    openai_tools = reg.get_openai_tools()
    assert len(openai_tools) >= 5
    assert openai_tools[0]["type"] == "function"

    # 测试分发执行
    ctx = {"user_id": "test_user"}
    res = await reg.dispatch("calculator", {"expression": "2**10"}, ctx)
    assert not res.is_error
    assert res.output == "1024"


@pytest.mark.asyncio
async def test_multitenant_cache_and_targeted_invalidation():
    manager = UserToolRegistryManager()
    user_a = "user_alpha"
    user_b = "user_beta"

    # 1. 分别为 user_a 和 user_b 获取 registry
    reg_a1 = await manager.get_registry_for_user(user_a)
    reg_b1 = await manager.get_registry_for_user(user_b)

    # 2. 验证多租户内存隔离：两人是两个完全不同的实例
    assert reg_a1 is not reg_b1

    # 3. 再次获取应直接命中内存缓存（同一对象）
    reg_a2 = await manager.get_registry_for_user(user_a)
    assert reg_a1 is reg_a2

    reg_b2 = await manager.get_registry_for_user(user_b)
    assert reg_b1 is reg_b2

    # 4. 定向失效 user_a
    manager.invalidate_cache(user_a)

    # 验证 user_a 被剔除，而 user_b 完好保留在缓存中
    assert user_a not in manager._user_registries
    assert user_b in manager._user_registries

    # 5. user_b 再次获取依然是原来的实例（未被影响）
    reg_b3 = await manager.get_registry_for_user(user_b)
    assert reg_b3 is reg_b1
