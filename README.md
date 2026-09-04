# X Agent Enterprise Platform

> 一个基于 **LangGraph 原生架构** 驱动的 **LLM Agent 任务调度与人机协同企业级平台**。原生具备 **LangGraph StateGraph 状态机、人机协同审批（HITL Interrupt / Resume）、安全隔离沙箱（Go Daemon + Docker）、Chromium 浏览器 CDP 自动化、模型上下文协议（MCP）、多智能体协同（A2A）、双层纵深鉴权、服务端真实物理 Cancel、文件多版本管理与极致前端流式动静分离**。

![image](./spec/images/image.png)

![image](./spec/images/CDP.png)

![image](./spec/images/codepreview.png)

![image](./spec/images/hitl.png)

---

## 🌟 核心特性全景

| 能力维度 | 核心技术方案 | 特性 |
|---|---|---|
| **LangGraph 状态机引擎** | **StateGraph + ReAct 闭环** | 遵循 LangGraph 原生规范构建 `agent_node` 与 `tools_node`，支持 Checkpointer 快照存储、多分支推演与状态自愈 |
| **人机协同 (HITL)** | **`interrupt()` 挂起 + `command.resume` 恢复** | 智能识别高危系统指令与文件覆盖，图状态物理挂起并向前端推送结构化表单；用户决策后原地无缝恢复推演 |
| **安全纵深双层鉴权** | **网关会话校验 + 内部短期 JWT + 协议级隔离** | 网关强校验 Session 归属并签发 60s 内部短效 JWT，Runtime 借助 `@my_auth.on.threads` 实现协议层租户资源硬隔离 |
| **服务端物理级 Cancel** | **`runs.cancel(action="interrupt")`** | 前端点击停止直连 LangGraph 服务端物理强杀推理与网络长连接，彻底避免假取消造成的算力空转与 Token 浪费 |
| **物理隔离沙箱** | **Docker + Go Sandbox Daemon (:5050)** | 独立执行子进程组、超时强杀熔断 (`SIGKILL`)、工作区文件系统隔离、沙箱文件操作直连落库 PostgreSQL `files` & `file_versions` |
| **CDP 浏览器自动化** | **Chrome DevTools Protocol (CDP)** | 无头 Chromium 隔离会话，提供 `open`、`click`、`snapshot`、`screenshot`、`close` 5 大高阶工具，递归语义 DOM 树与元素自动编号 |
| **生态扩展与工具集成** | **MCP (stdio/sse) + Google A2A + Redis 热刷新** | 统一 Tool 抽象分发、多租户内存热缓存、用户动态配置 MCP/A2A 后通过 Redis Pub/Sub 通道秒级热失效 |
| **极致流式渲染** | **Next.js 14 + SDK useStream + 动静分离** | 历史消息 0 重绘、当前流式叶子组件 60fps rAF 平滑吸底打字机、触顶 `client.threads.getHistory` 懒加载结合滚动锚定精确补偿 |

---

## 🏗️ 系统全栈拓扑架构

