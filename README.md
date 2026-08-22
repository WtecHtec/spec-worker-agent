# Antigravity Agent Enterprise Platform

> 一个高可靠、企业级 Agent 任务流调度与人机协同平台。具备 **多步思维链推理、工具调用、人机协同（HITL）、断点续传、分布式锁、Worker 故障自愈与高性能流式渲染** 能力。

---

## 🌟 核心特性全景

| 能力维度 | 核心技术方案 | 生产级特性 |
|---|---|---|
| **任务流调度** | Redis Stream + Consumer Group 异步解耦 | 生产者-消费者模型，HTTP 响应极速，Worker 水平弹性扩展 |
| **实时推流** | Server-Sent Events (SSE) + Redis Pub/Sub | 支持 `from_step` 历史查库补齐 + 实时广播无缝切换 |
| **人机协同 (HITL)** | 状态机驱动 + 交互决策卡片 | 遇到高危/歧义操作自动暂停，支持单选/文本决策，提交后断点自动恢复 |
| **可靠性与自愈** | Checkpoint + RedisLock + 优雅退出 | 心跳检测续期、`SIGTERM` 自动转 PAUSED、崩溃僵尸任务自动重入队、HITL 超期兜底 |
| **生产准入与安全** | Redis 窗口限流 + 429 配额拦截 | 单用户并发任务数限制、全链路 `X-Request-ID` 追踪、标准统一错误结构 |
| **极致流式体验** | `requestAnimationFrame` 驱动打字机 | 60FPS 逐帧消费、动态防积压缓冲加速、React.memo 隔离历史重绘、一键复制代码 |

---

## 🏗️ 系统全栈架构

```
                                 ┌───────────────────────────────┐
                                 │    Next.js 14 前端客户端      │
                                 │  - useTaskStream (SSE 监听)   │
                                 │  - useTypewriter (rAF 吐字)   │
                                 │  - HitlCard (人机交互卡片)    │
                                 └───────────────┬───────────────┘
                                                 │ HTTP / SSE
                                                 ▼
                                 ┌───────────────────────────────┐
                                 │     FastAPI 后端 API 服务     │
                                 │  - REST API & JWT 鉴权        │
                                 │  - 速率限流与全局并发配额     │
                                 │  - 任务入队 (XADD)            │
                                 └───────┬───────────────┬───────┘
                                         │               │
                     ┌───────────────────┘               └───────────────────┐
                     ▼                                                       ▼
        ┌─────────────────────────┐                             ┌─────────────────────────┐
        │   PostgreSQL 17 数据库   │                             │      Redis 7 内存集群   │
        │  - users / sessions     │                             │  - Stream 任务队列      │
        │  - messages / tasks     │                             │  - Pub/Sub 事件广播     │
        │  - task_steps / ckpt    │                             │  - RedisLock 分布式锁   │
        │  - hitl_requests        │                             │  - 速率计数器 (429)     │
        └─────────────────────────┘                             └────────────┬────────────┘
                                                                             │ XREADGROUP
                                                                             ▼
                                                                ┌─────────────────────────┐
                                                                │  Worker 任务执行引擎    │
                                                                │  - 分布式锁心跳续期     │
                                                                │  - 驱动 Agent 推理步骤   │
                                                                │  - Checkpoint 落库      │
                                                                │  - 广播步骤到 Pub/Sub   │
                                                                │  - 僵尸任务与超时巡检   │
                                                                └─────────────────────────┘
```

---

## 🚀 Docker Compose 部署配置

项目已完整配置容器化编排文件 `docker-compose.yml`，包含数据库、Redis、API 服务、Worker 引擎与前端应用共 5 个容器服务。

### 容器服务清单

| 服务名称 | 镜像 / 构建上下文 | 宿主机端口 | 说明 |
|---|---|---|---|
| `postgres` | `postgres:17-alpine` | `5432` | 关系型数据库，带健康检查探针 |
| `redis` | `redis:7-alpine` | `6379` | 任务队列、事件广播与分布式锁 |
| `backend-api` | `./backend/Dockerfile` | `8000` | FastAPI API Server (自动执行 Alembic 迁移) |
| `backend-worker` | `./backend/Dockerfile` | - | 后台 Worker 消费进程 |
| `frontend` | `./frontend/Dockerfile` | `3000` | Next.js 14 生产环境客户端 |

### 启动命令（准备好后可执行）

```bash
# 1. 启动全套服务（后台运行）
docker compose up -d

# 2. 查看各容器健康状态
docker compose ps

# 3. 查看实时日志流
docker compose logs -f

# 4. 停止所有服务
docker compose down
```

---

## 🛠️ 本地开发运行方式

### 1. 启动后端
```bash
cd backend
uv sync
uv run alembic upgrade head
# 启动 API
uv run uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload
# 启动 Worker
uv run python3 worker_main.py
```

### 2. 启动前端
```bash
cd frontend
npm install
npm run dev -- --port 3000
```

### 3. 运行后端自动化测试套件
```bash
cd backend
uv run python3 test_p1.py  # P1: HITL、取消任务、并发 409
uv run python3 test_p2.py  # P2: 分布式锁、僵尸任务恢复、PAUSED 优雅退出恢复、HITL 超时
uv run python3 test_p3.py  # P3: Liveness/Readiness 探针、Request-ID、统一错误、限流与配额
```

---

## 📁 详细技术文档

- 📖 [后端架构与 Worker 机制详解 (backend/README.md)](backend/README.md)
- 💻 [前端架构与 rAF 流式渲染详解 (frontend/README.md)](frontend/README.md)
- 📊 [功能优先级演进矩阵 (frontend_feature_priority.md)](frontend_feature_priority.md)
