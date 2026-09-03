# 07. LangGraph 架构演进与 P0 单节点落地规范

## 1. 架构演化背景与设计目标

### 1.1 背景
原系统采用自研的 `FastAPI Gateway + Redis Stream 队列 + 自研 Celery/Worker + Docker Sandbox` 架构。该架构在长期演进中存在以下痛点：
1. **取消无法物理中断**：前端发送 Cancel 请求后仅修改数据库任务状态为 `CANCELLED`，底层 Python/LLM 推理无法立即中断，持续消耗 Token 与计算资源。
2. **连接时序复杂**：客户端必须先 `POST /tasks` 获得 `task_id`，再发起 `EventSource` 订阅，存在高并发下的竞态条件与消息乱序风险。
3. **编排扩展困难**：自研 ReAct / Planner 状态机维护成本高，缺乏成熟的 Checkpoint 检查点版本机制与生态工具支持。

### 1.2 P0 核心目标
本阶段遵循**“Graph 极简（单 LLM 节点）、核心链路先行”**的原则，不引入复杂多节点与外部工具，全力攻坚并验证底层核心协议：
- **流式透传**：`前端 (useStream) ↔ 网关 (FastAPI Proxy) ↔ LangGraph Runtime (Port 8123)`
- **双层鉴权与租户隔离**：外部用户 JWT 鉴权 ↔ 网关签发内部短效 JWT ↔ LangGraph 原生 `Auth.on.threads` 隔离
- **服务端真中断**：前端停止生成直连 LangGraph `runs.cancel(action="interrupt")`，真正停止服务端 Token 消耗
- **消息持久化闭环**：流式传输完成或中断时，网关异步将完整或截断的文本写入业务库 `messages` 表

---

## 2. 整体架构与拓扑图

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Next.js / React)               │
│         @langchain/langgraph-sdk/react (useStream)      │
└────────────────────────────┬────────────────────────────┘
                             │ 1. Authorization: Bearer <user_jwt>
                             │ 2. POST /threads/{thread_id}/runs/stream
                             ▼
┌─────────────────────────────────────────────────────────┐
│                 后端网关 (FastAPI Proxy :8000)          │
│  - 验证用户 JWT，校验 thread_id (session_id) 归属权     │
│  - 幂等调用 LangGraph POST /threads 确保线程存在        │
│  - 签发短期内部服务 JWT (TTL 60s, HS256)               │
│  - 监听客户端断连，自动向 upstream 发起 run cancel     │
│  - 流式结束时异步聚合文本写入 PostgreSQL messages 表   │
└────────────────────────────┬────────────────────────────┘
                             │ 1. Authorization: Bearer <internal_jwt>
                             │ 2. POST /threads/{thread_id}/runs/stream
                             ▼
┌─────────────────────────────────────────────────────────┐
│            LangGraph Runtime (agent-runtime :8123)      │
│  - auth.py: 校验 internal_jwt，通过 @on.threads 隔离    │
│  - agent.py: START -> llm_node -> END                   │
│  - 模型驱动: ChatOpenAI (DeepSeek / OpenAI 兼容接口)   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 内部服务间鉴权与安全机制

### 3.1 令牌签发（Gateway 侧）
网关在验证用户外部 Token 确认合法身份后，通过 `mint_internal_jwt` 为当前用户生成一个短效内部 JWT（TTL=60s）：
- **Algorithm**: `HS256`
- **Secret**: `INTERNAL_JWT_SECRET`（后端与 Runtime 共享）
- **Payload Claims**:
  ```json
  {
    "user_id": "03816666-02e0-410c-99d9-f53856fa1e17",
    "iat": 1788410316,
    "exp": 1788410376,
    "iss": "spec-worker-gateway"
  }
  ```

