import uuid
from datetime import datetime
from sqlalchemy import (
    String, Text, Integer, BigInteger, Boolean,
    DateTime, ForeignKey, UniqueConstraint, Index,
    func, Identity,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def gen_uuid():
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# users
# ─────────────────────────────────────────────────────────────
class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    plan: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    max_concurrent_tasks: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    sessions: Mapped[list["SessionModel"]] = relationship(back_populates="user")


# ─────────────────────────────────────────────────────────────
# sessions
# ─────────────────────────────────────────────────────────────
class SessionModel(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    agent_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user: Mapped["UserModel"] = relationship(back_populates="sessions")
    messages: Mapped[list["MessageModel"]] = relationship(back_populates="session")
    files: Mapped[list["FileModel"]] = relationship(back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_sessions_user_active", "user_id", "last_message_at"),
    )


# ─────────────────────────────────────────────────────────────
# messages
# ─────────────────────────────────────────────────────────────
class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)           # USER / AGENT / SYSTEM
    content_type: Mapped[str] = mapped_column(String(30), default="text", nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="done", nullable=False)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session: Mapped["SessionModel"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("idx_messages_session_seq", "session_id", "seq"),
        Index("idx_messages_task_id", "task_id"),
    )


# ─────────────────────────────────────────────────────────────
# tasks
# ─────────────────────────────────────────────────────────────
class TaskModel(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("sessions.id"), nullable=True)
    trigger_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255))
    input: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="PENDING", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(100))
    worker_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    paused_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    steps: Mapped[list["TaskStepModel"]] = relationship(back_populates="task")
    checkpoint: Mapped["TaskCheckpointModel | None"] = relationship(back_populates="task", uselist=False)

    __table_args__ = (
        Index("idx_tasks_user_id", "user_id"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_worker_heartbeat", "worker_heartbeat"),
    )


# ─────────────────────────────────────────────────────────────
# task_steps
# ─────────────────────────────────────────────────────────────
class TaskStepModel(Base):
    __tablename__ = "task_steps"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)   # THINKING / TOOL_CALL / TOOL_RESULT / HITL_REQUEST / FINAL
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    task: Mapped["TaskModel"] = relationship(back_populates="steps")

    __table_args__ = (
        UniqueConstraint("task_id", "step_index", name="uq_task_step"),
        Index("idx_task_steps_task_id", "task_id"),
    )


# ─────────────────────────────────────────────────────────────
# task_checkpoints
# ─────────────────────────────────────────────────────────────
class TaskCheckpointModel(Base):
    __tablename__ = "task_checkpoints"

    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    last_completed_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recent_messages: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    context_summary: Mapped[str | None] = mapped_column(Text)
    task_variables: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    completed_tool_calls: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    task: Mapped["TaskModel"] = relationship(back_populates="checkpoint")


# ─────────────────────────────────────────────────────────────
# hitl_requests
# ─────────────────────────────────────────────────────────────
class HitlRequestModel(Base):
    __tablename__ = "hitl_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)   # choice / text_input / file_upload / form
    question: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB)
    default_action: Mapped[str] = mapped_column(String(20), default="cancel", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_decision: Mapped[str | None] = mapped_column(String(100))
    user_input: Mapped[dict | None] = mapped_column(JSONB)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_hitl_task_id", "task_id"),
        Index("idx_hitl_status_expires", "status", "expires_at"),
    )


# ─────────────────────────────────────────────────────────────
# ecosystem_configs (MCP & A2A per user persistence)
# ─────────────────────────────────────────────────────────────
class EcosystemConfigModel(Base):
    __tablename__ = "ecosystem_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # "mcp" or "a2a"
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    transport: Mapped[str] = mapped_column(String(20), default="sse", nullable=False)  # "stdio", "sse", "https"
    server_url: Mapped[str | None] = mapped_column(String(500))
    command: Mapped[str | None] = mapped_column(String(200))
    args: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    namespace: Mapped[str] = mapped_column(String(50), default="custom", nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cached_tools: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_ecosystem_user_type", "user_id", "type"),
    )


# ─────────────────────────────────────────────────────────────
# files (Session files & outputs)
# ─────────────────────────────────────────────────────────────
class FileModel(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream", nullable=False)
    category: Mapped[str] = mapped_column(String(50), default="document", nullable=False)  # html / image / code / document / data
    storage_type: Mapped[str] = mapped_column(String(50), default="sandbox", nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    session: Mapped["SessionModel"] = relationship(back_populates="files")
    versions: Mapped[list["FileVersionModel"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="desc(FileVersionModel.version_num)",
    )

    __table_args__ = (
        UniqueConstraint("session_id", "file_path", name="uq_session_file_path"),
        Index("idx_files_session_category", "session_id", "category"),
        Index("idx_files_session_created", "session_id", "created_at"),
        Index("idx_files_user_id", "user_id"),
    )


# ─────────────────────────────────────────────────────────────
# file_versions (Version history & unified diffs)
# ─────────────────────────────────────────────────────────────
class FileVersionModel(Base):
    __tablename__ = "file_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    file_id: Mapped[str] = mapped_column(String(36), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    version_num: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    diff_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    file: Mapped["FileModel"] = relationship(back_populates="versions")

    __table_args__ = (
        UniqueConstraint("file_id", "version_num", name="uq_file_version_num"),
        Index("idx_file_versions_file_id", "file_id"),
        Index("idx_file_versions_session_id", "session_id"),
    )


