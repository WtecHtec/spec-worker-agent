"""
领域异常定义（纯业务异常，具备领域错误码与状态映射）
"""
from typing import Optional


class DomainException(Exception):
    """领域层基础异常"""
    def __init__(
        self,
        message: str,
        code: str = "DOMAIN_ERROR",
        status_code: int = 400,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class UserNotFoundException(DomainException):
    def __init__(self, user_id: str):
        super().__init__(
            f"User {user_id} not found",
            code="USER_NOT_FOUND",
            status_code=404,
        )


class SessionNotFoundException(DomainException):
    def __init__(self, session_id: str):
        super().__init__(
            f"Session {session_id} not found",
            code="SESSION_NOT_FOUND",
            status_code=404,
        )


class TaskNotFoundException(DomainException):
    def __init__(self, task_id: str):
        super().__init__(
            f"Task {task_id} not found",
            code="TASK_NOT_FOUND",
            status_code=404,
        )


class HitlRequestNotFoundException(DomainException):
    def __init__(self, hitl_id: str):
        super().__init__(
            f"HITL request {hitl_id} not found",
            code="HITL_NOT_FOUND",
            status_code=404,
        )


class QuotaExceededException(DomainException):
    def __init__(self, max_concurrent: int):
        super().__init__(
            f"User concurrent tasks quota exceeded ({max_concurrent}). Please wait for active tasks to complete.",
            code="QUOTA_EXCEEDED",
            status_code=429,
            details={"max_concurrent": max_concurrent},
        )
        self.max_concurrent = max_concurrent
        self.retry_after = 30


class RateLimitException(DomainException):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limit exceeded. Please retry after {retry_after} seconds.",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after},
        )
        self.retry_after = retry_after


class SessionConflictException(DomainException):
    def __init__(self, session_id: str, running_task_id: str):
        super().__init__(
            f"Session {session_id} already has a running task ({running_task_id})",
            code="SESSION_CONFLICT",
            status_code=409,
            details={"running_task_id": running_task_id},
        )
        self.running_task_id = running_task_id


class TaskCannotCancelException(DomainException):
    def __init__(self, task_id: str, current_status: str):
        super().__init__(
            f"Task {task_id} in status '{current_status}' cannot be cancelled",
            code="TASK_CANNOT_CANCEL",
            status_code=400,
            details={"current_status": current_status},
        )


class HitlAlreadyResolvedException(DomainException):
    def __init__(self, hitl_id: str, current_status: str):
        super().__init__(
            f"HITL request {hitl_id} is already in status '{current_status}'",
            code="HITL_ALREADY_RESOLVED",
            status_code=409,
            details={"current_status": current_status},
        )


class HitlExpiredException(DomainException):
    def __init__(self, hitl_id: str):
        super().__init__(
            f"HITL request {hitl_id} has expired",
            code="HITL_EXPIRED",
            status_code=410,
        )
