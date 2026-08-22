# LLM Worker Agent 核心系统架构与运行方案设计

> **核心定位**：专为**长任务处理、多用户并发、深度沙箱隔离、可靠断点恢复**打造的工业级 LLM Agent 运行时架构。  
> **设计哲学**：轻量原生控制核（无重型黑盒框架负担）、契约式工具抽象、分层记忆防御、双层协作循环（Planner + ReAct）。

---

## 一、 系统全景架构图

```
                                  ┌─────────────────────────────────────────────────────────┐
                                  │                     用户接入与交互层                      │
                                  │      Web 前端 (React / SSE 实时终端) / API Gateway      │
                                  └────────────────────────────┬────────────────────────────┘
                                                               │ 任务下发 / 状态监听
                                                               ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                 LLM Worker 核心调度节点                                                   │
│                                                                                                                           │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                       宏观规划层 (Planner Agent)                                                  │   │
│   │   - 目标解构 (Goal Decomposition) -> 动态任务 DAG (Plan State) -> 阶段进度评估与重规划 (Re-planning)             │   │
│   └─────────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┘   │
│                                                         │ 派发具体子任务 (Sub-task)                                       │
│                                                         ▼                                                                 │
│   ┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐   │
│   │                                       微观执行层 (ReAct Worker Agent)                                             │   │
│   │   - Thought (状态评估) -> Action (意图决策) -> Observation (沙箱/工具回填)                                        │   │
│   │   - 循环安全卫士: Max Steps 限制 + 动作指纹检测 (Loop Detector) + 自我纠偏提示 (Nudge)                           │   │
│   └──────────────────────────────┬────────────────────────────────────────────────────┬───────────────────────────────┘   │
│                                  │                                                    │                                   │
│                                  ▼                                                    ▼                                   │
│   ┌───────────────────────────────────────────────────────────┐  ┌────────────────────────────────────────────────────┐   │
│   │                     统一 Tool 调度管道                    │  │                   上下文记忆装配器                 │   │
│   │                   (Tool Registry & AOP)                   │  │              (Context Assembly Pipeline)           │   │
│   │                                                           │  │                                                    │   │
│   │  - [切面] 审计日志 -> HITL 拦截 -> 超时熔断 -> 大输出截断 │  │  - System Prompt (独立 Markdown 模板渲染)           │   │
│   │  - [适配] ┌─────────────┬─────────────┬─────────────┐     │  │  - User Preferences (用户偏好画像)                  │   │
│   │           │ Sandbox Tool│  MCP Tool   │  A2A Tool   │     │  │  - Working Memory (近期步骤 + Token 滑动窗口)       │   │
│   │           └─────────────┴─────────────┴─────────────┘     │  │  - Checkpoint Context (阶段性长摘要)               │   │
│   └──────────────────────────────┬────────────────────────────┘  └────────────────────┬───────────────────────────────┘   │
└──────────────────────────────────┼────────────────────────────────────────────────────┼───────────────────────────────────┘
                                   │                                                    │
                 ┌─────────────────┴─────────────────┐                ┌─────────────────┴─────────────────┐
                 ▼                                   ▼                ▼                                   ▼
┌─────────────────────────────────┐ ┌─────────────────────────────────┐ ┌─────────────────────────────────┐
│     安全执行沙箱 (Docker)       │ │     外部生态 (MCP Server)       │ │     PostgreSQL 核心持久化       │
│  - Go 编写的极简 Daemon         │ │  - GitHub / DB / Slack / Web   │ │  - tasks / task_steps         │
│  - gRPC 双向流式 (Stdout/Stderr)│ │  - 标准 JSON-RPC 动态挂载       │ │  - task_checkpoints (断点续传) │
│  - /workspace 安全路径限制      │ └─────────────────────────────────┘ │  - user_memories (长期偏好)     │
└─────────────────────────────────┘                                     └─────────────────────────────────┘
```

---

## 二、 核心模块设计方案

### 1. Agent 执行控制层（Planner + ReAct + BaseAgent）

