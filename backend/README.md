# X Agent - 后端服务 (Backend)

基于 **FastAPI + SQLAlchemy 2.0 Async + Redis Stream + PostgreSQL** 构建的高可靠企业级 Agent 任务流调度系统。

---

## 一、核心架构设计

系统采用**读写与执行分离**的生产者-消费者架构：

```
                      ┌──────────────────────────────────────────────────────────┐
                      │                 FastAPI (api_main.py)                    │
                      │  - 提供 RESTful 接口 (Auth / Sessions / Messages / HITL) │
                      │  - SSE 事件流代理 (/tasks/{id}/stream)                   │
                      │  - 写入用户消息，生成 Task 并推入 Redis Stream           │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │ (生产者: XADD)
                                                   ▼
                                     ┌───────────────────────────┐
                                     │    Redis Stream 任务队列   │
                                     └─────────────┬─────────────┘
                                                   │ (消费者: XREADGROUP)
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                Worker (worker_main.py)                   │
                      │  - 分布式锁争抢 (RedisLock SET NX EX + Lua原子释放)       │
                      │  - 驱动 AgentExecutor 逐步推理 (思考 / 调工具 / 最终报告)│
                      │  - 每步落库持久化 (task_steps) 与 Checkpoint 状态保存    │
                      │  - 实时往 Redis Pub/Sub 广播步骤事件与结果               │
                      │  - 后台巡检：僵尸任务回收 / PAUSED 启动恢复 / HITL 超时  │
                      └──────────────────────────────────────────────────────────┘
```

---

## 二、为什么需要独立的 `worker_main.py`？

在 Agent 系统开发中，**绝对不能把 Agent 的长耗时执行逻辑直接写在 HTTP API 请求处理函数中**。独立 `worker_main.py` 的核心价值在于：

### 1. HTTP 线程与长耗时任务解耦
- Agent 执行一个复杂任务（如多步思维链推理、查询数据库、调用三方 API、生成长文本）通常需要耗费 **数秒到数分钟**。
- 若在 FastAPI 路由处理函数中同步执行，会占满 HTTP Worker 线程池，导致其他用户的简单请求（如登录、拉取消息、心跳探针）被严重阻塞乃至超时（504 Gateway Timeout）。
- **解耦后**：API 请求仅需 **几毫秒** 即可完成「入库 + 推入 Redis Stream + 返回 `task_id`」，前端拿到 ID 后通过 SSE 异步接收进度。

### 2. 水平弹性扩展（Horizontal Scaling）
- 通过 Redis Stream 消费者组机制（Consumer Group），可以随时根据任务积压量**启动多个 Worker 实例**（如 Worker 1、Worker 2、Worker 3...）。
- 每个 Worker 互不干扰地并发消费队列中的任务，极大提升集群整体吞吐能力。

### 3. 分布式锁互斥与防重跑 (`RedisLock`)
- 多个 Worker 并行消费时，通过 Redis `SET task:lock:{id} NX EX` 获取独占锁，防止同一任务被多个 Worker 同时执行。
- Worker 在执行循环中启动后台协程**自动心跳续期**，执行完毕后通过 Lua 脚本原子释放。

### 4. 故障恢复与断点续传 (Checkpoint & Crash Recovery)
- **优雅退出 (`SIGTERM`)**：Worker 收到终止信号时，安全中断当前步骤，将任务标记为 `PAUSED(worker_shutdown)` 并记录最后完成的 `step_index`；Worker 重启时由 `recover_paused_tasks` 自动拉起继续执行。
- **僵尸任务回收 (`recover_zombie_tasks`)**：如果 Worker 进程意外崩溃或断电失联，后台巡检服务检测到超过心跳超时的 `RUNNING` 任务，自动读取 Checkpoint 重置为 `PENDING` 并重新入队。
- **HITL 超时自动兜底 (`process_expired_hitl`)**：当等待人工审批超期时，依据预设规则自动标记失败或按默认动作继续执行。

---

## 三、核心机制详解

