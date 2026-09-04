# agent-runtime — LangGraph P0 单节点 Agent

> **P0 阶段**：极简 LangGraph 单节点（仅 LLM Node），专注打通 **前端流式渲染 ↔ 网关代理鉴权 ↔ LangGraph 推理** 基础链路。

---

## 目录结构

```
agent-runtime/
├── agent.py          # LangGraph 图定义（单 LLM Node）
├── auth.py           # LangGraph Auth 中间件（内部 JWT 校验 + 多租户隔离）
├── langgraph.json    # LangGraph Server 配置（graph 注册 + auth + env）
├── pyproject.toml    # 依赖声明（uv 管理）
├── requirements.txt  # 兼容旧版 pip（可保留）
├── Dockerfile        # 容器构建文件（使用 uv）
├── .env              # 本地运行环境变量（不提交 Git）
└── .env.example      # 环境变量示例
```

---

## 环境变量配置（.env）

复制示例文件并按实际情况修改：

```bash
cp .env.example .env
```

| 变量名 | 说明 | 示例值 |
|---|---|---|
| `LLM_BASE_URL` | LLM API Base URL | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称 | `deepseek-chat` |
| `LLM_API_KEY` | LLM API Key | `sk-xxx` |
| `DATABASE_URL` | PostgreSQL 连接串（用于 Checkpointer） | `postgresql://postgres:postgres@localhost:5432/app` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `INTERNAL_JWT_SECRET` | 内部服务间 JWT 签名密钥（需与 backend 一致） | `internal-service-secret-key-32-chars` |
| `HOST` | 监听地址 | `0.0.0.0` |
| `PORT` | 监听端口 | `8123` |

---

## 本地开发启动（使用 uv）

### 前置条件

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 已安装
- PostgreSQL 与 Redis 服务已运行（可复用 `docker-compose.yml` 中的服务）

### 安装 uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 或通过 pip
pip install uv
```

### 安装依赖

```bash
cd agent-runtime

# 创建虚拟环境并同步依赖（自动读取 pyproject.toml）
uv sync
```

### 启动 LangGraph Dev Server

```bash
# 启动（热重载，开发模式，不打开浏览器）
uv run langgraph dev --host 0.0.0.0 --port 8123 --no-browser
```

服务启动后监听 `http://0.0.0.0:8123`，LangGraph Studio 见 `http://localhost:8123/docs`。

### 验证服务健康

```bash
# 查询 assistants 列表（应返回 "agent" 图）
curl -X POST http://localhost:8123/assistants/search \
  -H 'Content-Type: application/json' \
  -d '{}'

# 健康检查
curl http://localhost:8123/info
```

---

## 添加 / 更新依赖

```bash
# 添加新依赖
uv add <package-name>

# 升级依赖
uv lock --upgrade-package <package-name>

# 同步更新虚拟环境
uv sync
```

---

---

## Docker 容器化运行

### 1. 使用模块内 docker-compose 启动（推荐）

在 `agent-runtime/` 目录下直接使用模块独立的 `docker-compose.yml`：

```bash
cd agent-runtime

# 构建并后台启动 agent-runtime 容器（端口 8123）
docker compose up -d --build
```

### 2. 使用 Docker 单独构建与运行

```bash
cd agent-runtime

# 构建镜像
docker build -t agent-runtime:latest .

# 启动容器（映射 8123 端口，挂载 .env）
docker run -d \
  -p 8123:8123 \
  --env-file .env \
  --name agent-runtime \
  agent-runtime:latest
```

---

## 架构说明（P0）

```
前端 useStream (SDK)
    │ POST /threads/{id}/runs/stream
    ↓
backend FastAPI 网关 (:8000)
    ├── 校验 JWT，验证 session 归属
    ├── 幂等 POST /threads 确保 LangGraph 侧 thread 存在（并附加 owner 身份）
    ├── 注入内部 JWT（Internal JWT，TTL 60s）
    └── 透传 SSE 流至前端
    │
    ↓ 内部 JWT 代理
agent-runtime LangGraph Server (:8123)
    └── auth.py：验证 Internal JWT，提取 user_id
    └── agent.py：单 LLM Node → ChatOpenAI.ainvoke → 返回 messages
```

### 关键设计

- **Thread ID 对齐**：`session_id`（业务 DB）= `thread_id`（LangGraph），一一对应
- **内部 JWT 鉴权**：网关签发短效 JWT（60s TTL），LangGraph auth.py 验证
- **多租户隔离**：auth.py 通过 `owner` 字段自动过滤 thread 归属
- **流式落库**：proxy 在 SSE 完成后异步将 AI 回复写入业务 DB messages 表

---

## 图结构（P0 极简）

```python
START → llm_node → END
```

`llm_node`：直接调用 `ChatOpenAI.ainvoke(state["messages"])`，返回 AI 消息。

后续 P1/P2 阶段将在此基础上扩展工具调用节点、HITL 中断节点等。
