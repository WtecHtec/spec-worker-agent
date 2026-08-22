"""
任务调度领域服务（内聚会话并发互斥、用户配额与优先级计算领域逻辑）
"""
from src.domain.entities.models import User, Session, Task
from src.domain.exceptions import QuotaExceededException, SessionConflictException


class TaskSchedulerService:
    @staticmethod
    def validate_session_concurrency(session_id: str, running_task: Task | None) -> None:
        """校验同会话是否有未完结任务，防止重复发消息并发执行"""
        if running_task and not running_task.is_terminal:
            raise SessionConflictException(session_id, running_task.id)

    @staticmethod
    def validate_user_quota(user: User | None, current_active_tasks: int) -> None:
        """校验单用户全局最大并发配额"""
        max_concurrent = user.max_concurrent_tasks if user else 3
        if current_active_tasks >= max_concurrent:
            raise QuotaExceededException(max_concurrent)

    @staticmethod
    def assign_priority(user: User | None, content: str) -> int:
        """根据用户套餐与输入特征确定任务优先级"""
        priority = 0
        if user and user.plan == "pro":
            priority += 10
        elif user and user.plan == "enterprise":
            priority += 20
        return priority
