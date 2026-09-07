import uuid
import mimetypes
from typing import Optional
from sqlalchemy import select, func
from src.infrastructure.db.database import AsyncSessionLocal
from src.infrastructure.db.models import FileModel, FileVersionModel


def infer_file_category(file_name: str) -> tuple[str, str]:
    """推断文件分类与 MIME 类型"""
    mime_type, _ = mimetypes.guess_type(file_name)
    mime_type = mime_type or "text/plain"

    ext = file_name.split(".")[-1].lower() if "." in file_name else ""
    if ext in ("html", "htm"):
        category = "html"
        mime_type = "text/html"
    elif ext in ("py", "js", "ts", "tsx", "jsx", "json", "sh", "sql", "css", "yaml", "yml"):
        category = "code"
    elif ext in ("png", "jpg", "jpeg", "gif", "svg", "webp"):
        category = "image"
    elif ext in ("csv", "xlsx", "parquet"):
        category = "data"
    else:
        category = "document"

    return category, mime_type


async def record_sandbox_file(
    thread_id: Optional[str],
    file_path: str,
    content: str,
    user_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> bool:
    """
    当 Agent 执行 sandbox_write_file 成功时，通过 SQLAlchemy ORM 持久化写入 files 和 file_versions 表
    """
    if not thread_id or not file_path:
        return False

    file_name = file_path.split("/")[-1]
    file_size = len(content.encode("utf-8"))
    category, mime_type = infer_file_category(file_name)

    try:
        async with AsyncSessionLocal() as session:
            # 1. 确定归属用户 ID（若为默认值或未显式指定，从 sessions 反查真实用户）
            effective_user_id = user_id
            if not effective_user_id or effective_user_id in ("default_user", "local_user", "user_test"):
                from sqlalchemy import text
                s_res = await session.execute(
                    text("SELECT user_id FROM sessions WHERE id = :sid"), {"sid": str(thread_id)}
                )
                row = s_res.fetchone()
                if row and row[0]:
                    effective_user_id = row[0]
                else:
                    u_res = await session.execute(text("SELECT id FROM users LIMIT 1"))
                    urow = u_res.fetchone()
                    effective_user_id = urow[0] if urow else str(uuid.uuid4())

            # 2. 通过 ORM 查询是否已存在该文件记录
            stmt = select(FileModel).where(
                FileModel.session_id == str(thread_id),
                FileModel.file_path == file_path,
            )
            res = await session.execute(stmt)
            file_obj = res.scalar_one_or_none()

            if not file_obj:
                file_obj = FileModel(
                    id=str(uuid.uuid4()),
                    session_id=str(thread_id),
                    user_id=str(effective_user_id),
                    task_id=task_id,
                    file_name=file_name,
                    file_path=file_path,
                    file_size=file_size,
                    mime_type=mime_type,
                    category=category,
                    storage_type="sandbox",
                    is_deleted=False,
                )
                session.add(file_obj)
                await session.flush()
            else:
                file_obj.file_name = file_name
                file_obj.file_size = file_size
                file_obj.mime_type = mime_type
                file_obj.category = category
                file_obj.task_id = task_id
                file_obj.is_deleted = False

            # 3. 统计现有版本并创建新版本实体
            v_stmt = select(func.coalesce(func.max(FileVersionModel.version_num), 0)).where(
                FileVersionModel.file_id == file_obj.id
            )
            v_res = await session.execute(v_stmt)
            curr_max_v = v_res.scalar() or 0
            next_version = curr_max_v + 1

            version_obj = FileVersionModel(
                id=str(uuid.uuid4()),
                file_id=file_obj.id,
                session_id=str(thread_id),
                task_id=task_id,
                version_num=next_version,
                file_size=file_size,
                summary=f"Agent 生成文件 (v{next_version}, {file_size} 字节)",
            )
            session.add(version_obj)

            await session.commit()
            print(
                f"[agent-runtime-orm] Successfully recorded file into PostgreSQL via ORM: {file_path} "
                f"(session={thread_id}, v={next_version}, size={file_size}B)"
            )
            return True

    except Exception as exc:
        print(f"[agent-runtime-orm] Warning: Failed to record file to PostgreSQL ({file_path}): {exc}")
        return False
