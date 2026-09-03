import os
import uuid
import mimetypes
from typing import Optional
import psycopg

# 数据库连接串：统一由环境变量 DATABASE_URL 控制
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/app"

def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")


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
    当 Agent 执行 sandbox_write_file 成功时，直接持久化写入 PostgreSQL 中的 files 和 file_versions 表
    """
    if not thread_id or not file_path:
        return False

    db_url = get_database_url()
    file_name = file_path.split("/")[-1]
    file_size = len(content.encode("utf-8"))
    category, mime_type = infer_file_category(file_name)

    try:
        async with await psycopg.AsyncConnection.connect(db_url) as aconn:
            async with aconn.cursor() as cur:
                # 1. 若未显式传入合法 user_id，从 sessions 表中精准反查该 thread 所属用户
                effective_user_id = user_id
                if not effective_user_id or effective_user_id == "default_user":
                    await cur.execute("SELECT user_id FROM sessions WHERE id = %s", (thread_id,))
                    row = await cur.fetchone()
                    if row:
                        effective_user_id = row[0]
                    else:
                        # 若 session 不存在（纯单元测试时），查询一个已存在用户兜底，避免外键异常
                        await cur.execute("SELECT id FROM users LIMIT 1")
                        user_row = await cur.fetchone()
                        effective_user_id = user_row[0] if user_row else str(uuid.uuid4())

                # 2. Upsert 写入 files 表（基于 (session_id, file_path) 唯一约束）
                upsert_file_sql = """
                INSERT INTO files (
                    id, session_id, user_id, task_id, file_name, file_path, file_size,
                    mime_type, category, storage_type, is_deleted, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, 'sandbox', false, NOW(), NOW()
                )
                ON CONFLICT (session_id, file_path) DO UPDATE SET
                    file_name = EXCLUDED.file_name,
                    file_size = EXCLUDED.file_size,
                    mime_type = EXCLUDED.mime_type,
                    category = EXCLUDED.category,
                    task_id = EXCLUDED.task_id,
                    is_deleted = false,
                    updated_at = NOW()
                RETURNING id;
                """
                new_file_id = str(uuid.uuid4())
                await cur.execute(
                    upsert_file_sql,
                    (
                        new_file_id,
                        str(thread_id),
                        str(effective_user_id),
                        task_id,
                        file_name,
                        file_path,
                        file_size,
                        mime_type,
                        category,
                    ),
                )
                file_row = await cur.fetchone()
                actual_file_id = file_row[0] if file_row else new_file_id

                # 3. 记录文件历史版本到 file_versions 表中
                await cur.execute(
                    "SELECT COALESCE(MAX(version_num), 0) FROM file_versions WHERE file_id = %s",
                    (actual_file_id,),
                )
                v_row = await cur.fetchone()
                next_version = (v_row[0] if v_row else 0) + 1

                insert_version_sql = """
                INSERT INTO file_versions (
                    id, file_id, session_id, task_id, version_num, file_size, summary, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, NOW()
                );
                """
                version_id = str(uuid.uuid4())
                summary = f"Agent 生成文件 (v{next_version}, {file_size} 字节)"
                await cur.execute(
                    insert_version_sql,
                    (
                        version_id,
                        actual_file_id,
                        str(thread_id),
                        task_id,
                        next_version,
                        file_size,
                        summary,
                    ),
                )

                await aconn.commit()
                print(
                    f"[agent-runtime-db] Successfully recorded file into PostgreSQL: {file_path} "
                    f"(session={thread_id}, user={effective_user_id}, v={next_version}, size={file_size}B)"
                )
                return True

    except Exception as exc:
        print(f"[agent-runtime-db] Warning: Failed to record file to PostgreSQL ({file_path}): {exc}")
        return False
