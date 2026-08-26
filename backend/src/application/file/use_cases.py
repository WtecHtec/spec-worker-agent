import mimetypes
import os
from pathlib import Path
from typing import Optional, AsyncGenerator, Any
import httpx
import structlog

from src.domain.entities.models import SessionFile
from src.domain.repositories.file import IFileRepository
from src.domain.repositories.session import ISessionRepository
from src.domain.exceptions import (
    SessionNotFoundException,
    FileNotFoundException,
    ForbiddenAccessException,
)
from src.config.settings import get_settings
from src.infrastructure.sandbox.client import SandboxClient, get_sandbox_client

logger = structlog.get_logger()


def detect_category_and_mime(file_path: str) -> tuple[str, str]:
    """根据文件扩展名推断 category 分类和 mime_type"""
    ext = Path(file_path).suffix.lower()
    
    # 常用 MIME 兜底与规范映射
    custom_mimes = {
        ".html": ("html", "text/html; charset=utf-8"),
        ".htm": ("html", "text/html; charset=utf-8"),
        ".png": ("image", "image/png"),
        ".jpg": ("image", "image/jpeg"),
        ".jpeg": ("image", "image/jpeg"),
        ".gif": ("image", "image/gif"),
        ".svg": ("image", "image/svg+xml"),
        ".webp": ("image", "image/webp"),
        ".ico": ("image", "image/x-icon"),
        ".md": ("document", "text/markdown; charset=utf-8"),
        ".txt": ("document", "text/plain; charset=utf-8"),
        ".csv": ("document", "text/csv; charset=utf-8"),
        ".pdf": ("document", "application/pdf"),
        ".json": ("code", "application/json"),
        ".py": ("code", "text/x-python; charset=utf-8"),
        ".js": ("code", "application/javascript"),
        ".ts": ("code", "application/typescript"),
        ".tsx": ("code", "text/typescript-jsx"),
        ".jsx": ("code", "text/javascript-jsx"),
        ".css": ("code", "text/css"),
        ".yaml": ("code", "text/yaml"),
        ".yml": ("code", "text/yaml"),
        ".sh": ("code", "text/x-sh"),
        ".sql": ("code", "text/x-sql"),
        ".go": ("code", "text/x-go"),
        ".rs": ("code", "text/x-rust"),
        ".zip": ("data", "application/zip"),
        ".tar": ("data", "application/x-tar"),
        ".gz": ("data", "application/gzip"),
    }
    
    if ext in custom_mimes:
        return custom_mimes[ext]

    guessed_mime, _ = mimetypes.guess_type(file_path)
    mime = guessed_mime or "application/octet-stream"

    if mime.startswith("image/"):
        return "image", mime
    elif mime.startswith("text/"):
        return "document", f"{mime}; charset=utf-8"
    else:
        return "document", mime


class ListSessionFilesUseCase:
    """获取指定会话下的产出文件列表"""

    def __init__(self, file_repo: IFileRepository, session_repo: ISessionRepository):
        self.file_repo = file_repo
        self.session_repo = session_repo

    async def execute(
        self,
        session_id: str,
        user_id: str,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SessionFile], int]:
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            raise SessionNotFoundException(session_id)
        if session.user_id != user_id:
            raise ForbiddenAccessException("You do not have permission to access this session's files")

        return await self.file_repo.list_by_session(
            session_id=session_id, category=category, limit=limit, offset=offset
        )


class GetFileMetadataUseCase:
    """获取单个文件的详细信息"""

    def __init__(self, file_repo: IFileRepository, session_repo: ISessionRepository):
        self.file_repo = file_repo
        self.session_repo = session_repo

    async def execute(self, file_id: str, user_id: str) -> SessionFile:
        file = await self.file_repo.get_by_id(file_id)
        if not file:
            raise FileNotFoundException(file_id)
        if file.user_id != user_id:
            raise ForbiddenAccessException("Access denied")
        return file