```
                                      ┌─────────────────────────────────────────────────────────┐
                                      │              Next.js 14 前端客户端                      │
                                      │  - @langchain/langgraph-sdk/react (useStream)           │
                                      │  - 动静分离 (Static History 0 重绘 + ActiveLeaf 60fps)  │
                                      │  - HitlFormCard (人机协同动态审批卡片 / command.resume) │
                                      │  - 触顶懒加载更早历史 (getHistory + 滚动锚定无闪烁)     │
                                      └────────────────────────────┬────────────────────────────┘
                                                                   │ HTTP REST / SSE Stream
                                                                   ▼
                                      ┌─────────────────────────────────────────────────────────┐
                                      │               FastAPI 统一网关服务 (:8000)              │
                                      │  - 外部用户 JWT 认证 & 会话所有权强校验                 │
                                      │  - 滑动窗口速率限流 & 单用户并发配额 (429 拦截)         │
                                      │  - 签发 60s 短期内部服务 JWT (HS256 纵深防御)           │
                                      │  - 监听客户端异常断连，自动向下游下发 run cancel        │
                                      │  - 流式结束异步持久化消息至 PostgreSQL messages 表      │
                                      └─────────────┬─────────────────────────────┬─────────────┘
                                                    │                             │
                        ┌───────────────────────────┘                             └───────────────────────────┐
                        ▼                                                                                     ▼
           ┌─────────────────────────┐                                                           ┌─────────────────────────┐
           │   PostgreSQL 17 数据库   │                                                           │      Redis 7 内存集群   │
           │  - users / sessions     │                                                           │  - 跨进程工具缓存失效   │
           │  - messages             │                                                           │    广播通道             │
           │  - files / versions     │                                                           │    (sys:tool_cache_     │
           │  - ecosystem_configs    │                                                           │     invalidation)       │
           │  - LangGraph            │                                                           │  - 分布式锁与速率计数器 │
           │    Checkpoints 状态快照 │                                                           └────────────┬────────────┘
           └─────────────────────────┘                                                                        │
                        ▲                                                                                     │ PubSub
                        │ (Checkpointer 持久化 & 文件直连落库)                                                 │ 订阅失效
                        └───────────────────────────────┬─────────────────────────────────────────────────────┘
                                                        │
                                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   LangGraph Agent 运行时 (agent-runtime :8123)                                             │
│                                                                                                                           │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                            纵深防御安全鉴权 (auth.py)                                             │   │
│   │   - @my_auth.authenticate: 验签网关内部短期 JWT，抽取真实租户 user_id                                             │   │
│   │   - @my_auth.on.threads: 强制限定资源归属 {"owner": ctx.user.identity}，杜绝越权串会话                             │   │
│   └─────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘   │
│                                                         ▼                                                                 │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                   ReAct 状态图引擎 (StateGraph Topology)                                          │   │
│   │                                                                                                                   │   │
│   │           [START] ──► [ agent_node ] ◄─────────────────────────────────────────────┐                              │   │
│   │                              │                                                     │                              │   │
│   │                              ▼ (should_continue 条件分支)                           │                              │   │
│   │                   ┌──────────┴──────────┐                                          │                              │   │
│   │            [无 tool_calls]       [有 tool_calls]                                   │                              │   │
│   │                   │                     │                                          │                              │   │
│   │                   ▼                     ▼                                          │                              │   │
│   │                 [END]             ┌────────────┐                                   │                              │   │
│   │                                   │ tools_node │ ──────────────────────────────────┘                              │   │
│   │                                   └─────┬──────┘                                                                  │   │
│   │                                         │                                                                         │   │
│   │                             (高危操作 / 审批请求)                                                                 │   │
│   │                                         ▼                                                                         │   │
│   │                                [ interrupt() 挂起 ] ──► (前端提交决策后 command.resume 恢复)                      │   │
│   └─────────────────────────────────────────┬─────────────────────────────────────────────────────────────────────────┘   │
│                                             │                                                                             │
│                                             ▼                                                                             │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                  多租户动态工具调度中心 (ToolRegistry)                                            │   │
│   │                                                                                                                   │   │
│   │  - [切面] 审计日志 -> 高危拦截 -> 超时熔断 -> 数据库同步落库                                                      │   │
│   │  - [路由] ┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐                               │   │
│   │           │   Builtin Tools │   Sandbox Tools │   Browser Tools │   MCP / A2A     │                               │   │
│   │           │   时间/计算/网络│   命令/读写文件 │   CDP 浏览器 5套│   外部协议生态  │                               │   │
│   │           └────────┬────────┴────────┬────────┴────────┬────────┴────────┬────────┘                               │   │
│   └────────────────────┼─────────────────┼─────────────────┼─────────────────┼────────────────────────────────────────┘   │
└────────────────────────┼─────────────────┼─────────────────┼─────────────────┼────────────────────────────────────────────┘
                         │                 │                 │                 │
                         │                 │ HTTP / REST     │ CDP WebSocket   │ stdio / SSE
                         ▼                 ▼ (:5050)         ▼ (:9222)         ▼
              ┌───────────────────────────────────────────────────────┐   ┌─────────────────────────┐
              │             Docker 物理隔离沙箱 (agent-sandbox)       │   │    外部 MCP / A2A 服务  │
              │  - Go Sandbox Daemon (:5050)                          │   │ - SQLite / GitHub MCP   │
              │  - /exec 隔离命令执行 & 进程树强杀 (SIGKILL)          │   │ - A2A 外部专家智能体    │
              │  - /fs 工作区文件读写 (路径防穿透)                    │   └─────────────────────────┘
              │  - Headless Chromium (CDP 页面探针与编号 DOM 交互)    │
              └───────────────────────────────────────────────────────┘
```

---

## 🧩 核心机制详解

### 1. 🧠 LangGraph 状态机与 ReAct 闭环
* **原生 StateGraph 编排**：定义于 [agent-runtime/agent.py](agent-runtime/agent.py)，采用标准 `AgentState(messages=...)`，通过 `add_messages` 实现对话与工具调用的幂等增量追加。
* **Checkpointer 检查点持久化**：生产环境通过环境变量 `POSTGRES_URI` 自动由平台接管持久化；单机开发支持内存调试，具备无缝断点续跑能力。

### 2. 🛡️ HITL 人机在环协同与安全审批
* **原生 `interrupt()` 挂起**：在 [tools_node.py](agent-runtime/src/nodes/tools_node.py) 内置安全策略，自动识别高危 Shell 命令（`rm -rf`, `delete`, `mkfs` 等）与文件覆写，直接触发 `interrupt({"action_requests": [...]})` 挂起图运行。
* **交互卡片与 `command.resume`**：前端通过 [HitlFormCard.tsx](frontend/src/components/chat/HitlFormCard.tsx) 渲染动态单选/确认表单，用户确认后前端调用 `command.resume` 原地恢复推演。

