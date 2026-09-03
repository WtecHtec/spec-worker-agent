import os
from jose import jwt, JWTError

INTERNAL_JWT_SECRET = os.getenv("INTERNAL_JWT_SECRET", "internal-service-secret-key-32-chars")
INTERNAL_JWT_ALGORITHM = "HS256"

def verify_internal_jwt(token: str) -> dict:
    return jwt.decode(token, INTERNAL_JWT_SECRET, algorithms=[INTERNAL_JWT_ALGORITHM])

try:
    from langgraph_sdk import Auth

    my_auth = Auth()

    @my_auth.authenticate
    async def authenticate(authorization: str) -> Auth.types.MinimalUserDict:
        """从 Authorization 请求头校验网关下发的内部 JWT"""
        if not authorization:
            raise ValueError("Missing authorization header")
        token = authorization.removeprefix("Bearer ").strip()
        try:
            payload = verify_internal_jwt(token)
            user_id = payload.get("user_id")
            if not user_id:
                raise ValueError("user_id not in token payload")
            return {"identity": user_id}
        except JWTError as e:
            raise ValueError(f"Invalid internal token: {e}")

    @my_auth.on.threads
    async def authorize_threads(ctx: Auth.types.AuthContext, value: dict):
        """Thread 资源自动按用户身份隔离"""
        return {"owner": ctx.user.identity}

except ImportError:
    # 允许在没有安装 langgraph_sdk 的纯本地调试环境下安全导入
    my_auth = None
