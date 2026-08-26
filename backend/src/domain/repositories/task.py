"""
任务与步骤、断点仓储抽象接口（领域层）
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from src.domain.entities.models import Task, TaskStep, Checkpoint


class ITaskRepository(ABC):
    @abstractmethod
    async def create(
        self,
        user_id: str,
        input_data: dict,
        session_id: Optional[str] = None,
        title: Optional[str] = None,
        priority: int = 0,
        trigger_message_id: Optional[str] = None,
    ) -> Task:
        """创建新任务实体并持久化"""
        pass

    @abstractmethod
    async def get_by_id(self, task_id: str) -> Optional[Task]:
        """根据 ID 查询任务"""
        pass

    @abstractmethod
    async def count_active_by_user(self, user_id: str) -> int:
        """统计用户当前活跃任务数（PENDING / RUNNING / WAITING_HUMAN）"""
        pass

    @abstractmethod
    async def get_active_in_session(self, session_id: str) -> Optional[Task]:
        """查询指定会话中是否有正在运行的任务"""
        pass

    @abstractmethod
    async def update_status(
        self,
        task_id: str,
        status: str,
        worker_id: Optional[str] = None,
        worker_heartbeat: Optional[datetime] = None,
        result: Optional[dict] = None,
        error: Optional[str] = None,
        paused_reason: Optional[str] = None,
        completed_at: Optional[datetime] = None,
    ) -> Optional[Task]:
        """更新任务状态及附属属性"""
        pass

    @abstractmethod
    async def find_zombie_tasks(self, heartbeat_before: datetime) -> list[Task]:
        """查询心跳超时的僵尸 RUNNING 任务"""
        pass

    @abstractmethod
    async def list_paused_for_recovery(self) -> list[Task]:
        """查询因 Worker 优雅退出而暂停的任务"""
        pass

    @abstractmethod
    async def set_trigger_message(self, task_id: str, message_id: str) -> None:
        """关联触发此任务的消息 ID"""
        pass


class ITaskStepRepository(ABC):
    @abstractmethod
    async def create(self, task_id: str, step_index: int, step_type: str, content: dict) -> TaskStep:
        """幂等写入步骤流水"""
        pass

    @abstractmethod
    async def list_after(self, task_id: str, after_index: int = 0) -> list[TaskStep]:
        """查询指定步骤序号之后的所有步骤列表"""
        pass


class ICheckpointRepository(ABC):
    @abstractmethod
    async def create(self, task_id: str) -> Checkpoint:
        """创建初始任务断点快照"""
        pass

    @abstractmethod
    async def get_by_task(self, task_id: str) -> Optional[Checkpoint]:
        """获取指定任务的断点快照"""
        pass

    @abstractmethod
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
        """基于乐观锁更新断点快照，版本不匹配返回 False"""
        pass