class DeleteFileUseCase:
    """软删除或物理删除文件"""

    def __init__(self, file_repo: IFileRepository):
        self.file_repo = file_repo

    async def execute(self, file_id: str, user_id: str) -> bool:
        file = await self.file_repo.get_by_id(file_id)
        if not file:
            raise FileNotFoundException(file_id)
        if file.user_id != user_id:
            raise ForbiddenAccessException("Access denied")
        return await self.file_repo.delete_by_id(file_id)


class RecordFileUseCase:
    """记录/更新产出的文件"""

    def __init__(self, file_repo: IFileRepository):
        self.file_repo = file_repo

    async def execute(
        self,
        session_id: str,
        user_id: str,
        file_path: str,
        file_size: int = 0,
        mime_type: Optional[str] = None,
        category: Optional[str] = None,
        storage_type: str = "sandbox",
        task_id: Optional[str] = None,
        storage_key: Optional[str] = None,
    ) -> SessionFile:
        inferred_category, inferred_mime = detect_category_and_mime(file_path)
        final_category = category or inferred_category
        final_mime = mime_type or inferred_mime
        file_name = Path(file_path).name or file_path

        return await self.file_repo.upsert(
            session_id=session_id,
            user_id=user_id,
            file_path=file_path,
            file_name=file_name,
            file_size=file_size,
            mime_type=final_mime,
            category=final_category,
            storage_type=storage_type,
            task_id=task_id,
            storage_key=storage_key,
        )


class StreamFileContentUseCase:
    """
    通过代理流方式从沙箱（或本地工作区）读取文件二进制/文本内容，
    隔离内网沙箱环境，保护数据安全。
    """

    def __init__(
        self,
        file_repo: IFileRepository,
        session_repo: ISessionRepository,
        sandbox_client: Optional[SandboxClient] = None,
    ):
        self.file_repo = file_repo
        self.session_repo = session_repo
        self.sandbox_client = sandbox_client or get_sandbox_client()
        self.settings = get_settings()

    async def execute(
        self, file_id: str, user_id: str
    ) -> tuple[AsyncGenerator[bytes, None], SessionFile]:
        file = await self.file_repo.get_by_id(file_id)
        if not file:
            raise FileNotFoundException(file_id)
        if file.user_id != user_id:
            raise ForbiddenAccessException("Access denied")

        # 1. 优先从沙箱服务拉取原始流 (/fs/raw?path=...)
        if self.settings.sandbox_enabled and await self.sandbox_client.health_check():
            sandbox_raw_url = f"{self.sandbox_client.base_url.rstrip('/')}/fs/raw?path={file.file_path}"

            async def sandbox_stream_generator() -> AsyncGenerator[bytes, None]:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("GET", sandbox_raw_url) as resp:
                        if resp.status_code != 200:
                            logger.error("failed_to_stream_from_sandbox", status=resp.status_code, path=file.file_path)
                            yield f"Error: Failed to stream file from sandbox (HTTP {resp.status_code})".encode("utf-8")
                            return
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            yield chunk

            return sandbox_stream_generator(), file

        # 2. 本地回退工作区流式读取（优先在 sessions/{session_id} 下检索）
        workspace_dir = Path(self.settings.llm_workspace_dir).resolve()
        safe_path = (workspace_dir / "sessions" / file.session_id / file.file_path.lstrip("/")).resolve()
        if not (str(safe_path).startswith(str(workspace_dir)) and safe_path.exists()):
            # 回退兼容全局根目录
            safe_path = (workspace_dir / file.file_path.lstrip("/")).resolve()
            if not str(safe_path).startswith(str(workspace_dir)) or not safe_path.exists():
                raise FileNotFoundException(f"Physical file not found: {file.file_path}")

        async def local_stream_generator() -> AsyncGenerator[bytes, None]:
            with open(safe_path, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk

        return local_stream_generator(), file
