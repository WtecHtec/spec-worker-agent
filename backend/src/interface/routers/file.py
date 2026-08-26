import urllib.parse
from typing import Optional
from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import FileRepository, SessionRepository, FileVersionRepository
from src.interface.middleware.auth import get_current_user_id
from src.application.file.use_cases import (
    ListSessionFilesUseCase,
    GetFileMetadataUseCase,
    DeleteFileUseCase,
    ListFileVersionsUseCase,
    GetFileVersionDetailUseCase,
    StreamFileContentUseCase,
)

router = APIRouter(prefix="/sessions/{session_id}/files", tags=["files"])


class FileVersionResponse(BaseModel):
    id: str
    file_id: str
    session_id: str
    task_id: Optional[str] = None
    version_num: int
    file_size: int
    diff_content: Optional[str] = None
    summary: Optional[str] = None
    created_at: str


class FileItemResponse(BaseModel):
    id: str
    session_id: str
    user_id: str
    task_id: Optional[str] = None
    file_name: str
    file_path: str
    file_size: int
    mime_type: str
    category: str
    storage_type: str
    preview_url: str
    download_url: str
    created_at: str
    updated_at: str


class FileListResponse(BaseModel):
    total: int
    items: list[FileItemResponse]


@router.get("", response_model=FileListResponse)
async def list_session_files(
    session_id: str,
    category: Optional[str] = Query(None, description="分类过滤: all, html, image, code, document, data"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取指定会话下的产出文件列表"""
    use_case = ListSessionFilesUseCase(
        file_repo=FileRepository(db),
        session_repo=SessionRepository(db),
    )
    files, total = await use_case.execute(
        session_id=session_id,
        user_id=user_id,
        category=category,
        limit=limit,
        offset=offset,
    )

    items = [
        FileItemResponse(
            id=f.id,
            session_id=f.session_id,
            user_id=f.user_id,
            task_id=f.task_id,
            file_name=f.file_name,
            file_path=f.file_path,
            file_size=f.file_size,
            mime_type=f.mime_type,
            category=f.category,
            storage_type=f.storage_type,
            preview_url=f"/sessions/{f.session_id}/files/{f.id}/preview",
            download_url=f"/sessions/{f.session_id}/files/{f.id}/download",
            created_at=f.created_at.isoformat() if f.created_at else "",
            updated_at=f.updated_at.isoformat() if f.updated_at else "",
        )
        for f in files
    ]

    return FileListResponse(total=total, items=items)


@router.get("/{file_id}", response_model=FileItemResponse)
async def get_file_metadata(
    session_id: str,
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取单个文件元数据"""
    use_case = GetFileMetadataUseCase(
        file_repo=FileRepository(db),
        session_repo=SessionRepository(db),
    )
    f = await use_case.execute(file_id=file_id, user_id=user_id)
    return FileItemResponse(
        id=f.id,
        session_id=f.session_id,
        user_id=f.user_id,
        task_id=f.task_id,
        file_name=f.file_name,
        file_path=f.file_path,
        file_size=f.file_size,
        mime_type=f.mime_type,
        category=f.category,
        storage_type=f.storage_type,
        preview_url=f"/sessions/{f.session_id}/files/{f.id}/preview",
        download_url=f"/sessions/{f.session_id}/files/{f.id}/download",
        created_at=f.created_at.isoformat() if f.created_at else "",
        updated_at=f.updated_at.isoformat() if f.updated_at else "",
    )


@router.get("/{file_id}/preview")
async def preview_file(
    session_id: str,
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """通过后端安全代理流式预览文件（在线查看）"""
    use_case = StreamFileContentUseCase(
        file_repo=FileRepository(db),
        session_repo=SessionRepository(db),
    )
    stream_gen, file = await use_case.execute(file_id=file_id, user_id=user_id)

    headers = {
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(
        stream_gen,
        media_type=file.mime_type or "application/octet-stream",
        headers=headers,
    )


@router.get("/{file_id}/download")
async def download_file(
    session_id: str,
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """通过后端安全代理下载文件（触发浏览器下载）"""
    use_case = StreamFileContentUseCase(
        file_repo=FileRepository(db),
        session_repo=SessionRepository(db),
    )
    stream_gen, file = await use_case.execute(file_id=file_id, user_id=user_id)

    # 规范化 RFC 5987 / URL 编码下载文件名，兼容中文及特殊字符
    encoded_filename = urllib.parse.quote(file.file_name)
    headers = {
        "Content-Disposition": f"attachment; filename=\"{encoded_filename}\"; filename*=UTF-8''{encoded_filename}",
        "Cache-Control": "no-cache",
    }
    return StreamingResponse(
        stream_gen,
        media_type=file.mime_type or "application/octet-stream",
        headers=headers,
    )


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    session_id: str,
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """删除文件"""
    use_case = DeleteFileUseCase(file_repo=FileRepository(db))
    await use_case.execute(file_id=file_id, user_id=user_id)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{file_id}/versions", response_model=list[FileVersionResponse])
async def list_file_versions(
    session_id: str,
    file_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取指定文件的所有历史版本记录列表（降序）"""
    use_case = ListFileVersionsUseCase(
        file_repo=FileRepository(db),
        version_repo=FileVersionRepository(db),
    )
    versions = await use_case.execute(file_id=file_id, user_id=user_id)
    return [
        FileVersionResponse(
            id=v.id,
            file_id=v.file_id,
            session_id=v.session_id,
            task_id=v.task_id,
            version_num=v.version_num,
            file_size=v.file_size,
            diff_content=v.diff_content,
            summary=v.summary,
            created_at=v.created_at.isoformat() if v.created_at else "",
        )
        for v in versions
    ]


@router.get("/{file_id}/versions/{version_id}", response_model=FileVersionResponse)
async def get_file_version_detail(
    session_id: str,
    file_id: str,
    version_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """获取指定版本的详细 Diff 内容与元数据"""
    use_case = GetFileVersionDetailUseCase(
        file_repo=FileRepository(db),
        version_repo=FileVersionRepository(db),
    )
    v = await use_case.execute(file_id=file_id, version_id=version_id, user_id=user_id)
    return FileVersionResponse(
        id=v.id,
        file_id=v.file_id,
        session_id=v.session_id,
        task_id=v.task_id,
        version_num=v.version_num,
        file_size=v.file_size,
        diff_content=v.diff_content,
        summary=v.summary,
        created_at=v.created_at.isoformat() if v.created_at else "",
    )
