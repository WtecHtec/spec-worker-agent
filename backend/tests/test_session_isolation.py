import pytest
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from src.domain.services.tools.sandbox import (
    SandboxRunCommandTool,
    SandboxReadFileTool,
    SandboxWriteFileTool,
    _resolve_safe_local_path,
)
from src.application.file.use_cases import StreamFileContentUseCase
from src.domain.entities.models import SessionFile


@pytest.fixture
def temp_workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    yield ws
    shutil.rmtree(tmp_path, ignore_errors=True)


def test_resolve_safe_local_path_with_session(temp_workspace):
    # 1. 正常在会话子目录中解析
    session_dir = temp_workspace / "sessions" / "sess_001"
    target = _resolve_safe_local_path(str(session_dir), "src/index.html")
    assert str(target).startswith(str(session_dir))
    assert target.name == "index.html"

    # 2. 越界访问抛出异常
    with pytest.raises(PermissionError):
        _resolve_safe_local_path(str(session_dir), "../../secret.txt")


@pytest.mark.asyncio
async def test_sandbox_tools_session_isolation(temp_workspace):
    write_tool = SandboxWriteFileTool()
    read_tool = SandboxReadFileTool()
    run_tool = SandboxRunCommandTool()

    # 禁用 Docker 沙箱以测试本地回退隔离
    write_tool.settings.sandbox_enabled = False
    read_tool.settings.sandbox_enabled = False
    run_tool.settings.sandbox_enabled = False

    ctx_a = {
        "workspace_dir": str(temp_workspace),
        "session_id": "sess_a",
    }
    ctx_b = {
        "workspace_dir": str(temp_workspace),
        "session_id": "sess_b",
    }

    # 1. 在会话 A 中写入 index.html
    res_a = await write_tool.execute(ctx_a, file_path="index.html", content="<h1>Session A</h1>")
    assert res_a.is_error is False

    # 2. 在会话 B 中写入同名 index.html
    res_b = await write_tool.execute(ctx_b, file_path="index.html", content="<h1>Session B</h1>")
    assert res_b.is_error is False

    # 3. 验证物理文件是否分别存放在各自独立的 sessions/{session_id} 目录下
    file_a = temp_workspace / "sessions" / "sess_a" / "index.html"
    file_b = temp_workspace / "sessions" / "sess_b" / "index.html"
    assert file_a.exists()
    assert file_b.exists()
    assert file_a.read_text(encoding="utf-8") == "<h1>Session A</h1>"
    assert file_b.read_text(encoding="utf-8") == "<h1>Session B</h1>"

    # 4. 读取验证
    read_res_a = await read_tool.execute(ctx_a, file_path="index.html")
    assert "<h1>Session A</h1>" in read_res_a.output

    read_res_b = await read_tool.execute(ctx_b, file_path="index.html")
    assert "<h1>Session B</h1>" in read_res_b.output

    # 5. 在会话 A 中执行 shell 命令 (pwd / ls)，验证执行工作目录是否限定在会话目录
    run_res_a = await run_tool.execute(ctx_a, command="pwd")
    assert run_res_a.is_error is False
    assert "sess_a" in run_res_a.output


@pytest.mark.asyncio
async def test_stream_file_use_case_session_isolation(temp_workspace):
    file_repo = AsyncMock()
    session_repo = AsyncMock()

    # 预置物理文件在 session 目录下
    sess_dir = temp_workspace / "sessions" / "sess_100"
    sess_dir.mkdir(parents=True, exist_ok=True)
    (sess_dir / "index.html").write_text("<h1>Hello Stream</h1>", encoding="utf-8")

    dummy_file = SessionFile(
        id="f_1",
        session_id="sess_100",
        user_id="user_1",
        file_name="index.html",
        file_path="index.html",
        file_size=20,
        mime_type="text/html",
        category="html",
    )
    file_repo.get_by_id.return_value = dummy_file

    use_case = StreamFileContentUseCase(
        file_repo=file_repo,
        session_repo=session_repo,
    )
    use_case.settings.sandbox_enabled = False
    use_case.settings.llm_workspace_dir = str(temp_workspace)

    stream_gen, file_meta = await use_case.execute("f_1", "user_1")
    assert file_meta.id == "f_1"

    chunks = []
    async for chunk in stream_gen:
        chunks.append(chunk)
    content = b"".join(chunks).decode("utf-8")
    assert content == "<h1>Hello Stream</h1>"
