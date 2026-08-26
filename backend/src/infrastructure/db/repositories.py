from typing import cast, Optional
from datetime import datetime, timezone
from sqlalchemy import select, update, func
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.db.models import (
    UserModel, SessionModel, MessageModel,
    TaskModel, TaskStepModel, TaskCheckpointModel, HitlRequestModel,
    EcosystemConfigModel, FileModel, FileVersionModel,
)
from src.domain.entities.models import (
    User, Session, Message, Task, TaskStep, Checkpoint, HitlRequest,
    SessionFile, FileVersion,
)
from src.domain.repositories.user import IUserRepository
from src.domain.repositories.session import ISessionRepository, IMessageRepository
from src.domain.repositories.task import ITaskRepository, ITaskStepRepository, ICheckpointRepository
from src.domain.repositories.hitl import IHitlRepository
from src.domain.repositories.file import IFileRepository


# ─── Mappers ──────────────────────────────────────────────────

def to_user(m: UserModel) -> User:
    return User(
        id=m.id,
        email=m.email,
        password_hash=m.hashed_password,
        display_name=m.display_name,
        plan=m.plan,
        max_concurrent_tasks=m.max_concurrent_tasks,
        status=m.status,
        created_at=m.created_at,
    )


def to_session(m: SessionModel) -> Session:
    return Session(id=m.id, user_id=m.user_id, title=m.title,
                   status=m.status, agent_config=m.agent_config or {},
                   message_count=m.message_count,
                   last_message_at=m.last_message_at, created_at=m.created_at)


def to_message(m: MessageModel) -> Message:
    return Message(id=m.id, session_id=m.session_id, role=m.role,
                   content_type=m.content_type, content=m.content or {},
                   task_id=m.task_id, status=m.status,
                   seq=m.seq, created_at=m.created_at)


def to_task(m: TaskModel) -> Task:
    return Task(id=m.id, user_id=m.user_id, session_id=m.session_id,
                trigger_message_id=m.trigger_message_id, title=m.title,
                input=m.input or {}, status=m.status, priority=m.priority,
                worker_id=m.worker_id, worker_heartbeat=m.worker_heartbeat,
                result=m.result, error=m.error, created_at=m.created_at,
                started_at=m.started_at, completed_at=m.completed_at)


def to_step(m: TaskStepModel) -> TaskStep:
    return TaskStep(id=m.id, task_id=m.task_id, step_index=m.step_index,
                    type=m.type, content=m.content or {}, created_at=m.created_at)


def to_checkpoint(m: TaskCheckpointModel) -> Checkpoint:
    return Checkpoint(task_id=m.task_id,
                      last_completed_step=m.last_completed_step,
                      version=m.version,
                      recent_messages=m.recent_messages or [],
                      context_summary=m.context_summary,
                      task_variables=m.task_variables or {},
                      completed_tool_calls=m.completed_tool_calls or [])


def to_file(m: FileModel) -> SessionFile:
    return SessionFile(
        id=m.id,
        session_id=m.session_id,
        user_id=m.user_id,
        file_name=m.file_name,
        file_path=m.file_path,
        file_size=m.file_size,
        mime_type=m.mime_type,
        category=m.category,
        storage_type=m.storage_type,
        task_id=m.task_id,
        storage_key=m.storage_key,
        is_deleted=m.is_deleted,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


# ─── Repositories ─────────────────────────────────────────────
class UserRepository(IUserRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(select(UserModel).where(UserModel.id == user_id))
        m = result.scalar_one_or_none()
        return to_user(m) if m else None

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(UserModel).where(UserModel.email == email))
        m = result.scalar_one_or_none()
        return to_user(m) if m else None

    async def get_model_by_email(self, email: str) -> Optional[UserModel]:
        result = await self.db.execute(select(UserModel).where(UserModel.email == email))
        return result.scalar_one_or_none()

    async def create(self, email: str, password_hash: str = "", display_name: Optional[str] = None, hashed_password: Optional[str] = None) -> User:
        pw = hashed_password or password_hash
        m = UserModel(email=email, hashed_password=pw, display_name=display_name)
        self.db.add(m)
        await self.db.flush()
        return to_user(m)


class SessionRepository(ISessionRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: str, title: Optional[str] = "新会话", agent_config: Optional[dict] = None) -> Session:
        m = SessionModel(user_id=user_id, title=title, agent_config=agent_config or {})
        self.db.add(m)
        await self.db.flush()
        return to_session(m)

    async def list_by_user(self, user_id: str, limit: int = 20) -> list[Session]:
        result = await self.db.execute(
            select(SessionModel)
            .where(SessionModel.user_id == user_id, SessionModel.status == "active")
            .order_by(
                func.coalesce(SessionModel.last_message_at, SessionModel.created_at).desc(),
                SessionModel.created_at.desc(),
            )
            .limit(limit)
        )
        return [to_session(m) for m in result.scalars().all()]

    async def get_by_id(self, session_id: str) -> Session | None:
        result = await self.db.execute(select(SessionModel).where(SessionModel.id == session_id))
        m = result.scalar_one_or_none()
        return to_session(m) if m else None

    async def increment_message_count(self, session_id: str):
        await self.db.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(message_count=SessionModel.message_count + 1, last_message_at=func.now())
        )


