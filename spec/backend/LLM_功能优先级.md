# LLM Worker Agent 功能实施优先级规划

> **制定原则**：以 **“最小可用闭环（MVP） $\to$ 生产级沙箱与流式 $\to$ 宏观规划与分层记忆 $\to$ 多源生态与多 Agent 协同”** 为演进节奏，分步交付，步步闭环。

---

## 阶段演进路线总览

```
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 0: 最小可用真实 Agent 闭环 (Core LLM ReAct Loop)                 │
│ 目标: 跑通真实 LLM API、单进程基础工具、原生 ReAct 步进与防死循环熔断  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 1: 生产级安全沙箱与长耗时流式 (Production Sandbox & Streaming)   │
│ 目标: Go Daemon 沙箱容器化、gRPC 流式日志、超大输出截断、进程中断 Kill │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 2: Planner 双层编排与分层记忆体系 (Planner + Memory Hierarchy)   │
│ 目标: Planner 动态规划拆解、Pydantic 严格协议、三层记忆与 Checkpoint 融合│
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Phase 3: 多源生态与高级协同 (MCP / A2A & Production Hardening)         │
│ 目标: 动态 MCP 挂载、A2A 子任务派发、沙箱预热池与智能自省经验库        │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 一、 Phase 0｜最小可用真实 Agent 闭环（MVP 阶段）

> **核心目标**：从系统原有的 Mock 模式无缝切换为**真实大模型驱动**，跑通基于 `BaseAgent` 的单步 ReAct 循环与基础工具。

### 1. 统一 OpenAI 兼容 LLM Client 封装
```
- 默认接入硅基流动 (SiliconFlow): BaseURL="https://api.siliconflow.cn/v1", Model="Qwen/Qwen3-8B"
- 统一模型调用抽象 (BaseURL, APIKey, ModelName, Temperature)
- 支持 OpenAI、DeepSeek、Qwen、Ollama 等多厂商接入
- 基础重试、超时控制与 Token 用量自动统计
```

### 2. 独立 Prompt 目录与模板管理
```
- 创建 prompts/ 目录结构
- prompts/system/react_worker.md (ReAct 执行者核心系统指令)
- Jinja2 模板渲染机制 (支持注入当前时间、工作区路径、系统指令)
```

### 3. BaseAgent 核心与 ReAct 执行循环
```
- 实现 BaseAgent 原子抽象 (LLM 调用、消息上下文维护、Tool 分发)
- 实现 ReActAgent (Thought -> Action -> Observation 步进流转)
- 步骤持久化: 每步产生并写入 task_steps (THINKING, TOOL_CALL, TOOL_RESULT)
```

### 4. 统一 BaseTool 抽象与 3 个核心工具
```
- 定义标准 Tool 接口 (Name, Description, ParametersSchema, Execute)
- 本地执行工具: run_command (受限命令执行)、read_file、write_file
```

### 5. 基础死循环防御与熔断机制
```
- 步数硬熔断: max_react_steps = 15
- 动作指纹哈希: 拦截最近连续 3 次相同参数的重复工具调用
```

**Phase 0 交付标志**：
```
✅ 替换掉 Mock 模式，真实 LLM 能够接收用户任务并自主思考
✅ LLM 能够调用本地 read/write/bash 工具完成简单多步任务
✅ 步骤实时写入 PostgreSQL 并通过现有 SSE 推向前端展示
```

---

## 二、 Phase 1｜生产级安全沙箱与长耗时流式（安全与体验加固）

> **核心目标**：将工具执行从宿主机隔离到 **Go 编写的独立 Docker 沙箱**，实现长耗时命令流式推送与随时中断。

### 1. Go Sandbox Daemon 独立服务
```
- 单静态编译二进制 (~10MB 内存占用，毫秒级冷启动)
- 暴露标准接口: /exec (命令执行), /fs/read (文件读取), /fs/write (文件写入), /health (探针)
- 路径穿透安全校验 (强行限制在 /workspace 目录内)
- Docker 基础镜像构建 (预装 bash, git, python, curl, sandbox-daemon)
```

### 2. 长耗时流式双向通信（gRPC / WebSocket）
```
- Worker 与沙箱建立双向长连接
- 沙箱实时将 stdout/stderr 分块 (Chunk) 吐出
- 透传至 Redis Pub/Sub -> 前端 SSE 终端实现实时滚动输出
```

### 3. 超大输出截断与指针化（Truncation Decorator）
```
- 单次工具输出 > 4KB 自动截断并存盘至沙箱 /tmp/observations/
- 回填 LLM 的结果替换为: "Output Truncated: Stored to path, Summary: ..."
- 保留头部与尾部关键错误 Traceback
```

### 4. 异步控制与进程树强杀（Job Control & Kill）
```
- 为每个执行分配 ExecID
- 用户在前端点击取消或超时时，沙箱通过 syscall 强杀整个子进程树 (Kill -PID)
```

### 5. Tool 切面中间件流水线（AOP Pipeline）
```
- LoggingDecorator (记录执行耗时与参数)
- TimeoutDecorator (单命令执行超时熔断)
- HITLDecorator (高危操作拦截并转为 WAITING_HUMAN 状态)
```

**Phase 1 交付标志**：
```
✅ 任务在完全隔离的 Docker 容器中执行，宿主机零安全风险
✅ 支持长耗时命令（如 npm install、编译），前端终端可实时看到流式日志
✅ 用户可随时主动中断卡住的命令，大日志输出不再挤爆 LLM 上下文
```

---

## 三、 Phase 2｜Planner 宏观编排与分层记忆（长任务能力飞跃）

> **核心目标**：引入宏观规划能力与严格协议校验，解决长任务容易偏离目标、上下文溢出的问题。

### 1. PlannerAgent 宏观规划层
```
- prompts/system/planner.md (目标拆解与依赖规划指令)
- 生成并维护 PlanState (子任务有序列表及完成状态)
- 宏观调度 ReActAgent 分步攻坚单一子任务
```

### 2. 严格结构化输出（Strict Structured Outputs）
```
- 采用 Pydantic V2 / instructor / Native response_format: { strict: true }
- 确保 Planner 输出的 Plan 结构 100% 格式合法，零 JSON 语法解析错误
```

### 3. 动态重规划机制（Dynamic Re-planning）
```
- 当子任务执行失败或遇到非预期结果时，Planner 介入反思
- 动态调整后续 Plan (修改步骤、追加步骤、跳过步骤)
- 设定重规划上限: max_replan_count = 3
```

### 4. 工作记忆分层与滚动压缩（Working Memory Compaction）
```
- 动态 Token 预算管理 (System: 20%, Plan: 15%, Steps: 40%, Output: 25%)
- 步骤超长时自动触发异步轻量总结，生成 context_summary 存入 task_checkpoints
- 配合现有断点续传机制，实现任务随暂停/崩溃后的高保真恢复
```

### 5. 用户偏好与画像记忆（user_memories）
```
- 增量建表: user_memories (存储用户编程语言偏好、环境配置)
- 任务启动时自动装配偏好上下文注入 Prompt
```

**Phase 2 交付标志**：
```
✅ 面对复杂综合大任务，Agent 先列出清晰步骤计划再逐一执行
✅ 即使执行 30+ 步，上下文也不会溢出崩溃，且始终围绕宏观目标推进
✅ 结合 Checkpoint 能够完美实现 HITL 审批恢复与断网续传
```

---

## 四、 Phase 3｜生态扩展与高级协同（企业级增强）

> **核心目标**：对接行业标准 MCP 协议，支持多 Agent 分工协同与秒级容器启动。

### 1. MCP 协议适配器（Model Context Protocol）
```
- 实现 MCP Client 模块 (支持 stdio 与 SSE 传输)
- 动态连接外部 MCP Server (如 GitHub MCP, PostgreSQL MCP, Notion MCP)
- 自动发现 tools/list 并动态封装为系统内部标准 Tool
```

### 2. A2A 多 Agent 协同（Agent-to-Agent Delegation）
```
- A2ATool 适配器: 主 Agent 可通过工具调用向专业 Subagent 派发子任务
- 支持 ResearcherAgent (查资料)、CoderAgent (写代码)、ReviewerAgent (代码审查)
```

### 3. 沙箱预热池（Pre-warmed Container Pool）
```
- 维护 3~5 个空闲预热容器处于就绪状态
- 任务到达时秒级分配并绑定工作区卷，冷启动耗时从 3 秒降至 50ms
```

### 4. 经验沉淀与向量检索（Episodic Memory via pgvector）
```
- 任务完成后触发自我反思，沉淀成功经验与踩坑方案
- 借助 pgvector 进行相似历史任务的向量检索与知识注入
```

---

## 五、 优先级汇总对照表

| 阶段 | 交付核心 | 依赖关键组件 | 预期达成效果 |
| :--- | :--- | :--- | :--- |
| **Phase 0** | 真实 LLM ReAct 闭环 | BaseAgent, Prompts, OpenAI API | 替换 Mock，真实 LLM 自主跑通简单多步任务 |
| **Phase 1** | Go 独立沙箱 + 流式终端 | Go Daemon, Docker, gRPC, 截断切面 | 安全隔离，支持长耗时编译与实时日志流式推送 |
| **Phase 2** | Planner + 三层记忆 | Pydantic, 动态重规划, Checkpoint 摘要 | 复杂长任务不迷航，上下文永不超限，支持中断恢复 |
| **Phase 3** | MCP 外部生态 + A2A 协同 | MCP Client, 预热池, pgvector | 支持外部插件生态、多专家 Agent 协作与秒级调度 |
