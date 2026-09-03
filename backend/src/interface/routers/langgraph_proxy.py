import json
import re
import structlog
import httpx
from fastapi import APIRouter, Request, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings
from src.infrastructure.db.database import get_db, AsyncSessionLocal
from src.infrastructure.db.repositories import SessionRepository, MessageRepository
from src.interface.middleware.auth import get_current_user_id
from src.application.auth.internal_jwt import mint_internal_jwt

logger = structlog.get_logger()
settings = get_settings()

router = APIRouter(tags=["langgraph-proxy"])

# 全局共享 HTTP 客户端连接池
_http_client: httpx.AsyncClient | None = None

def get_proxy_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        limits = httpx.Limits(max_connections=200, max_keepalive_connections=50)
        _http_client = httpx.AsyncClient(limits=limits, timeout=httpx.Timeout(connect=5.0, read=None, write=30.0, pool=10.0))
    return _http_client


async def assert_thread_belongs_to_user(thread_id: str, user_id: str, db: AsyncSession):
    """多租户归属校验：确保 thread_id (session_id) 属于当前请求用户"""
    session_repo = SessionRepository(db)
    session_obj = await session_repo.get_by_id(thread_id)
    if not session_obj:
        # 针对新会话首次 run，按需自动创建 session 实体
        await session_repo.create(user_id=user_id, title="新对话")
        return
    if session_obj.user_id != user_id:
        logger.warning("unauthorized_thread_access", thread_id=thread_id, user_id=user_id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Thread does not belong to user",
        )


def extract_run_id_from_chunk(chunk_str: str) -> str | None:
    """尝试从 SSE 数据块中提取 run_id"""
    match = re.search(r'"run_id"\s*:\s*"([^"]+)"', chunk_str)
    if match:
        return match.group(1)
    return None


def extract_latest_ai_text_from_chunk(chunk_str: str) -> tuple[str | None, bool]:
    """
    尝试从 LangGraph event chunk 中提取最新生成的 AI 文本。
    返回 (text, is_incremental):
    - is_incremental=False: 代表该 text 是最新的完整文本快照（应覆盖更新，杜绝重复累加）
    - is_incremental=True: 代表该 text 是增量 token（应累加追加）
    """
    for line in chunk_str.splitlines():
        if line.startswith("data:"):
            raw_data = line.removeprefix("data:").strip()
            if not raw_data:
                continue
            try:
                payload = json.loads(raw_data)
                if isinstance(payload, dict):
                    # 1. 顶层 messages（event: values）——只看最后一条真正由当前步骤生成的 AI 消息
                    if "messages" in payload and isinstance(payload["messages"], list) and payload["messages"]:
                        last_m = payload["messages"][-1]
                        if isinstance(last_m, dict) and last_m.get("type") in ("AIMessageChunk", "ai", "assistant"):
                            c = last_m.get("content", "")
                            if isinstance(c, str) and c:
                                return c, False

                    # 2. event: updates 节点消息
                    for node_val in payload.values():
                        if isinstance(node_val, dict) and "messages" in node_val and isinstance(node_val["messages"], list) and node_val["messages"]:
                            last_m = node_val["messages"][-1]
                            if isinstance(last_m, dict) and last_m.get("type") in ("AIMessageChunk", "ai", "assistant"):
                                c = last_m.get("content", "")
                                if isinstance(c, str) and c:
                                    return c, False

                    # 3. 增量 content
                    if "content" in payload and isinstance(payload["content"], str) and payload["content"]:
                        return payload["content"], True
            except Exception:
                pass
    return None, False


# 保持兼容性别名
def extract_content_from_chunk(chunk_str: str) -> str:
    text, _ = extract_latest_ai_text_from_chunk(chunk_str)
    return text or ""


