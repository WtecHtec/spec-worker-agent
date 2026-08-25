import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.prompts.prompt_manager import PromptManager
from src.domain.services.tools.base import BaseTool, ToolResult
from src.domain.services.tools.builtin import (
    CalculatorTool,
    CurrentTimeTool,
    FetchWebpageTool,
)
from src.domain.services.tools.sandbox import (
    SandboxRunCommandTool,
    SandboxReadFileTool,
    SandboxWriteFileTool,
    _resolve_safe_sandbox_path,
)
from src.domain.services.tools.registry import ToolRegistry, create_default_registry
from src.domain.services.agents.react import ReActAgent
from src.infrastructure.executor.llm_executor import LlmAgentExecutor


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> str:
    ws = tmp_path / "test_workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


def test_prompt_manager_render():
    pm = PromptManager()
    rendered = pm.render("system/react_worker.md", workspace_dir="/tmp/test_ws")
    assert "/tmp/test_ws" in rendered
    assert "ReAct 模式" in rendered


def test_resolve_safe_sandbox_path(tmp_workspace: str):
    # 正常路径
    p = _resolve_safe_sandbox_path(tmp_workspace, "sub/dir/test.txt")
    assert str(p).startswith(tmp_workspace)

    # 路径穿越攻击拦截
    with pytest.raises(PermissionError):
        _resolve_safe_sandbox_path(tmp_workspace, "../../etc/passwd")


@pytest.mark.asyncio
async def test_builtin_in_memory_tools():
    ctx = {}
    calc = CalculatorTool()
    calc_res = await calc.execute(ctx, expression="2**10 + 100")
    assert not calc_res.is_error
    assert "1124" in calc_res.output

    time_tool = CurrentTimeTool()
    time_res = await time_tool.execute(ctx)
    assert not time_res.is_error
    assert "UTC" in time_res.output

    # 测试 FetchWebpageTool（通过 Mock httpx 响应）
    web_tool = FetchWebpageTool()
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "# Hacker News Top Story\nClean markdown content."
        mock_get.return_value = mock_resp

        web_res = await web_tool.execute(ctx, url="https://news.ycombinator.com")
        assert not web_res.is_error
        assert "Hacker News Top Story" in web_res.output
        assert web_res.metadata["jina_url"] == "https://r.jina.ai/https://news.ycombinator.com"



@pytest.mark.asyncio
async def test_sandbox_tools(tmp_workspace: str):
    ctx = {"workspace_dir": tmp_workspace}

    with patch("src.domain.services.tools.sandbox.get_settings") as mock_settings:
        s = MagicMock()
        s.sandbox_enabled = False
        s.llm_workspace_dir = tmp_workspace
        mock_settings.return_value = s

        # 1. 测试 SandboxWriteFileTool
        write_tool = SandboxWriteFileTool()
        write_tool.settings = s
        write_res = await write_tool.execute(
            ctx, file_path="src/hello.py", content="print('hello sandbox world')\n"
        )
        assert not write_res.is_error
        assert (Path(tmp_workspace) / "src/hello.py").exists()

        # 2. 测试 SandboxReadFileTool
        read_tool = SandboxReadFileTool()
        read_tool.settings = s
        read_res = await read_tool.execute(ctx, file_path="src/hello.py")
        assert not read_res.is_error
        assert "hello sandbox world" in read_res.output

        # 3. 测试 SandboxRunCommandTool
        cmd_tool = SandboxRunCommandTool()
        cmd_tool.settings = s
        cmd_res = await cmd_tool.execute(ctx, command="python3 src/hello.py")
        assert not cmd_res.is_error
        assert "hello sandbox world" in cmd_res.output


def test_tool_registry_openai_schema():
    reg = create_default_registry()
    schemas = reg.get_openai_tools()
    tool_names = [s["function"]["name"] for s in schemas]
    # 包含纯内存内置工具与沙箱环境工具
    assert "calculator" in tool_names
    assert "get_current_time" in tool_names
    assert "fetch_webpage" in tool_names
    assert "sandbox_run_command" in tool_names
    assert "sandbox_read_file" in tool_names
    assert "sandbox_write_file" in tool_names


