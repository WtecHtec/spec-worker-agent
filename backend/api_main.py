import structlog
import logging
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.config.settings import get_settings
from src.infrastructure.redis.client import close_redis
from src.interface.routers import auth, session, message, task, hitl, ecosystem
from src.interface.middleware.rate_limiter import RateLimitMiddleware
from src.interface.middleware.error_handler import (
    RequestContextMiddleware, register_exception_handlers
)

settings = get_settings()

# 配置 structlog
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer() if settings.app_env == "production" else structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if settings.app_env == "development" else logging.INFO
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    from src.domain.services.tools.manager import user_tool_registry_manager

    logger.info("api_server_starting", env=settings.app_env)
    try:
        from src.infrastructure.db.database import engine
        from src.infrastructure.db.models import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_tables_ensured")
    except Exception as e:
        logger.warning("database_tables_init_warning", error=str(e))

    # 启动 Redis 跨进程缓存失效监听器
    invalidation_task = asyncio.create_task(
        user_tool_registry_manager.start_invalidation_listener()
    )

    yield

    invalidation_task.cancel()
    await close_redis()
    logger.info("api_server_stopped")


app = FastAPI(
    title="Agent API",
    version="0.1.0",
    lifespan=lifespan,
)

# 1. 注册统一异常处理
register_exception_handlers(app)

# 2. 注册中间件（注意：FastAPI 中间件是洋葱模型，后添加的在外层先执行）
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)


from src.interface.routers import auth, session, message, task, hitl, ecosystem, file, langgraph_proxy

# 3. 注册业务路由
app.include_router(auth.router)
app.include_router(session.router)
app.include_router(message.router)
app.include_router(task.router)
app.include_router(hitl.router)
app.include_router(ecosystem.router)
app.include_router(file.router)
app.include_router(langgraph_proxy.router)


# 4. 健康检查与探针接口
@app.get("/health")
async def health():
    """Liveness 存活探针"""
    return {"status": "ok", "env": settings.app_env}


@app.get("/health/ready")
async def readiness(response: Response):
    """Readiness 就绪探针：检查 DB 和 Redis 连接"""
    from src.infrastructure.redis.client import get_redis
    from src.infrastructure.redis.adapters import RedisTaskQueue
    from src.infrastructure.db.database import AsyncSessionLocal
    from sqlalchemy import text

    db_ok = False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.error("readiness_db_check_failed", error=str(e))

    redis_ok = False
    redis_stats = {}
    try:
        redis = await get_redis()
        queue = RedisTaskQueue(redis)
        redis_stats = await queue.get_stats()
        redis_ok = True
    except Exception as e:
        logger.error("readiness_redis_check_failed", error=str(e))

    all_ready = db_ok and redis_ok
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "not_ready",
        "database": "ok" if db_ok else "unreachable",
        "redis": "ok" if redis_ok else "unreachable",
        "queue": redis_stats,
        "env": settings.app_env,
    }
