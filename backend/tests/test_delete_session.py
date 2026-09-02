import pytest
from unittest.mock import AsyncMock, MagicMock
from src.application.session.use_cases import DeleteSessionUseCase


@pytest.mark.asyncio
async def test_delete_session_use_case_success():
    """测试: DeleteSessionUseCase 成功删除存在的会话并提交事务"""
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()

    mock_session_repo = MagicMock()
    mock_session_repo.delete = AsyncMock(return_value=True)

    use_case = DeleteSessionUseCase(db=mock_db, session_repo=mock_session_repo)
    result = await use_case.execute(session_id="sess_123", user_id="user_abc")

    assert result is True
    mock_session_repo.delete.assert_awaited_once_with(session_id="sess_123", user_id="user_abc")
    mock_db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_session_use_case_not_found():
    """测试: DeleteSessionUseCase 删除不存在会话时返回 False 且不提交事务"""
    mock_db = MagicMock()
    mock_db.commit = AsyncMock()

    mock_session_repo = MagicMock()
    mock_session_repo.delete = AsyncMock(return_value=False)

    use_case = DeleteSessionUseCase(db=mock_db, session_repo=mock_session_repo)
    result = await use_case.execute(session_id="sess_non_exist", user_id="user_abc")

    assert result is False
    mock_session_repo.delete.assert_awaited_once_with(session_id="sess_non_exist", user_id="user_abc")
    mock_db.commit.assert_not_awaited()