@pytest.mark.asyncio
async def test_react_agent_loop_with_mocked_llm(tmp_workspace: str):
    ctx = {"workspace_dir": tmp_workspace, "task_id": "task_123"}
    agent = ReActAgent()

    with patch("src.domain.services.tools.sandbox.get_settings") as mock_settings:
        s = MagicMock()
        s.sandbox_enabled = False
        s.llm_workspace_dir = tmp_workspace
        mock_settings.return_value = s

        # 将 registry 中的 sandbox tools 的 settings 也设为 false
        for t in agent.tool_registry.list_tools():
            if hasattr(t, "settings"):
                t.settings = s

        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_write_01"
        mock_tool_call.function.name = "sandbox_write_file"
        mock_tool_call.function.arguments = json.dumps(
            {"file_path": "msg.txt", "content": "test payload"}
        )

        mock_msg_1 = MagicMock()
        mock_msg_1.content = "我需要先创建 msg.txt 文件。"
        mock_msg_1.tool_calls = [mock_tool_call]
        mock_choice_1 = MagicMock(message=mock_msg_1)
        mock_resp_1 = MagicMock(choices=[mock_choice_1])

        mock_msg_2 = MagicMock()
        mock_msg_2.content = "文件已创建完成，任务顺利结束。"
        mock_msg_2.tool_calls = []
        mock_choice_2 = MagicMock(message=mock_msg_2)
        mock_resp_2 = MagicMock(choices=[mock_choice_2])

        agent.client.chat.completions.create = AsyncMock(
            side_effect=[mock_resp_1, mock_resp_2]
        )

        steps = []
        async for step in agent.run("请帮我创建 msg.txt 文件", ctx):
            steps.append(step)

        types = [s["type"] for s in steps]
        assert types == ["THINKING", "TOOL_CALL", "TOOL_RESULT", "FINAL"]
        assert steps[0]["content"]["text"] == "我需要先创建 msg.txt 文件。"
        assert steps[1]["content"]["tool_name"] == "sandbox_write_file"
        assert "文件成功写入" in steps[2]["content"]["output"]
        assert "任务顺利结束" in steps[3]["content"]["text"]

        assert (Path(tmp_workspace) / "msg.txt").exists()



@pytest.mark.asyncio
async def test_llm_agent_executor(tmp_workspace: str):
    executor = LlmAgentExecutor(
        task_input={"instruction": "测试指令", "task_id": "test_t1"},
        resume_from_step=0,
    )

    with patch("src.infrastructure.executor.llm_executor.PlanAndExecuteFlow.run") as mock_run:
        async def fake_steps(*args, **kwargs):
            yield {
                "step_index": 1,
                "type": "THINKING",
                "content": {"text": "思考中..."},
                "wait_for_human": False,
            }
            yield {
                "step_index": 2,
                "type": "FINAL",
                "content": {"text": "已全部搞定"},
                "wait_for_human": False,
            }

        mock_run.side_effect = fake_steps

        collected = []
        async for s in executor.run():
            collected.append(s)

        assert len(collected) == 2
        res = executor.get_result()
        assert res["summary"] == "已全部搞定"


@pytest.mark.asyncio
async def test_react_agent_loop_detection(tmp_workspace: str):
    ctx = {"workspace_dir": tmp_workspace, "task_id": "loop_task"}
    agent = ReActAgent()

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_repeat"
    mock_tool_call.function.name = "sandbox_read_file"
    mock_tool_call.function.arguments = json.dumps({"file_path": "non_existent.txt"})

    mock_msg = MagicMock()
    mock_msg.content = "让我再次尝试读取"
    mock_msg.tool_calls = [mock_tool_call]
    mock_choice = MagicMock(message=mock_msg)
    mock_resp = MagicMock(choices=[mock_choice])

    agent.client.chat.completions.create = AsyncMock(return_value=mock_resp)

    steps = []
    async for step in agent.run("重复任务", ctx):
        steps.append(step)

    final_steps = [s for s in steps if s["type"] == "FINAL"]
    assert len(final_steps) == 1
    assert "死循环熔断保护" in final_steps[0]["content"]["text"]
