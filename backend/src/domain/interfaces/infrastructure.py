"""
可替换基础设施接口定义（任务队列、分布式锁、事件发布总线、密码与Token）
领域层和应用层只依赖这些抽象接口，具体实现由基础设施层（Redis / JWT / bcrypt）注入。
"""
from abc import ABC, abstractmethod
from typing import Any, Optional


class ITaskQueue(ABC):
    """异步任务队列抽象接口"""
    @abstractmethod
    async def enqueue(self, task_id: str, priority: int = 0, resume_from_step: int = 0) -> str:
        """任务入队并返回消息ID"""
        pass

    @abstractmethod
    async def ack(self, message_id: str) -> None:
        """确认消费消息"""
        pass


class IEventPublisher(ABC):
    """实时事件发布总线抽象接口"""
    @abstractmethod
    async def publish(self, task_id: str, event_data: dict) -> None:
        """向任务专用频道发布事件"""
        pass


class IDistributedLock(ABC):
    """分布式锁抽象接口"""
    @abstractmethod
    async def acquire(self, task_id: str, worker_id: str, ttl_seconds: int = 60) -> bool:
        """获取独占锁"""
        pass

    @abstractmethod
    async def renew(self, task_id: str, worker_id: str, ttl_seconds: int = 60) -> bool:
        """心跳续期锁"""
        pass

    @abstractmethod
    async def release(self, task_id: str, worker_id: str) -> None:
        """释放锁"""
        pass


class IPasswordHasher(ABC):
    """密码哈希与验证接口"""
    @abstractmethod
    def hash(self, password: str) -> str:
        pass

    @abstractmethod
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        pass


class ITokenProvider(ABC):
    """认证 Token 签发与解析接口"""
    @abstractmethod
    def create_token(self, user_id: str, expires_minutes: Optional[int] = None) -> str:
        pass

    @abstractmethod
    def decode_token(self, token: str) -> str:
        pass
