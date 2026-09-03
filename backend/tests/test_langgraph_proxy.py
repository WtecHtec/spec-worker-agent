import pytest
import json
from datetime import datetime, timezone
from jose import jwt

from src.config.settings import get_settings
from src.application.auth.internal_jwt import mint_internal_jwt
from src.interface.routers.langgraph_proxy import (
    extract_run_id_from_chunk,
    extract_content_from_chunk,
)

settings = get_settings()

def test_mint_internal_jwt():
    """测试内部短效 JWT 签发与有效性"""
    user_id = "user-12345"
    token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    assert token is not None

    payload = jwt.decode(token, settings.internal_jwt_secret, algorithms=["HS256"])
    assert payload["user_id"] == user_id
    assert payload["iss"] == "spec-worker-gateway"
    assert payload["exp"] > payload["iat"]


def test_extract_run_id_from_chunk():
    """测试从 SSE 数据块中精准匹配 run_id"""
    sample_chunk = 'event: metadata\ndata: {"run_id": "run-abc-789", "attempt": 1}\n\n'
    run_id = extract_run_id_from_chunk(sample_chunk)
    assert run_id == "run-abc-789"

    no_run_chunk = 'event: ping\ndata: {}\n\n'
    assert extract_run_id_from_chunk(no_run_chunk) is None


def test_extract_content_from_chunk():
    """测试从事件流 chunk 中提取 AI 文本"""
    # 模拟 AIMessageChunk
    chunk_msg = 'data: {"messages": [{"type": "AIMessageChunk", "content": "Hello World"}]}\n\n'
    content = extract_content_from_chunk(chunk_msg)
    assert content == "Hello World"

    # 模拟 partial content
    chunk_direct = 'data: {"content": " direct stream"}\n\n'
    content2 = extract_content_from_chunk(chunk_direct)
    assert content2 == " direct stream"


@pytest.mark.asyncio
async def test_langgraph_proxy_auth_rejection():
    """测试未经认证访问代理接口被拒绝 401"""
    from httpx import AsyncClient, ASGITransport
    from api_main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 匿名请求无 token
        resp = await client.post("/threads/test-thread-id/runs/stream", json={"input": {}})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_langgraph_proxy_cancel_auth_rejection():
    """测试未经认证调用 Cancel 端点被拒绝 401"""
    from httpx import AsyncClient, ASGITransport
    from api_main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/threads/test-thread/runs/test-run/cancel")
        assert resp.status_code == 401
