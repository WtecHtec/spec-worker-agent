import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from src.config.settings import get_settings
from src.infrastructure.redis.client import get_redis
from src.domain.exceptions import RateLimitException

settings = get_settings()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    基于 Redis 滑动/固定时间窗口的请求限流中间件
    """

    async def dispatch(self, request: Request, call_next):
        # 排除无需限流的路径（如健康检查）
        if not settings.rate_limit_enabled or request.url.path.startswith("/health") or request.url.path.startswith("/docs") or request.url.path.startswith("/openapi.json"):
            return await call_next(request)

        # 获取客户端标识（优先从 Authorization token 或客户端 IP）
        client_id = request.client.host if request.client else "unknown"
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from src.application.auth.security import decode_token
                user_id = decode_token(auth_header.split(" ")[1])
                client_id = f"user:{user_id}"
            except Exception:
                pass

        current_minute = int(time.time() // 60)
        redis_key = f"rate_limit:{client_id}:{current_minute}"

        try:
            redis = await get_redis()
            current_count = await redis.incr(redis_key)
            if current_count == 1:
                await redis.expire(redis_key, 120)

            limit = settings.rate_limit_requests_per_minute
            if current_count > limit:
                retry_after = 60 - int(time.time() % 60)
                raise RateLimitException(
                    message=f"Rate limit exceeded. Maximum {limit} requests per minute.",
                    retry_after=retry_after
                )

            response: Response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - current_count))
            return response
        except RateLimitException:
            raise
        except Exception:
            # Redis 短暂故障时不阻断正常流量
            return await call_next(request)
