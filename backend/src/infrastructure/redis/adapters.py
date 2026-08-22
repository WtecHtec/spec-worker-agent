import json
from redis.asyncio import Redis
from src.config.settings import get_settings
from src.domain.interfaces.infrastructure import ITaskQueue, IEventPublisher, IDistributedLock

settings = get_settings()


class RedisTaskQueue(ITaskQueue):
    """Redis Stream 任务队列"""

    def __init__(self, redis: Redis):
        self.redis = redis
        self.stream = settings.redis_stream_name
        self.group = settings.redis_consumer_group

    async def ensure_group(self):
        """确保消费者组存在"""
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception:
            pass  # 已存在则忽略

    async def enqueue(self, task_id: str, priority: int = 0, resume_from_step: int = 0):
        """推任务入队"""
        await self.redis.xadd(
            self.stream,
            {
                "task_id": task_id,
                "priority": str(priority),
                "resume_from_step": str(resume_from_step),
            },
            maxlen=settings.redis_stream_max_len,
            approximate=True,
        )

    async def consume(self, worker_id: str, count: int = 1, block_ms: int = 5000):
        """Worker 消费任务，阻塞等待"""
        messages = await self.redis.xreadgroup(
            groupname=self.group,
            consumername=worker_id,
            streams={self.stream: ">"},
            count=count,
            block=block_ms,
        )
        if not messages:
            return []
        results = []
        for _stream, entries in messages:
            for msg_id, data in entries:
                results.append({
                    "msg_id": msg_id,
                    "task_id": data["task_id"],
                    "priority": int(data.get("priority", 0)),
                    "resume_from_step": int(data.get("resume_from_step", 0)),
                })
        return results

    async def ack(self, msg_id: str):
        """确认消费完成"""
        await self.redis.xack(self.stream, self.group, msg_id)

    async def get_stats(self) -> dict:
        """获取队列统计信息"""
        try:
            length = await self.redis.xlen(self.stream)
            groups = await self.redis.xinfo_groups(self.stream)
            pending_count = 0
            consumers_count = 0
            if groups:
                for g in groups:
                    if g.get("name") == self.group:
                        pending_count = g.get("pending", 0)
                        consumers_count = g.get("consumers", 0)
            return {
                "stream_length": length,
                "pending_messages": pending_count,
                "active_consumers": consumers_count,
            }
        except Exception:
            return {"stream_length": 0, "pending_messages": 0, "active_consumers": 0}


class RedisPubSub(IEventPublisher):
    """Redis Pub/Sub 实时事件发布与订阅"""

    def __init__(self, redis: Redis):
        self.redis = redis

    async def publish(self, task_id: str, event_data: dict):
        """广播事件给所有订阅该任务的客户端"""
        channel = f"task:{task_id}"
        await self.redis.publish(channel, json.dumps(event_data, ensure_ascii=False))


class RedisLock(IDistributedLock):
    """Redis 分布式锁，基于 SET NX EX + Lua 脚本安全释放"""

    RELEASE_SCRIPT = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    def _key(self, task_id: str) -> str:
        return f"task_lock:{task_id}"

    async def acquire(self, task_id: str, worker_id: str, ttl: int = 60) -> bool:
        result = await self.redis.set(
            self._key(task_id), worker_id, nx=True, ex=ttl
        )
        return result is True

    async def renew(self, task_id: str, worker_id: str, ttl: int = 60) -> bool:
        current = await self.redis.get(self._key(task_id))
        if current == worker_id:
            await self.redis.expire(self._key(task_id), ttl)
            return True
        return False

    async def release(self, task_id: str, worker_id: str):
        await self.redis.eval(self.RELEASE_SCRIPT, 1, self._key(task_id), worker_id)
