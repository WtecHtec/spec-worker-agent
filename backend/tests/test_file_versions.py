import pytest
from unittest.mock import AsyncMock
from src.application.file.use_cases import (
    calculate_unified_diff,
    RecordFileUseCase,
    ListFileVersionsUseCase,
    GetFileVersionDetailUseCase,
)
from src.domain.entities.models import SessionFile, FileVersion
from src.domain.exceptions import ForbiddenAccessException, FileNotFoundException


def test_calculate_unified_diff():
    old_code = "function hello() {\n  return 'hello';\n}\n"
    new_code = "function hello() {\n  return 'hello world!';\n}\n"
    diff = calculate_unified_diff(old_code, new_code, file_path="src/App.tsx")
    assert "--- a/src/App.tsx" in diff
    assert "+++ b/src/App.tsx" in diff
    assert "-  return 'hello';" in diff
    assert "+  return 'hello world!';" in diff


@pytest.mark.asyncio
async def test_record_file_auto_versions():
    file_repo = AsyncMock()
    version_repo = AsyncMock()

    dummy_file = SessionFile(
        id="f_100",
        session_id="sess_1",
        user_id="user_1",
        file_name="App.tsx",
        file_path="src/App.tsx",
        file_size=200,
        mime_type="text/typescript",
        category="code",
    )
    file_repo.upsert.return_value = dummy_file
    version_repo.get_latest_version.return_value = None

    uc = RecordFileUseCase(file_repo=file_repo, version_repo=version_repo)
    result = await uc.execute(
        session_id="sess_1",
        user_id="user_1",
        file_path="src/App.tsx",
        file_size=200,
        new_content="export default function App() {}",
    )

    assert result.id == "f_100"
    version_repo.create.assert_called_once()
    args = version_repo.create.call_args[1]
    assert args["file_id"] == "f_100"
    assert args["version_num"] == 1
    assert "export default function App() {}" in (args["diff_content"] or "")


@pytest.mark.asyncio
async def test_list_and_get_file_versions():
    file_repo = AsyncMock()
    version_repo = AsyncMock()

    dummy_file = SessionFile(
        id="f_100",
        session_id="sess_1",
        user_id="user_1",
        file_name="App.tsx",
        file_path="src/App.tsx",
    )
    file_repo.get_by_id.return_value = dummy_file

    v1 = FileVersion(
        id="v_1",
        file_id="f_100",
        session_id="sess_1",
        version_num=1,
        file_size=100,
        diff_content="initial",
    )
    v2 = FileVersion(
        id="v_2",
        file_id="f_100",
        session_id="sess_1",
        version_num=2,
        file_size=150,
        diff_content="updated",
    )
    version_repo.list_by_file_id.return_value = [v2, v1]
    version_repo.get_by_id.return_value = v2

    list_uc = ListFileVersionsUseCase(file_repo=file_repo, version_repo=version_repo)
    versions = await list_uc.execute("f_100", user_id="user_1")
    assert len(versions) == 2
    assert versions[0].version_num == 2

    # Forbidden access
    with pytest.raises(ForbiddenAccessException):
        await list_uc.execute("f_100", user_id="other_user")

    # Get detail
    detail_uc = GetFileVersionDetailUseCase(file_repo=file_repo, version_repo=version_repo)
    detail = await detail_uc.execute("f_100", "v_2", user_id="user_1")
    assert detail.id == "v_2"
    assert detail.diff_content == "updated"


@pytest.mark.asyncio
async def test_record_large_file_snapshot(tmp_path):
    file_repo = AsyncMock()
    version_repo = AsyncMock()

    dummy_file = SessionFile(
        id="f_large",
        session_id="sess_large",
        user_id="user_1",
        file_name="bundle.js",
        file_path="dist/bundle.js",
        file_size=600 * 1024,
    )
    file_repo.upsert.return_value = dummy_file
    version_repo.get_latest_version.return_value = None

    uc = RecordFileUseCase(
        file_repo=file_repo,
        version_repo=version_repo,
        base_storage_dir=str(tmp_path),
    )

    large_content = "x" * (600 * 1024)
    result = await uc.execute(
        session_id="sess_large",
        user_id="user_1",
        file_path="dist/bundle.js",
        file_size=len(large_content),
        new_content=large_content,
    )

    assert result.id == "f_large"
    version_repo.create.assert_called_once()
    args = version_repo.create.call_args[1]
    assert args["storage_key"] is not None
    assert "大文件归档快照" in args["diff_content"]
    assert (tmp_path / "sessions" / "sess_large" / ".versions" / "f_large_v1.snapshot").exists()