### 3.2 令牌校验与多租户隔离（Runtime 侧）
在 `agent-runtime/auth.py` 中接入 LangGraph 原生鉴权机制：
```python
@my_auth.authenticate
async def authenticate(authorization: str) -> Auth.types.MinimalUserDict:
    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_internal_jwt(token)
    return {"identity": payload["user_id"]}

@my_auth.on.threads
async def authorize_threads(ctx: Auth.types.AuthContext, value: dict):
    # 作用域限定为 threads 资源，避免公共 Assistant 被误过滤
    return {"owner": ctx.user.identity}
```

> **踩坑与核心规范**：
> 1. 绝不能注册全局 `@my_auth.on`，否则由 `langgraph.json` 注册的系统公共 Assistant（`agent`）在查询时也会被过滤，导致 404 `Thread or assistant not found`。
> 2. 网关在调用 LangGraph 创建 Thread 时，必须显式传递 `metadata: {"owner": user_id}`，否则 `Runs.put` 在执行校验时会因缺少 `owner` 匹配判定无权访问而拒绝执行。

---

## 4. 网关代理端点设计与契约

| HTTP 方法 | 网关暴露路径 | 目标透传 Upstream 路径 | 核心业务处理逻辑 |
|---|---|---|---|
| `POST` | `/threads/{thread_id}/runs/stream` | `/threads/{thread_id}/runs/stream` | 1. 校验会话所有权<br/>2. 幂等创建 Thread 并附带 owner 元数据<br/>3. 自动对齐 assistant_id 为 UUID<br/>4. 双向透传 SSE 流并在结束时异步持久化消息 |
| `POST` | `/threads/{thread_id}/runs/{run_id}/cancel` | `/threads/{thread_id}/runs/{run_id}/cancel` | 携带 `{"action": "interrupt", "wait": true}`，物理级中断当前运行中的 Run |
| `GET` | `/threads/{thread_id}/state` | `/threads/{thread_id}/state` | SDK 初始化调用。若 Thread 刚创建无 Checkpoint，网关兜底返回合法空 State 对象，杜绝 404 |
| `GET` | `/threads/{thread_id}/history` | `/threads/{thread_id}/history` | 透传查询该 Thread 的历史快照列表 |
| `GET` | `/assistants/{assistant_id}` | `/assistants/{assistant_id}` | SDK 校验 Assistant 存在性代理 |
| `POST` | `/assistants/search` | `/assistants/search` | 透传查询 Assistant 列表 |

---

## 5. 消息持久化与状态治理

当 SSE 响应流通过网关代理直推前端时，网关在后台并发维护状态机：
1. **输入落库**：代理在向 upstream 发起连接前，解析 payload 中的首条/末条用户消息，同步写入 PostgreSQL 的 `messages` 表（`role="USER"`）。
2. **增量累加与截断持久化**：
   - 监听每个 chunk：通过正则与 JSON 解析同时抓取 `run_id` 与增量文本（兼容 `values`, `updates`, `partial` 模式）。
   - 连接正常关闭：写入 `role="AGENT"`, `status="done"`。
   - 客户端断开连接（如用户关闭标签页或网络中断）：`request.is_disconnected()` 触发，网关向 Runtime 发起 `cancel_upstream_run`，并将已生成的局部文本存入数据库，标记为 `status="cancelled"`。

---

## 6. agent-runtime 工程化与运行管理

### 6.1 包管理标准：uv
`agent-runtime` 统一使用现代 Python 包管理器 `uv` 进行依赖锁定与构建，不再依赖散装 pip：
- **依赖声明**：`agent-runtime/pyproject.toml`
- **安装与同步**：`uv sync`
- **本地启动**：`uv run langgraph dev --host 0.0.0.0 --port 8123 --no-browser`

### 6.2 Docker 构建标准
```dockerfile
FROM python:3.11-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/
WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev
COPY . .
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8123
CMD ["uv", "run", "langgraph", "dev", "--host", "0.0.0.0", "--port", "8123", "--no-browser"]
```