@router.post("/threads/{thread_id}/runs/stream")
async def proxy_run_stream(
    thread_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    网关层流式代理：
    1. 校验用户对 thread_id 的所有权
    2. 签发短效内部 JWT
    3. 代理 upstream LangGraph Server 的流式输出并直推前端
    4. 监听前端断连触发后台真取消
    5. 流式结束/取消时持久化业务库消息
    """
    await assert_thread_belongs_to_user(thread_id, user_id, db)

    # 幂等确保 LangGraph upstream 中存在该 thread（避免 404 NOT_FOUND）
    await _ensure_thread_in_upstream(thread_id, user_id)

    body = await request.json()
    internal_token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    client = get_proxy_http_client()

    # 自动将 assistant_id 对齐为 LangGraph 内部的 UUID
    assistant_id = body.get("assistant_id")
    if not assistant_id or assistant_id == "agent":
        real_assistant_id = await get_system_assistant_id(internal_token)
        body["assistant_id"] = real_assistant_id

    # 确保 stream_mode 包含官方标准 messages 通道
    stream_mode = body.get("stream_mode")
    if isinstance(stream_mode, list):
        if "messages-tuple" in stream_mode and "messages" not in stream_mode:
            stream_mode.append("messages")
        body["stream_mode"] = stream_mode

    run_id_state = {"run_id": None, "is_cancelled": False}

    async def event_generator():
        upstream_url = f"{settings.langgraph_upstream_url.rstrip('/')}/threads/{thread_id}/runs/stream"
        headers = {
            "Authorization": f"Bearer {internal_token}",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

        try:
            async with client.stream("POST", upstream_url, json=body, headers=headers) as resp:
                if resp.status_code >= 400:
                    error_detail = await resp.aread()
                    logger.error("upstream_stream_failed", status=resp.status_code, detail=error_detail.decode())
                    yield f"event: error\ndata: {json.dumps({'error': 'Upstream error', 'status': resp.status_code})}\n\n".encode()
                    return

                async for chunk in resp.aiter_bytes():
                    chunk_str = chunk.decode("utf-8", errors="ignore")
                    
                    # 抓取 run_id
                    if not run_id_state["run_id"]:
                        found_run_id = extract_run_id_from_chunk(chunk_str)
                        if found_run_id:
                            run_id_state["run_id"] = found_run_id

                    if "event: messages-tuple" in chunk_str and "event: messages\n" not in chunk_str:
                        yield chunk_str.replace("event: messages-tuple", "event: messages").encode("utf-8")
                    else:
                        yield chunk

                    # 检测客户端是否已主动断开
                    if await request.is_disconnected():
                        logger.info("client_disconnected_trigger_cancel", thread_id=thread_id, run_id=run_id_state["run_id"])
                        run_id_state["is_cancelled"] = True
                        if run_id_state["run_id"]:
                            await cancel_upstream_run(thread_id, run_id_state["run_id"], internal_token)
                        break

        except httpx.RequestError as exc:
            logger.error("langgraph_proxy_request_error", error=str(exc))
            yield f"event: error\ndata: {json.dumps({'error': 'LangGraph Server connection failed'})}\n\n".encode()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def cancel_upstream_run(thread_id: str, run_id: str, token: str):
    """向 LangGraph 发起真实 Cancel 请求"""
    client = get_proxy_http_client()
    url = f"{settings.langgraph_upstream_url.rstrip('/')}/threads/{thread_id}/runs/{run_id}/cancel"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = await client.post(url, json={"action": "interrupt", "wait": True}, headers=headers)
        logger.info("upstream_cancel_response", status=resp.status_code, run_id=run_id)
    except Exception as e:
        logger.error("upstream_cancel_failed", run_id=run_id, error=str(e))


@router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def proxy_cancel_run(
    thread_id: str,
    run_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    前端主动点击停止时调用的服务端真正取消端点：
    1. 校验会话所有权
    2. 转发 LangGraph 执行 runs.cancel(action='interrupt')
    3. 标记业务库中相关消息为 cancelled
    """
    await assert_thread_belongs_to_user(thread_id, user_id, db)
    internal_token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    
    await cancel_upstream_run(thread_id, run_id, internal_token)
    
    return {"status": "cancelled", "run_id": run_id, "thread_id": thread_id}


# ─────────────────────────────────────────────────────────────────────────────
# 以下路由：透传 LangGraph 协议中 SDK 需要的辅助接口
# useStream SDK 在每次 submit() 前会先 GET /threads/{id}/state 拉取历史，
# 以及调用 GET /assistants/{id} 验证 assistant 是否存在。
# 这些请求需要注入内部 JWT 并透传到 upstream LangGraph。
# ─────────────────────────────────────────────────────────────────────────────

async def _proxy_get(path: str, user_id: str, query_params: str = "") -> dict:
    """通用 GET 透传：注入内部 JWT，转发至 LangGraph upstream"""
    client = get_proxy_http_client()
    token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    url = f"{settings.langgraph_upstream_url.rstrip('/')}{path}"
    if query_params:
        url += f"?{query_params}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        resp = await client.get(url, headers=headers)
        return resp.json() if resp.status_code < 400 else {}
    except Exception as e:
        logger.error("langgraph_proxy_get_error", path=path, error=str(e))
        return {}


_cached_assistant_id: str | None = None

async def get_system_assistant_id(token: str) -> str:
    """自动获取系统注册的 agent assistant UUID，带缓存"""
    global _cached_assistant_id
    if _cached_assistant_id:
        return _cached_assistant_id
    client = get_proxy_http_client()
    url = f"{settings.langgraph_upstream_url.rstrip('/')}/assistants/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = await client.post(url, json={}, headers=headers)
        if resp.status_code == 200:
            items = resp.json()
            if items and len(items) > 0:
                _cached_assistant_id = items[0]["assistant_id"]
                logger.info("resolved_system_assistant_id", assistant_id=_cached_assistant_id)
                return _cached_assistant_id
    except Exception as e:
        logger.warning("failed_to_fetch_assistant_id", error=str(e))
    return "agent"


async def _ensure_thread_in_upstream(thread_id: str, user_id: str):
    """
    确保 LangGraph upstream 中存在该 thread（POST /threads 幂等创建）。
    - LangGraph Server 要求 thread_id 为 UUID（我们的 session_id 满足）
    - 携带 metadata: {"owner": user_id} 以配合 LangGraph Auth 的用户级多租户隔离
    - 如果 thread 已存在会返回 409，我们直接忽略即认为成功
    """
    client = get_proxy_http_client()
    token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    url = f"{settings.langgraph_upstream_url.rstrip('/')}/threads"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        resp = await client.post(
            url,
            json={"thread_id": thread_id, "metadata": {"owner": user_id}},
            headers=headers,
        )
        if resp.status_code in (200, 201):
            logger.info("thread_created_in_upstream", thread_id=thread_id, owner=user_id)
        elif resp.status_code == 409:
            logger.debug("thread_already_exists_upstream", thread_id=thread_id)
        else:
            logger.error(
                "thread_create_upstream_failed",
                thread_id=thread_id,
                status=resp.status_code,
                detail=resp.text[:200],
            )
    except httpx.ConnectError:
        logger.warning("upstream_not_reachable", upstream=settings.langgraph_upstream_url, thread_id=thread_id)
        # 当 upstream 暂不可达时，不中断流程，让后续调用返回友好降级结果
    except Exception as e:
        logger.error("thread_create_upstream_exception", thread_id=thread_id, error=str(e))


@router.get("/threads/{thread_id}/state")
async def proxy_thread_state(
    thread_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """透传 GET /threads/{id}/state → LangGraph upstream（SDK 内部调用）"""
    await assert_thread_belongs_to_user(thread_id, user_id, db)

    # 尝试确保 thread 存在于 LangGraph（优雅降级）
    await _ensure_thread_in_upstream(thread_id, user_id)

    client = get_proxy_http_client()
    token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    url = f"{settings.langgraph_upstream_url.rstrip('/')}/threads/{thread_id}/state"
    query = str(request.query_params)
    if query:
        url += f"?{query}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 200:
            return resp.json()
        # Thread 存在但尚无 run 记录时返回空 state，保持 SDK 协议兼容
        return {
            "values": {"messages": []},
            "next": [],
            "checkpoint": None,
            "metadata": {},
            "created_at": None,
            "parent_checkpoint": None,
        }
    except (httpx.ConnectError, httpx.RequestError) as e:
        logger.warning("langgraph_upstream_unavailable_for_state", error=str(e))
        return {
            "values": {"messages": []},
            "next": [],
            "checkpoint": None,
            "metadata": {"warning": "Agent Runtime 正在启动或未就绪"},
        }
    except Exception as e:
        logger.error("langgraph_proxy_state_error", thread_id=thread_id, error=str(e))
        return {"values": {"messages": []}, "next": [], "checkpoint": None, "metadata": {}}


@router.api_route("/threads/{thread_id}/history", methods=["GET", "POST"])
async def proxy_thread_history(
    thread_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """透传 GET/POST /threads/{id}/history → LangGraph upstream（官方 SDK getHistory 内部调用）"""
    await assert_thread_belongs_to_user(thread_id, user_id, db)
    await _ensure_thread_in_upstream(thread_id, user_id)

    client = get_proxy_http_client()
    token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    url = f"{settings.langgraph_upstream_url.rstrip('/')}/threads/{thread_id}/history"
    query = str(request.query_params)
    if query:
        url += f"?{query}"

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    try:
        if request.method == "POST":
            headers["Content-Type"] = "application/json"
            try:
                body = await request.json()
            except Exception:
                body = {}
            resp = await client.post(url, json=body, headers=headers)
        else:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 200:
            return resp.json()
        return []
    except Exception as e:
        logger.error("langgraph_proxy_history_error", thread_id=thread_id, error=str(e))
        return []


@router.get("/assistants/{assistant_id}")
async def proxy_assistant(
    assistant_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """透传 GET /assistants/{id} → LangGraph upstream（SDK 验证 assistant 存在性）"""
    data = await _proxy_get(f"/assistants/{assistant_id}", user_id)
    return data


@router.post("/assistants/search")
async def proxy_assistants_search(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """透传 POST /assistants/search → LangGraph upstream"""
    client = get_proxy_http_client()
    token = mint_internal_jwt(user_id=user_id, ttl_seconds=60)
    url = f"{settings.langgraph_upstream_url.rstrip('/')}/assistants/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = await request.json()
    try:
        resp = await client.post(url, json=body, headers=headers)
        return resp.json()
    except Exception as e:
        logger.error("langgraph_proxy_assistants_search_error", error=str(e))
        return []
