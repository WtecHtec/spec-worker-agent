"""
领域实体与值对象（纯业务模型，不依赖 SQLAlchemy，内聚核心业务逻辑与状态机行为）
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class User:
    id: str
    email: str
    password_hash: str
    display_name: Optional[str] = None
    plan: str = "free"
    max_concurrent_tasks: int = 3
    status: str = "active"
    created_at: Optional[datetime] = None

    def can_create_task(self, current_active_tasks: int) -> bool:
        """检查用户当前活跃任务数是否已达上限"""
        return current_active_tasks < self.max_concurrent_tasks


@dataclass
class Session:
    id: str
    user_id: str
    title: str = "新会话"
    agent_config: dict = field(default_factory=dict)
    status: str = "active"
    message_count: int = 0
    last_message_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Message:
    id: str
    session_id: str
    role: str                       # USER / AGENT / SYSTEM
    content_type: str               # text / task_reference / error
    content: dict                   # {"text": "..."} or {"task_id": "...", "task_status": "..."}
    task_id: Optional[str] = None
    status: str = "done"            # done / streaming / failed
    seq: int = 0
    created_at: Optional[datetime] = None

    @property
    def is_agent(self) -> bool:
        return self.role == "AGENT"

    def mark_streaming(self, task_id: str):
        self.status = "streaming"
        self.task_id = task_id
        self.content = {
            **self.content,
            "task_id": task_id,
            "task_status": "PENDING",
        }

    def complete(self, summary: str):
        self.status = "done"
        self.content = {
            **self.content,
            "task_status": "COMPLETED",
            "summary": summary,
        }

    def fail(self, error_message: str):
        self.status = "failed"
        self.content = {
            **self.content,
            "task_status": "FAILED",
            "error": error_message,
        }


@dataclass
class TaskStep:
    id: str
    task_id: str
    step_index: int
    type: str                       # THINKING / TOOL_CALL / TOOL_RESULT / HITL_REQUEST / FINAL
    content: dict
    created_at: Optional[datetime] = None


@dataclass
class Checkpoint:
    task_id: str
    last_completed_step: int = 0
    version: int = 1
    recent_messages: list = field(default_factory=list)
    context_summary: Optional[str] = None
    task_variables: dict = field(default_factory=dict)
    completed_tool_calls: list = field(default_factory=list)
    updated_at: Optional[datetime] = None


@dataclass
class HitlRequest:
    id: str
    task_id: str
    step_index: int
    type: str                       # choice / text_input / file_upload / form
    question: str
    options: Optional[list] = None
    default_action: str = "cancel"
    status: str = "PENDING"         # PENDING / RESOLVED / EXPIRED / CANCELLED
    expires_at: Optional[datetime] = None
    user_decision: Optional[str] = None
    user_input: Optional[dict] = None
    responded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def is_pending(self) -> bool:
        return self.status == "PENDING"

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if not self.expires_at or not self.is_pending():
            return False
        current_time = now or datetime.now(timezone.utc)
        return current_time > self.expires_at

    def resolve(self, decision: str, user_input: Optional[dict] = None, now: Optional[datetime] = None):
        self.status = "RESOLVED"
        self.user_decision = decision
        self.user_input = user_input
        self.responded_at = now or datetime.now(timezone.utc)


@dataclass
class Task:
    id: str
    user_id: str
    session_id: Optional[str]
    input: dict
    status: str = "PENDING"         # PENDING / RUNNING / WAITING_HUMAN / PAUSED / COMPLETED / FAILED / CANCELLED
    priority: int = 0
    trigger_message_id: Optional[str] = None
    worker_id: Optional[str] = None
    worker_heartbeat: Optional[datetime] = None
    result: Optional[dict] = None
    error: Optional[str] = None
    paused_reason: Optional[str] = None
    title: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def is_terminal(self) -> bool:
        """任务是否已进入最终终止态"""
        return self.status in ("COMPLETED", "FAILED", "CANCELLED")

    @property
    def is_running(self) -> bool:
        return self.status == "RUNNING"

    def can_cancel(self) -> bool:
        """非终止态均允许取消"""
        return not self.is_terminal

    def cancel(self, now: Optional[datetime] = None):
        self.status = "CANCELLED"
        self.completed_at = now or datetime.now(timezone.utc)
        self.error = "Cancelled by user"

    def start(self, worker_id: str, now: Optional[datetime] = None):
        current_time = now or datetime.now(timezone.utc)
        self.status = "RUNNING"
        self.worker_id = worker_id
        self.worker_heartbeat = current_time
        if not self.started_at:
            self.started_at = current_time

    def update_heartbeat(self, now: Optional[datetime] = None):
        self.worker_heartbeat = now or datetime.now(timezone.utc)

    def wait_for_human(self):
        self.status = "WAITING_HUMAN"

    def pause(self, reason: str = "worker_shutdown"):
        self.status = "PAUSED"
        self.paused_reason = reason

    def complete(self, result: dict, now: Optional[datetime] = None):
        self.status = "COMPLETED"
        self.result = result
        self.completed_at = now or datetime.now(timezone.utc)

    def fail(self, error_message: str, now: Optional[datetime] = None):
        self.status = "FAILED"
        self.error = error_message
        self.completed_at = now or datetime.now(timezone.utc)

    def is_heartbeat_expired(self, timeout_seconds: int = 60, now: Optional[datetime] = None) -> bool:
        """判断心跳是否已超时失联（僵尸任务检测）"""
        if not self.is_running or not self.worker_heartbeat:
            return False
        current_time = now or datetime.now(timezone.utc)
        delta = (current_time - self.worker_heartbeat).total_seconds()
        return delta > timeout_seconds


@dataclass
class SessionFile:
    id: str
    session_id: str
    user_id: str
    file_name: str
    file_path: str
    file_size: int = 0
    mime_type: str = "application/octet-stream"
    category: str = "document"  # html / image / code / document / data
    storage_type: str = "sandbox"
    task_id: Optional[str] = None
    storage_key: Optional[str] = None
    is_deleted: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class FileVersion:
    id: str
    file_id: str
    session_id: str
    version_num: int
    file_size: int = 0
    task_id: Optional[str] = None
    diff_content: Optional[str] = None
    storage_key: Optional[str] = None
    summary: Optional[str] = None
    created_at: Optional[datetime] = None

