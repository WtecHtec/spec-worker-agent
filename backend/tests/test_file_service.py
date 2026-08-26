import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from src.application.file.use_cases import (
    detect_category_and_mime,
    ListSessionFilesUseCase,
    GetFileMetadataUseCase,
    DeleteFileUseCase,
    RecordFileUseCase,
)
from src.domain.entities.models import SessionFile, Session
from src.domain.exceptions import ForbiddenAccessException, FileNotFoundException


def test_detect_category_and_mime():
    # HTML
    cat, mime = detect_category_and_mime("dist/index.html")
    assert cat == "html"
    assert "text/html" in mime

    # Image
    cat, mime = detect_category_and_mime("screenshots/dashboard.png")
    assert cat == "image"
    assert mime == "image/png"

    # Code
    cat, mime = detect_category_and_mime("src/main.py")
    assert cat == "code"
    assert "python" in mime

    # Document
    cat, mime = detect_category_and_mime("README.md")
    assert cat == "document"
    assert "markdown" in mime


@pytest.mark.asyncio
async def test_record_and_list_files_use_case():
    file_repo = AsyncMock()
    session_repo = AsyncMock()

    dummy_session = Session(
        id="sess_100",
        user_id="user_1",
        title="Test Session",
    )
    session_repo.get_by_id.return_value = dummy_session

    dummy_file = SessionFile(
        id="f_1",
        session_id="sess_100",
        user_id="user_1",
        file_name="index.html",
        file_path="index.html",
        file_size=1024,
        mime_type="text/html",
        category="html",
    )
    file_repo.upsert.return_value = dummy_file
    file_repo.list_by_session.return_value = ([dummy_file], 1)

    # 1. Record file
    record_uc = RecordFileUseCase(file_repo=file_repo)
    res_file = await record_uc.execute(
        session_id="sess_100",
        user_id="user_1",
        file_path="index.html",
        file_size=1024,
    )
    assert res_file.file_name == "index.html"
    assert file_repo.upsert.called

    # 2. List files
    list_uc = ListSessionFilesUseCase(file_repo=file_repo, session_repo=session_repo)
    files, total = await list_uc.execute(session_id="sess_100", user_id="user_1")
    assert total == 1
    assert len(files) == 1
    assert files[0].category == "html"

    # 3. Forbidden test
    with pytest.raises(ForbiddenAccessException):
        await list_uc.execute(session_id="sess_100", user_id="wrong_user")


@pytest.mark.asyncio
async def test_get_and_delete_file_use_case():
    file_repo = AsyncMock()
    session_repo = AsyncMock()

    dummy_file = SessionFile(
        id="f_1",
        session_id="sess_100",
        user_id="user_1",
        file_name="report.pdf",
        file_path="report.pdf",
        file_size=2048,
        mime_type="application/pdf",
        category="document",
    )
    file_repo.get_by_id.return_value = dummy_file
    file_repo.delete_by_id.return_value = True

    get_uc = GetFileMetadataUseCase(file_repo=file_repo, session_repo=session_repo)
    res = await get_uc.execute(file_id="f_1", user_id="user_1")
    assert res.id == "f_1"

    # Forbidden on other user
    with pytest.raises(ForbiddenAccessException):
        await get_uc.execute(file_id="f_1", user_id="other_user")

    # Delete
    del_uc = DeleteFileUseCase(file_repo=file_repo)
    del_res = await del_uc.execute(file_id="f_1", user_id="user_1")
    assert del_res is True


@pytest.mark.asyncio
async def test_file_router_endpoints():
    from api_main import app
    from src.interface.middleware.auth import get_current_user_id
    from src.infrastructure.db.database import get_db
    from datetime import datetime, timezone

    dummy_session = Session(
        id="sess_100",
        user_id="test_user",
        title="Test Session",
    )
    dummy_file = SessionFile(
        id="f_1",
        session_id="sess_100",
        user_id="test_user",
        file_name="index.html",
        file_path="index.html",
        file_size=1024,
        mime_type="text/html",
        category="html",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    mock_db = AsyncMock()
    app.dependency_overrides[get_current_user_id] = lambda: "test_user"
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock repository behavior
    mock_file_repo = AsyncMock()
    mock_file_repo.list_by_session.return_value = ([dummy_file], 1)
    mock_file_repo.get_by_id.return_value = dummy_file
    mock_session_repo = AsyncMock()
    mock_session_repo.get_by_id.return_value = dummy_session

    from unittest.mock import patch
    with patch("src.interface.routers.file.FileRepository", return_value=mock_file_repo), \
         patch("src.interface.routers.file.SessionRepository", return_value=mock_session_repo):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. List files
            resp = await ac.get("/sessions/sess_100/files")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["items"][0]["file_name"] == "index.html"
            assert "/preview" in data["items"][0]["preview_url"]

            # 2. Get file metadata
            resp = await ac.get("/sessions/sess_100/files/f_1")
            assert resp.status_code == 200
            assert resp.json()["id"] == "f_1"

    app.dependency_overrides.clear()

