import time
import uuid
import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from src.domain.exceptions import DomainException

logger = structlog.get_logger()


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    注入 request_id 和记录请求耗时的中间件
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # 绑定当前请求的结构化日志上下文
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            process_time = time.perf_counter() - start_time
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.4f}s"

            # 排除高频 health 日志
            if not request.url.path.startswith("/health"):
                logger.info(
                    "http_request_finished",
                    status_code=response.status_code,
                    duration_ms=round(process_time * 1000, 2),
                )
            return response
        except Exception as e:
            process_time = time.perf_counter() - start_time
            logger.exception(
                "http_request_failed",
                error=str(e),
                duration_ms=round(process_time * 1000, 2),
            )
            raise


def register_exception_handlers(app: FastAPI):
    """注册全局异常处理器，统一错误响应结构"""

    @app.exception_handler(DomainException)
    async def domain_exception_handler(request: Request, exc: DomainException):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        headers = {}
        if hasattr(exc, "retry_after"):
            headers["Retry-After"] = str(exc.retry_after)

        return JSONResponse(
            status_code=exc.status_code,
            headers=headers,
            content={
                "code": exc.code,
                "message": exc.message,
                "request_id": request_id,
                "details": exc.details if exc.details else None,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        code_map = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            429: "TOO_MANY_REQUESTS",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": code_map.get(exc.status_code, "HTTP_ERROR"),
                "message": exc.detail if isinstance(exc.detail, str) else str(exc.detail),
                "request_id": request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        # 简化验证错误格式
        errors = [{"loc": list(err["loc"]), "msg": err["msg"]} for err in exc.errors()]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "code": "VALIDATION_ERROR",
                "message": "Invalid request payload",
                "request_id": request_id,
                "details": {"errors": errors},
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("unhandled_server_exception", error=str(exc))
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An internal server error occurred. Please contact support.",
                "request_id": request_id,
            },
        )