#### 1.1 分层继承与模板方法模式（Template Method Pattern）
* **`BaseAgent`（原子驱动基类 / 模板核心）**：
  * **统管通用执行流**：实现全功能的 `run(instruction, ctx) -> AsyncGenerator[dict, None]`，统一负责装配上下文、驱动 LLM 调用、解析 Thinking/ToolCall、执行工具回填、计算动作指纹与拦截死循环。
  * **定义扩展钩子（Hooks）**：提供 `get_system_prompt(ctx)`、`get_tools_schema()` 等钩子方法供子类覆盖。
* **`ReActAgent`（单步微观攻坚者）**：
  * 继承 `BaseAgent`，仅需声明 `get_system_prompt()` 绑定 `system/react_worker.md` 模板与沙箱/本地工具集，实现极致精简与代码复用。
* **`PlannerAgent`（宏观规划者）**：
  * 继承 `BaseAgent`，仅需绑定 `system/planner.md` 模板与规划专用工具集（`create_plan`, `update_step`），无缝复用底层的 LLM 通信与安全循环能力。


#### 1.2 死循环防御与熔断体系（Multi-layered Loop Defense）
1. **硬限制熔断**：
   * ReAct 单子任务最大步数：`max_react_steps = 15`。
   * 全局重规划上限：`max_replan_count = 3`。
   * 任务全局超时阈值：`max_duration = 15min`。
2. **动作指纹哈希（Action Fingerprinting）**：
   * 记录最近 5 步的 `hash(tool_name + sorted_arguments)`。
   * 命中相同参数执行 $\ge 3$ 次，判定为同参死循环。
3. **渐进式纠偏（Progressive Nudge）**：
   * **Level 1**：注入高优先级系统提示：`【系统警报】检测到该命令已连续失败 3 次，请立即更换解决策略`。
   * **Level 2**：若无法纠正，自动将任务切入 `WAITING_HUMAN`（HITL）由用户接管或优雅报错终止。

---

### 2. 记忆系统设计（Memory Architecture）

整个系统划分为三层记忆，既保证 Context 永远不超限，又保证长任务具备断点续传能力：

| 记忆分层 | 作用域 | 存储载体 | 运作机制 |
| :--- | :--- | :--- | :--- |
| **Layer 1: Working Memory**<br>(实时工作记忆) | 当前任务当前步 | 内存 / Scratchpad | - **动态 Token 预算**（Prompt 各部分设固定比例配额）。<br>- **大输出指针化**：工具输出超限时自动存盘，Prompt 仅留文件指针。 |
| **Layer 2: Short-term Context**<br>(会话与任务断点) | 单次任务 / 会话 | PostgreSQL<br>(`task_checkpoints` + `task_steps`) | - 记录全量思考流水与工具调用记录。<br>- 滚动摘要压缩（`context_summary`），支持任务随时挂起、崩溃恢复、HITL 恢复。 |
| **Layer 3: Long-term Memory**<br>(长期用户与经验) | 跨任务 / 跨会话 | PostgreSQL<br>(`user_memories` / `pgvector`) | - **用户画像**：记录环境偏好（Python版本、TS严格模式等）。<br>- **经验库**：任务结束后的自省总结与向量检索。 |

---

### 3. 工具生态与通用抽象（Tool Architecture）

#### 3.1 统一工具接口规范
所有工具屏蔽底层差异，对外暴露标准描述：
* `Name` / `Description` / `ParametersSchema`（标准 JSON Schema）。
* `Execute(ctx, args, runtimeContext) -> ToolResult`。

#### 3.2 三大来源适配器（Adapters）
* **Sandbox Tool**：与沙箱容器通信，执行本地文件读写、Bash 命令、环境探测。
* **MCP Tool**：通过 JSON-RPC 自动对接外部 MCP Server（如 GitHub、Postgres、Notion），自动发现并转换工具。
* **A2A Tool（Agent-to-Agent）**：主 Agent 将子任务派发给专业 Subagent（如 `researcher`、`coder`），异步等待子任务结果并回填。