class MessageRepository(IMessageRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_user_message(self, session_id: str, text: str) -> Message:
        return await self.create(
            session_id=session_id,
            role="USER",
            content={"text": text},
            content_type="text",
            status="done",
        )

    async def create_agent_placeholder(self, session_id: str, task_id: str) -> Message:
        return await self.create(
            session_id=session_id,
            role="AGENT",
            content_type="task_reference",
            content={
                "text": "好的，我已开始执行这个任务，请稍候...",
                "task_id": task_id,
                "task_status": "PENDING",
            },
            task_id=task_id,
            status="streaming",
        )

    async def create(self, session_id: str, role: str, content: dict,
                     content_type: str = "text", task_id: str | None = None,
                     status: str = "done") -> Message:
        m = MessageModel(session_id=session_id, role=role, content=content,
                         content_type=content_type, task_id=task_id, status=status)
        self.db.add(m)

        # 同步递增所属会话的消息计数，并更新活跃时间
        await self.db.execute(
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(
                message_count=SessionModel.message_count + 1,
                last_message_at=func.now(),
            )
        )

        await self.db.flush()
        return to_message(m)

    async def list_by_session(self, session_id: str, after_seq: int = 0, limit: int = 50) -> list[Message]:
        result = await self.db.execute(
            select(MessageModel)
            .where(MessageModel.session_id == session_id, MessageModel.seq > after_seq)
            .order_by(MessageModel.seq)
            .limit(limit)
        )
        return [to_message(m) for m in result.scalars().all()]

    async def update_content(self, message_id: str, content: dict):
        await self.db.execute(
            update(MessageModel).where(MessageModel.id == message_id).values(content=content)
        )

    async def update_message(self, message_id: str, **kwargs):
        await self.db.execute(
            update(MessageModel).where(MessageModel.id == message_id).values(**kwargs)
        )

    async def get_by_task_id(self, task_id: str) -> Message | None:
        result = await self.db.execute(
            select(MessageModel).where(MessageModel.task_id == task_id, MessageModel.role == "AGENT")
        )
        m = result.scalar_one_or_none()
        return to_message(m) if m else None


class TaskRepository(ITaskRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, user_id: str, input_data: dict, session_id: str | None = None,
                     title: str | None = None, priority: int = 0,
                     trigger_message_id: str | None = None) -> Task:
        m = TaskModel(user_id=user_id, session_id=session_id,
                      title=title, input=input_data, priority=priority,
                      trigger_message_id=trigger_message_id)
        self.db.add(m)
        await self.db.flush()
        return to_task(m)

    async def get_by_id(self, task_id: str) -> Task | None:
        result = await self.db.execute(select(TaskModel).where(TaskModel.id == task_id))
        m = result.scalar_one_or_none()
        return to_task(m) if m else None

    async def get_active_by_session(self, session_id: str) -> Optional[Task]:
        """查询该会话下是否有未完结的任务（PENDING / RUNNING / WAITING_HUMAN / PAUSED）"""
        result = await self.db.execute(
            select(TaskModel).where(
                TaskModel.session_id == session_id,
                TaskModel.status.in_(["PENDING", "RUNNING", "WAITING_HUMAN", "PAUSED"])
            ).limit(1)
        )
        m = result.scalar_one_or_none()
        return to_task(m) if m else None

    async def get_active_in_session(self, session_id: str) -> Optional[Task]:
        return await self.get_active_by_session(session_id)

    async def count_active_by_user(self, user_id: str) -> int:
        """统计当前用户全局并发中的任务数量"""
        result = await self.db.execute(
            select(func.count(TaskModel.id)).where(
                TaskModel.user_id == user_id,
                TaskModel.status.in_(["PENDING", "RUNNING", "WAITING_HUMAN"])
            )
        )
        return result.scalar() or 0

    async def update_status(self, task_id: str, status: str, **kwargs) -> Optional[Task]:
        await self.db.execute(
            update(TaskModel).where(TaskModel.id == task_id).values(status=status, **kwargs)
        )
        await self.db.flush()
        return await self.get_by_id(task_id)

    async def find_zombie_tasks(self, heartbeat_before: datetime) -> list[Task]:
        result = await self.db.execute(
            select(TaskModel).where(
                TaskModel.status == "RUNNING",
                TaskModel.worker_heartbeat < heartbeat_before,
            )
        )
        return [to_task(m) for m in result.scalars().all()]

    async def list_zombie_tasks(self, timeout_seconds: int = 60) -> list[Task]:
        """查询心跳超时的僵尸任务（RUNNING 且心跳超时）"""
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        return await self.find_zombie_tasks(cutoff)

    async def list_paused_for_recovery(self) -> list[Task]:
        """查询因 Worker 优雅退出而暂停的任务"""
        result = await self.db.execute(
            select(TaskModel).where(
                TaskModel.status == "PAUSED",
                TaskModel.paused_reason == "worker_shutdown"
            )
        )
        return [to_task(m) for m in result.scalars().all()]

    async def list_paused_shutdown_tasks(self) -> list[Task]:
        return await self.list_paused_for_recovery()

    async def set_trigger_message(self, task_id: str, message_id: str):
        await self.db.execute(
            update(TaskModel).where(TaskModel.id == task_id).values(trigger_message_id=message_id)
        )


class TaskStepRepository(ITaskStepRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, task_id: str, step_index: int, step_type: str, content: dict) -> TaskStep:
        m = TaskStepModel(task_id=task_id, step_index=step_index, type=step_type, content=content)
        self.db.add(m)
        await self.db.flush()
        return to_step(m)

    async def list_after(self, task_id: str, after_index: int = 0) -> list[TaskStep]:
        result = await self.db.execute(
            select(TaskStepModel)
            .where(TaskStepModel.task_id == task_id, TaskStepModel.step_index > after_index)
            .order_by(TaskStepModel.step_index)
        )
        return [to_step(m) for m in result.scalars().all()]


class CheckpointRepository(ICheckpointRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, task_id: str) -> Checkpoint:
        m = TaskCheckpointModel(task_id=task_id)
        self.db.add(m)
        await self.db.flush()
        return to_checkpoint(m)

    async def get_by_task(self, task_id: str) -> Optional[Checkpoint]:
        result = await self.db.execute(
            select(TaskCheckpointModel).where(TaskCheckpointModel.task_id == task_id)
        )
        m = result.scalar_one_or_none()
        return to_checkpoint(m) if m else None

    async def update(
        self,
        task_id: str,
        last_step: int,
        expected_version: int,
        recent_messages: Optional[list] = None,
        context_summary: Optional[str] = None,
        task_variables: Optional[dict] = None,
        completed_tool_calls: Optional[list] = None,
    ) -> bool:
        values: dict = {
            "last_completed_step": last_step,
            "version": expected_version + 1,
            "updated_at": func.now(),
        }
        if recent_messages is not None:
            values["recent_messages"] = recent_messages
        if context_summary is not None:
            values["context_summary"] = context_summary
        if task_variables is not None:
            values["task_variables"] = task_variables
        if completed_tool_calls is not None:
            values["completed_tool_calls"] = completed_tool_calls

        result = cast(CursorResult, await self.db.execute(
            update(TaskCheckpointModel)
            .where(
                TaskCheckpointModel.task_id == task_id,
                TaskCheckpointModel.version == expected_version,
            )
            .values(**values)
        ))
        return result.rowcount > 0


# ─── HitlRepository ───────────────────────────────────────────

def to_hitl(m: HitlRequestModel) -> HitlRequest:
    return HitlRequest(
        id=m.id,
        task_id=m.task_id,
        step_index=m.step_index,
        type=m.type,
        question=m.question,
        options=m.options,
        default_action=m.default_action or "cancel",
        status=m.status,
        expires_at=m.expires_at,
        user_decision=m.user_decision,
        user_input=m.user_input,
        responded_at=m.responded_at,
        created_at=m.created_at,
    )


class HitlRepository(IHitlRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pending_by_task(self, task_id: str) -> HitlRequest | None:
        from datetime import datetime, timezone
        result = await self.db.execute(
            select(HitlRequestModel)
            .where(HitlRequestModel.task_id == task_id,
                   HitlRequestModel.status == "PENDING")
            .order_by(HitlRequestModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return to_hitl(m) if m else None

    async def get_by_id(self, hitl_id: str) -> HitlRequest | None:
        result = await self.db.execute(
            select(HitlRequestModel).where(HitlRequestModel.id == hitl_id)
        )
        m = result.scalar_one_or_none()
        return to_hitl(m) if m else None

    async def list_expired_requests(self) -> list[HitlRequest]:
        """查询所有超时未响应的 PENDING HITL 请求"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(HitlRequestModel).where(
                HitlRequestModel.status == "PENDING",
                HitlRequestModel.expires_at < now
            )
        )
        return [to_hitl(m) for m in result.scalars().all()]

    async def mark_expired(self, hitl_id: str):
        await self.db.execute(
            update(HitlRequestModel)
            .where(HitlRequestModel.id == hitl_id)
            .values(status="EXPIRED")
        )

    async def resolve(self, hitl_id: str, decision: str, user_input: dict | None = None):
        from datetime import datetime, timezone
        await self.db.execute(
            update(HitlRequestModel)
            .where(HitlRequestModel.id == hitl_id)
            .values(
                status="RESOLVED",
                user_decision=decision,
                user_input=user_input,
                responded_at=datetime.now(timezone.utc),
            )
        )


class EcosystemConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_by_user(self, user_id: str, type: str | None = None) -> list[EcosystemConfigModel]:
        stmt = select(EcosystemConfigModel).where(EcosystemConfigModel.user_id == user_id)
        if type:
            stmt = stmt.where(EcosystemConfigModel.type == type)
        stmt = stmt.order_by(EcosystemConfigModel.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, config_id: str, user_id: str | None = None) -> EcosystemConfigModel | None:
        stmt = select(EcosystemConfigModel).where(EcosystemConfigModel.id == config_id)
        if user_id:
            stmt = stmt.where(EcosystemConfigModel.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: str,
        type: str,
        name: str,
        transport: str = "sse",
        server_url: str | None = None,
        command: str | None = None,
        args: list[str] | None = None,
        namespace: str = "custom",
        description: str | None = None,
        cached_tools: list[dict] | None = None,
    ) -> EcosystemConfigModel:
        model = EcosystemConfigModel(
            user_id=user_id,
            type=type,
            name=name,
            transport=transport,
            server_url=server_url,
            command=command,
            args=args or [],
            namespace=namespace,
            description=description,
            cached_tools=cached_tools or [],
            enabled=True,
        )
        self.db.add(model)
        await self.db.flush()
        return model

    async def delete(self, config_id: str, user_id: str) -> bool:
        stmt = select(EcosystemConfigModel).where(
            EcosystemConfigModel.id == config_id,
            EcosystemConfigModel.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        m = result.scalar_one_or_none()
        if m:
            await self.db.delete(m)
            await self.db.flush()
            return True
        return False


class FileRepository(IFileRepository):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(
        self,
        session_id: str,
        user_id: str,
        file_path: str,
        file_name: str,
        file_size: int,
        mime_type: str,
        category: str,
        storage_type: str = "sandbox",
        task_id: Optional[str] = None,
        storage_key: Optional[str] = None,
    ) -> SessionFile:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = (
            pg_insert(FileModel)
            .values(
                session_id=session_id,
                user_id=user_id,
                file_path=file_path,
                file_name=file_name,
                file_size=file_size,
                mime_type=mime_type,
                category=category,
                storage_type=storage_type,
                task_id=task_id,
                storage_key=storage_key,
                is_deleted=False,
            )
            .on_conflict_do_update(
                constraint="uq_session_file_path",
                set_={
                    "file_name": file_name,
                    "file_size": file_size,
                    "mime_type": mime_type,
                    "category": category,
                    "storage_type": storage_type,
                    "task_id": task_id,
                    "storage_key": storage_key,
                    "is_deleted": False,
                    "updated_at": func.now(),
                },
            )
            .returning(FileModel)
        )
        result = await self.db.execute(stmt)
        m = result.scalar_one()
        return to_file(m)

    async def list_by_session(
        self,
        session_id: str,
        category: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[SessionFile], int]:
        conditions = [
            FileModel.session_id == session_id,
            FileModel.is_deleted == False,
        ]
        if category and category != "all":
            conditions.append(FileModel.category == category)

        # 统计总数
        count_stmt = select(func.count(FileModel.id)).where(*conditions)
        count_res = await self.db.execute(count_stmt)
        total = count_res.scalar() or 0

        # 分页查询
        query = (
            select(FileModel)
            .where(*conditions)
            .order_by(FileModel.updated_at.desc(), FileModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.db.execute(query)
        items = [to_file(m) for m in res.scalars().all()]
        return items, total

    async def get_by_id(self, file_id: str) -> Optional[SessionFile]:
        res = await self.db.execute(
            select(FileModel).where(FileModel.id == file_id, FileModel.is_deleted == False)
        )
        m = res.scalar_one_or_none()
        return to_file(m) if m else None

    async def get_by_path(self, session_id: str, file_path: str) -> Optional[SessionFile]:
        res = await self.db.execute(
            select(FileModel).where(
                FileModel.session_id == session_id,
                FileModel.file_path == file_path,
                FileModel.is_deleted == False,
            )
        )
        m = res.scalar_one_or_none()
        return to_file(m) if m else None

    async def delete_by_id(self, file_id: str) -> bool:
        stmt = (
            update(FileModel)
            .where(FileModel.id == file_id)
            .values(is_deleted=True, updated_at=func.now())
        )
        res = cast(CursorResult, await self.db.execute(stmt))
        return (res.rowcount or 0) > 0


def to_file_version(m: FileVersionModel) -> FileVersion:
    return FileVersion(
        id=m.id,
        file_id=m.file_id,
        session_id=m.session_id,
        task_id=m.task_id,
        version_num=m.version_num,
        file_size=m.file_size,
        diff_content=m.diff_content,
        storage_key=m.storage_key,
        summary=m.summary,
        created_at=m.created_at,
    )


class FileVersionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        file_id: str,
        session_id: str,
        version_num: int,
        file_size: int,
        task_id: Optional[str] = None,
        diff_content: Optional[str] = None,
        storage_key: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> FileVersion:
        model = FileVersionModel(
            file_id=file_id,
            session_id=session_id,
            task_id=task_id,
            version_num=version_num,
            file_size=file_size,
            diff_content=diff_content,
            storage_key=storage_key,
            summary=summary,
        )
        self.db.add(model)
        await self.db.flush()
        return to_file_version(model)

    async def list_by_file_id(self, file_id: str) -> list[FileVersion]:
        stmt = (
            select(FileVersionModel)
            .where(FileVersionModel.file_id == file_id)
            .order_by(FileVersionModel.version_num.desc())
        )
        res = await self.db.execute(stmt)
        return [to_file_version(m) for m in res.scalars().all()]

    async def get_by_id(self, version_id: str) -> Optional[FileVersion]:
        stmt = select(FileVersionModel).where(FileVersionModel.id == version_id)
        res = await self.db.execute(stmt)
        m = res.scalar_one_or_none()
        return to_file_version(m) if m else None

    async def get_latest_version(self, file_id: str) -> Optional[FileVersion]:
        stmt = (
            select(FileVersionModel)
            .where(FileVersionModel.file_id == file_id)
            .order_by(FileVersionModel.version_num.desc())
            .limit(1)
        )
        res = await self.db.execute(stmt)
        m = res.scalar_one_or_none()
        return to_file_version(m) if m else None


