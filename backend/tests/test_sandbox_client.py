import pytest
from src.infrastructure.sandbox.client import SandboxClient
from src.domain.services.tools.sandbox import (
    SandboxRunCommandTool,
    SandboxReadFileTool,
    SandboxWriteFileTool,
)


@pytest.mark.asyncio
async def test_sandbox_client_live_docker_container():
    """测试与正在运行的独立 Go Sandbox Docker 容器进行真实通信"""
    client = SandboxClient(base_url="http://127.0.0.1:5050")

    # 1. 探针存活测试
    is_alive = await client.health_check()
    assert is_alive, "Sandbox container should be alive on http://127.0.0.1:5050"

    # 2. 文件写入测试
    write_res = await client.write_file(
        "test_pkg/math_calc.py",
        "import sys\nprint(f'CALC_RESULT:{2**8}')\n",
    )
    assert write_res.get("success") is True

    # 3. 文件读取测试
    read_res = await client.read_file("test_pkg/math_calc.py")
    assert not read_res.get("is_error")
    assert "CALC_RESULT" in read_res.get("content", "")

    # 4. 目录列表测试
    list_res = await client.list_files("test_pkg")
    files = [f["name"] for f in list_res.get("files", [])]
    assert "math_calc.py" in files

    # 5. 命令执行测试
    exec_res = await client.execute_command("python3 test_pkg/math_calc.py")
    assert exec_res.get("exit_code") == 0
    assert "CALC_RESULT:256" in exec_res.get("output", "")


@pytest.mark.asyncio
async def test_sandbox_tools_with_client():
    """测试通过 Agent Tool 接口调用 Docker 沙箱"""
    client = SandboxClient(base_url="http://127.0.0.1:5050")
    ctx = {"task_id": "test_sandbox_tool_task"}

    # Write tool
    write_tool = SandboxWriteFileTool(sandbox_client=client)
    res_w = await write_tool.execute(ctx, file_path="app.py", content="print('hello agent in docker!')")
    assert not res_w.is_error
    assert res_w.metadata.get("mode") == "docker_sandbox"

    # Read tool
    read_tool = SandboxReadFileTool(sandbox_client=client)
    res_r = await read_tool.execute(ctx, file_path="app.py")
    assert not res_r.is_error
    assert "hello agent in docker!" in res_r.output

    # Exec tool
    exec_tool = SandboxRunCommandTool(sandbox_client=client)
    res_e = await exec_tool.execute(ctx, command="python3 app.py")
    assert not res_e.is_error
    assert "hello agent in docker!" in res_e.output