#### 3.3 装饰器/切面管道（Decorator Pipeline）
执行工具时依次通过以下切面：
1. **`LoggingDecorator`**：记录工具调用审计与消耗。
2. **`HITLDecorator`**：高危指令（如格式化、删库、外部强推）拦截并挂起任务等待人工审批。
3. **`TimeoutDecorator`**：防止单条命令（如卡住的编译命令）无限挂起。
4. **`TruncationDecorator`**：返回值超过 4KB 自动存盘，转换为“摘要 + 路径指针”。

---

### 4. 沙箱运行时设计（Sandbox Architecture）

```
[Worker Host Server]
        │
        │ gRPC / Streaming HTTP (双向长连接)
        ▼
[Docker / MicroVM 隔离容器]
  ├── [Go-written Sandbox Daemon] (单静态二进制，毫秒级启动，~10MB内存)
  │     ├── /exec     -> 支持流式实时返回 stdout/stderr，支持 PID 进程树强杀
  │     ├── /fs/read  -> 分页游标读取 (Offset + Limit)，内置 Grep/Tail
  │     ├── /fs/write -> 限制在 /workspace 目录，防止路径穿透
  │     └── /health   -> 探针检查
  └── [/workspace]    -> 挂载用户隔离数据卷 (持久化)
```

* **预热池技术（Pre-warmed Pool）**：常驻 3~5 个空闲容器，分配任务时秒级挂载，规避 Docker 冷启动开销。

---

### 5. 提示词与协议合规设计（Prompts & Structured Outputs）

#### 5.1 提示词独立管理
* 独立 `prompts/` 目录，按 `system/`、`tools/`、`nudges/`、`templates/` 分类管理 Markdown 模板。
* 采用 Jinja2 模板引擎实现动态上下文组装，支持热加载。

#### 5.2 严格结构化输出（100% Protocol Compliance）
* **弃用重型框架的脆弱正则解析**。
* 采用 **Pydantic V2 数据契约** + **LLM 原生 `response_format: { strict: true }` / `instructor` 方案**。
* 在 Token 采样阶段物理约束格式输出，确保 Planner 计划列表、HITL 表单等数据百分之百解析无误。

#### 5.3 默认大模型接入配置（硅基流动 SiliconFlow）
系统底层基于标准 OpenAI 兼容 SDK，默认配置接入**硅基流动（SiliconFlow）**平台：
* **Base URL**: `https://api.siliconflow.cn/v1`
* **Default Model**: `Qwen/Qwen3-8B` (原生支持 Function/Tool Calling 与流式输出，兼具高性价比与极速响应)
* **Environment Variable**: `SILICONFLOW_API_KEY` (或从会话配置 `sessions.agent_config` 中动态覆盖)
* **协议标准**: 统一使用 OpenAI 官方 Async Client（配置 `base_url` 与 `api_key`）。



---

## 三、 数据存储增量对齐方案（PostgreSQL）

无需重构现有表结构，仅做**增量追加**：

```sql
-- 1. 增量表：用户偏好与长期记忆表
CREATE TABLE user_memories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT NOT NULL, -- 'preference', 'environment', 'profile'
    key         TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, category, key)
);

-- 2. 增量字段：会话长期摘要（防止超长会话 Message 溢出）
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS context_summary TEXT;

-- 3. 现有表复用（无需修改）：
-- - tasks：任务状态机管理
-- - task_steps：流式步骤与工具调用审计
-- - task_checkpoints：断点续传、中间变量、最近上下文与阶段摘要
```

---

## 四、 方案总结

本方案在保持系统架构整洁（Clean Architecture）的前提下：
1. **摆脱重型黑盒框架**：以简洁原生的状态机与循环取代 LangChain，完全掌控执行流。
2. **兼顾宏观与微观**：Planner 把握方向，ReAct 落实执行，死循环多层拦截。
3. **安全与弹性兼备**：Go Daemon 驱动的轻量沙箱搭配流式传输与截断机制，保障极端长任务下的高可用与安全性。
