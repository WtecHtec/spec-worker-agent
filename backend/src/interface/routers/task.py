import asyncio
import json
import httpx
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.settings import get_settings, Settings
from src.domain.exceptions import TaskNotFoundException
from src.infrastructure.db.database import get_db
from src.infrastructure.db.repositories import TaskRepository, TaskStepRepository, MessageRepository
from src.infrastructure.redis.client import get_redis
from src.infrastructure.redis.adapters import RedisPubSub
from src.interface.middleware.auth import get_current_user_id
from src.application.task.use_cases import CancelTaskUseCase, GetTaskDetailUseCase, GetTaskStepsUseCase

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    id: str
    status: str
    title: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    result: dict | None
    error: str | None


class StepResponse(BaseModel):
    step_index: int
    type: str
    content: dict
    created_at: str


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询任务详情（委托 GetTaskDetailUseCase）"""
    use_case = GetTaskDetailUseCase(task_repo=TaskRepository(db))
    task = await use_case.execute(task_id=task_id, user_id=user_id)
    return TaskResponse(
        id=task.id,
        status=task.status,
        title=task.title,
        created_at=task.created_at.isoformat() if task.created_at else "",
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        result=task.result,
        error=task.error,
    )


@router.get("/{task_id}/steps", response_model=list[StepResponse])
async def get_steps(
    task_id: str,
    after_step: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """查询任务步骤流水（委托 GetTaskStepsUseCase）"""
    use_case = GetTaskStepsUseCase(task_repo=TaskRepository(db), step_repo=TaskStepRepository(db))
    steps = await use_case.execute(task_id=task_id, user_id=user_id, after_step=after_step)
    return [
        StepResponse(
            step_index=s.step_index,
            type=s.type,
            content=s.content,
            created_at=s.created_at.isoformat() if s.created_at else "",
        )
        for s in steps
    ]


@router.post("/{task_id}/cancel", response_model=TaskResponse)
@router.delete("/{task_id}", response_model=TaskResponse)
async def cancel_task(
    task_id: str,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """取消任务端点（委托 CancelTaskUseCase）"""
    redis = await get_redis()
    pubsub = RedisPubSub(redis)

    use_case = CancelTaskUseCase(
        db=db,
        task_repo=TaskRepository(db),
        msg_repo=MessageRepository(db),
        event_publisher=pubsub,
    )
    task = await use_case.execute(task_id=task_id, user_id=user_id)

    return TaskResponse(
        id=task.id,
        status=task.status,
        title=task.title,
        created_at=task.created_at.isoformat() if task.created_at else "",
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        result=task.result,
        error=task.error,
    )


@router.get("/{task_id}/stream")
async def task_stream(
    task_id: str,
    from_step: int = 0,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """SSE 实时推送端点"""
    use_case = GetTaskDetailUseCase(task_repo=TaskRepository(db))
    task = await use_case.execute(task_id=task_id, user_id=user_id)

    step_repo = TaskStepRepository(db)

    async def event_generator():
        # 1. 先补发历史步骤（from_step 之后已入库的）
        history_steps = await step_repo.list_after(task_id, after_index=from_step)
        for step in history_steps:
            data = {
                "event": "new_step",
                "task_id": task_id,
                "step_index": step.step_index,
                "step_type": step.type,
                "content": step.content,
                "created_at": step.created_at.isoformat() if step.created_at else "",
            }
            yield f"event: new_step\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        # 如果任务已结束，推送结束事件后关闭
        if task.status in ("COMPLETED", "FAILED", "CANCELLED"):
            end_data = {"event": f"task_{task.status.lower()}", "task_id": task_id}
            if task.result:
                end_data["result"] = task.result
            if task.error:
                end_data["error"] = task.error
            yield f"event: task_{task.status.lower()}\ndata: {json.dumps(end_data, ensure_ascii=False)}\n\n"
            return

        # 2. 订阅 Redis Pub/Sub，实时监听新步骤
        redis = await get_redis()
        pubsub = redis.pubsub()
        channel = f"task:{task_id}"
        await pubsub.subscribe(channel)

        try:
            ping_counter = 0
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                event = json.loads(message["data"])
                event_type = event.get("event")

                if event_type == "new_step":
                    step_index = event["step_index"]
                    steps = await step_repo.list_after(task_id, after_index=step_index - 1)
                    matched = next((s for s in steps if s.step_index == step_index), None)
                    if matched:
                        data = {
                            "event": "new_step",
                            "task_id": task_id,
                            "step_index": matched.step_index,
                            "step_type": matched.type,
                            "content": matched.content,
                            "created_at": matched.created_at.isoformat() if matched.created_at else "",
                        }
                        yield f"event: new_step\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                elif event_type in ("task_completed", "task_failed", "task_cancelled", "hitl_created"):
                    yield f"event: {event_type}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event_type in ("task_completed", "task_failed", "task_cancelled"):
                        break

                ping_counter += 1
                if ping_counter % 30 == 0:
                    yield "event: ping\ndata: {}\n\n"

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/{task_id}/artifacts/{file_path:path}")
async def get_task_artifact_raw(
    task_id: str,
    file_path: str,
    download: bool = Query(False),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """
    流式读取并返回沙箱中的任务产物文件（支持浏览器直接 URL 预览/图片渲染/文件下载）
    """
    task_repo = TaskRepository(db)
    task = await task_repo.get_by_id(task_id)
    if not task or task.user_id != user_id:
        raise TaskNotFoundException(task_id)

    sandbox_url = settings.sandbox_url.rstrip("/")
    target_url = f"{sandbox_url}/fs/raw?path={file_path}"
    if download:
        target_url += "&download=true"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            res = await client.get(target_url)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to connect to sandbox: {str(e)}")

        if res.status_code != 200:
            raise HTTPException(status_code=res.status_code, detail=res.text)

        content_type = res.headers.get("content-type", "application/octet-stream")
        response_headers = {
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
        }
        if "content-disposition" in res.headers:
            response_headers["Content-Disposition"] = res.headers["content-disposition"]

        return Response(
            content=res.content,
            media_type=content_type,
            headers=response_headers,
        )