### 3. 🌐 浏览器 CDP 自动化（5 大高阶工具）
* **会话隔离**：通过 `_get_session_id(ctx)` 维护与 Chromium Incognito 绑定的独立 BrowserContext，避免 Cookie/Session 串扰。
* **编号 DOM 交互**：基于递归语义 DOM 树探针为页面所有交互按钮（含 Vue/React 伪按钮）自动编排 `[数字编号]`，LLM 仅需传递数字即可完成真实点击。
* **5 大核心工具**：`browser_open_page`、`browser_click`、`browser_get_snapshot`、`browser_screenshot`、`browser_close_page`。

### 4. ⚡ 极致流式渲染与动静分离架构
* **动静分离（0 重绘）**：已完成的历史消息轮次在打字期间完全冻结；当前打字内容下沉在独立的 [ActiveStreamingTurn.tsx](frontend/src/components/chat/ActiveStreamingTurn.tsx) 叶子组件中，内部结合 `requestAnimationFrame`（16.6ms）平滑吸底。
* **触顶懒加载更早历史**：顶部设置 `IntersectionObserver` 哨兵，触顶自动调用 `client.threads.getHistory`，并通过 `scrollHeight` 差值计算补偿 `scrollTop` 滚动锚定，视口内容绝对静止零闪烁。

---

## 🚀 模块化 Docker Compose 容器编排

系统遵循**各子模块自内聚、独立维护自身容器定义**的架构原则，根目录不存放单体编排文件，各模块在各自目录下独立管理 `docker-compose.yml`：

### 模块编排分布与职责

| 模块目录 | 编排文件 | 容器服务 | 默认端口 | 职责定位 |
|---|---|---|---|---|
| **`sandbox/`** | `sandbox/docker-compose.yml` | `agent-sandbox` | `5050` | 物理隔离沙箱容器（含 Chromium 浏览器与 Go Daemon） |
| **`backend/`** | `backend/docker-compose.yml` | `postgres`<br/>`redis`<br/>`backend-api` | `5432`<br/>`6379`<br/>`8000` | 基础设施中间件与 FastAPI 统一业务接口网关 |
| **`agent-runtime/`** | `agent-runtime/docker-compose.yml` | `agent-runtime` | `8123` | LangGraph 核心智能体运行时（负责 REST/SSE、租户鉴权与 StateGraph 执行） |
| **`frontend/`** | `frontend/docker-compose.yml` | `agent_frontend` | `3000` | Next.js 14 Web 客户端界面 |

### 各模块启动指引

```bash
# 1. 启动沙箱守护服务 (Docker + Chromium)
cd sandbox && docker compose up -d

# 2. 启动基础存储与后端网关 (Postgres, Redis & FastAPI)
cd backend && docker compose up -d

# 3. 启动 LangGraph 运行时
cd agent-runtime && docker compose up -d

# 4. 启动前端客户端
cd frontend && docker compose up -d
```

---

## 🛠️ 本地敏捷开发指南

### 1. 启动后端与依赖中间件

```bash
# 步骤 1: 启动依赖中间件 (PostgreSQL & Redis)
cd backend && docker compose up -d postgres redis

# 步骤 2: 启动 LangGraph 运行时（端口 8123）
cd ../agent-runtime
cp .env.example .env
uv sync
uv run langgraph dev --host 0.0.0.0 --port 8123 --no-browser

# 步骤 3: 启动后端 FastAPI 网关（端口 8000）
cd ../backend
cp .env.example .env  # 配置 OPENAI_API_KEY / 数据库连接等
uv sync
uv run alembic upgrade head
uv run uvicorn api_main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 启动前端应用

```bash
cd frontend
npm install
npm run dev -- --port 3000
```

### 3. 运行全套自动化测试套件

```bash
# 1. 运行 agent-runtime 智能体与工具测试 (CDP、HITL 审批节点、多租户缓存)
cd agent-runtime
uv run python3 -m pytest tests/

# 2. 运行后端网关与鉴权测试 (LangGraph 代理、JWT 验证、会话隔离)
cd ../backend
uv run python3 -m pytest tests/test_langgraph_proxy.py
```

---

## 📁 详细架构设计文档

- 📘 **[Agent Runtime 核心架构与状态机规范](spec/agentruntime/01_核心架构与状态机机制.md)**
- 🔒 **[Agent Runtime 鉴权机制与多租户隔离](spec/agentruntime/02_鉴权机制与多租户隔离.md)**
- 🤝 **[Agent Runtime HITL 人机协同与安全审批机制](spec/agentruntime/03_HITL人机协同与安全审批机制.md)**
- 🛠️ **[Agent Runtime 动态多租户工具注册与缓存机制](spec/agentruntime/04_动态多租户工具注册与缓存机制.md)**
- 🌐 **[Sandbox 核心机制与通信时序设计](spec/backend/01_Sandbox核心机制与通信时序.md)**
- 🖥️ **[Sandbox CDP 浏览器工具与 DDD 架构规范](spec/backend/04_Sandbox_CDP浏览器工具与DDD设计.md)**
- 🚪 **[LangGraph 统一网关代理设计](spec/backend/08_LangGraph统一网关代理设计.md)**
- 💻 **[前端流式动静分离、接力交接与触顶懒加载优化](spec/frontend/04_流式动静分离_接力交接与触顶懒加载优化.md)**
