# 后端 LangGraph 统一网关代理设计规范

## 1. 架构定位与职责划分

后端 FastAPI 服务作为系统的 **统一安全与业务代理网关**，位于前端浏览器与内部 Agent Runtime 之间：
- **前端接入**：接收外部携带标准 `access_token` 的 API 请求；
- **多租户审计**：强校验 `thread_id` 归属，严禁越权；
- **零信任鉴权**：签发 60 秒内部短效 `internal_jwt`，代表用户访问 upstream；
- **双向无损代理**：透传 LangGraph SSE 流、状态查询与历史分页；
- **异常收敛与断连感知**：监听前端客户端连接中断，自动向上游触发后台 Task 物理取消。

---

## 2. 核心路由与代理行为（[langgraph_proxy.py]( /backend/src/interface/routers/langgraph_proxy.py)）

| 接口路径 | HTTP 方法 | 功能描述 | upstream 透传逻辑 |
| :--- | :--- | :--- | :--- |
| `/threads` | POST | 创建新 Thread | 自动同步创建本系统的 `sessions` 索引，透传 upstream |
| `/threads/{id}/runs/stream` | POST | 核心流式执行 | 校验所有权 ➔ 注入 `internal_jwt` ➔ 代理 SSE 流 ➔ 监听断连取消 |
| `/threads/{id}/history` | GET / POST | 历史 Checkpoints 状态查询 | 兼容官方 SDK 的 POST JSON 查询与 GET Query，透传 upstream |
| `/threads/{id}/state` | GET | 查询最新状态快照 | 获取当前活跃状态，优雅降级保证 SDK 协议对齐 |
| `/threads/{id}/runs/{run_id}/cancel` | POST | 强制终止正在运行的任务 | 触发 upstream 终止 run，释放沙箱与大模型计算资源 |
| `/assistants/{id}` | GET | 校验智能体有效性 | 透传 upstream 验证 Assistant 配置 |

---

## 3. 关键代理机制实现

### 3.1 历史状态双轨方法透传（`GET` & `POST`）
官方 JS SDK `client.threads.getHistory(threadId, options)` 在底层通过 POST 发送包含 `before: { configurable: { ... } }` 的请求。网关采用通用路由代理：
```python
@router.api_route("/threads/{thread_id}/history", methods=["GET", "POST"])
async def proxy_thread_history(...):
    await assert_thread_belongs_to_user(thread_id, user_id, db)
    await _ensure_thread_in_upstream(thread_id, user_id)
    # 动态根据 request.method 转发 GET 或 POST JSON Body
    ...
```

### 3.2 客户端断连感知与后台真取消
用户在浏览器关闭标签页或点击“停止生成”时：
```python
try:
    async for chunk in resp.aiter_bytes():
        if await request.is_disconnected():
            logger.info("client_disconnected_triggering_cancel", thread_id=thread_id, run_id=run_id)
            # 立即向 upstream 发送真实取消请求
            await client.post(f"{upstream_url}/cancel", headers=headers)
            break
        yield chunk
```
彻底避免大模型在后台继续空转打字浪费 Token 与沙箱算力。
