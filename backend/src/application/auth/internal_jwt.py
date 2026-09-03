from datetime import datetime, timedelta, timezone
from jose import jwt
from src.config.settings import get_settings

settings = get_settings()

def mint_internal_jwt(user_id: str, ttl_seconds: int = 60) -> str:
    """网关签发内部短效 JWT，用于向 LangGraph Server 传递已经过校验的用户身份"""
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=ttl_seconds)
    payload = {
        "user_id": user_id,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": "spec-worker-gateway",
    }
    return jwt.encode(payload, settings.internal_jwt_secret, algorithm="HS256")