### 1. SSE 增量推流与历史补发
- 客户端请求 `GET /tasks/{id}/stream?from_step=N`：
  - **历史补发**：服务端优先查询数据库 `task_steps` 表中 `step_index > N` 的历史记录逐条推给客户端；
  - **实时切换**：历史补发完毕后，无缝接入 Redis Pub/Sub 订阅通道（`task:{id}:events`），实时推送后续生成的步骤与完成事件。

### 2. 人机协同闭环 (HITL - Human In The Loop)
1. Worker 遇到需要人工确认的工具调用（如高危写操作、异常处理），创建 `hitl_requests` 记录，将 Task 置为 `WAITING_HUMAN`，并广播 `hitl_created` 事件。
2. 前端展示专属交互决策卡片。
3. 用户提交选择或补充输入 (`POST /tasks/{id}/hitl/{id}/respond`)。
4. 服务端将决策落库，更新状态为 `PENDING`，并将携带 `resume_from_step` 的任务重新推入 Redis Stream，Worker 从断点无缝继续执行。

### 3. 并发安全与生产准入
- **单会话并发锁**：检测到同一会话已有未完结任务时，`POST /sessions/{id}/messages` 直接返回 `409 Conflict`。
- **单用户并发配额**：单用户活跃任务数超过 `max_concurrent_tasks`（默认 3）时，返回 `429 Quota Exceeded`。
- **全局限流**：基于 Redis 时间窗口计数器的 `RateLimitMiddleware`，响应头携带 `X-RateLimit-*`。
- **全链路追踪**：`RequestContextMiddleware` 统一注入 `X-Request-ID` 与 `X-Process-Time`。

---

## 四、主要 API 端点列表

| 模块 | 方法 | 路径 | 说明 |
|---|---|---|---|
| **Auth** | `POST` | `/auth/register` | 用户注册 |
| **Auth** | `POST` | `/auth/login` | 用户登录（获取 JWT Bearer Token） |
| **Sessions** | `GET` | `/sessions` | 获取当前用户的会话列表 |
| **Sessions** | `POST` | `/sessions` | 创建新会话 |
| **Messages** | `GET` | `/sessions/{id}/messages` | 获取指定会话的全量历史消息 |
| **Messages** | `POST` | `/sessions/{id}/messages` | 发送消息（创建 Task 并推入 Redis Stream） |
| **Tasks** | `GET` | `/tasks/{id}` | 查询任务详情与当前状态 |
| **Tasks** | `GET` | `/tasks/{id}/steps` | 查询任务已落库的步骤列表 |
| **Tasks** | `POST` | `/tasks/{id}/cancel` | 主动终止/取消进行中的任务 |
| **Tasks** | `GET` | `/tasks/{id}/stream` | **SSE 实时步骤事件流**（支持 `from_step`） |
| **HITL** | `GET` | `/tasks/{id}/hitl/pending` | 查询任务当前待处理的人工决策请求 |
| **HITL** | `POST` | `/tasks/{id}/hitl/{id}/respond` | 提交人工决策响应并恢复任务 |
| **Probes** | `GET` | `/health` | Liveness 存活探针 |
| **Probes** | `GET` | `/health/ready` | Readiness 就绪探针（检查 DB/Redis/Stream） |

---

## 五、本地运行与测试

### 1. 环境准备 (使用 uv)
```bash
cd backend
uv sync
```

### 2. 数据库迁移
```bash
uv run alembic upgrade head
```

### 3. 启动服务
```bash
# 终端 1：启动 API 服务
uv run python -m uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2：启动 Worker 执行进程
uv run python worker_main.py
```

### 4. 运行全量自动化测试
```bash
uv run python3 test_p1.py  # 验证 HITL、任务取消、断点续传、并发 409
uv run python3 test_p2.py  # 验证分布式锁、僵尸任务回收、PAUSED 重启恢复、HITL 超时
uv run python3 test_p3.py  # 验证健康探针、结构化日志追踪、统一错误格式、Redis 限流与并发配额
```