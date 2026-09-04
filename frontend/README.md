# X Agent - 前端客户端 (Frontend)

基于 **Next.js 14 (App Router) + Tailwind CSS + Zustand + Framer Motion + React Markdown** 构建的高性能企业级 Agent 交互客户端。

---

## 一、技术架构与状态流转

```
                      ┌──────────────────────────────────────────────────────────┐
                      │                        UI 组件树                         │
                      │  - Sidebar: 会话管理、搜索过滤、用户卡片                 │
                      │  - ChatWindow: 历史消息流、智能节流吸底滚动              │
                      │  - MessageItem: User 气泡 / Agent 卡片                   │
                      │  - StepContainer: 步骤容器 (Thinking / Tools / Final)    │
                      │  - HitlStep: 人机协同决策交互卡片                        │
                      │  - ChatInput: 快捷提示词、自适应输入框、终止按钮         │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                 全局状态层 (Zustand Stores)              │
                      │  - useAuthStore: Token、登录态、401 自动失效监听         │
                      │  - useSessionStore: 会话列表、当前消息流、发送调度       │
                      │  - useTaskStore: 步骤缓存 Map、活跃 HITL、任务状态       │
                      │  - useToastStore: 浮动通知 (409 互斥 / 429 配额告警)     │
                      └────────────────────────────┬─────────────────────────────┘
                                                   │
                                                   ▼
                      ┌──────────────────────────────────────────────────────────┐
                      │                   核心 Custom Hooks                      │
                      │  - useTaskStream: SSE 连接管理、指数退避重连、增量续传   │
                      │  - useTypewriter: rAF 逐帧帧预算调度、自适应防积压打字机 │
                      └──────────────────────────────────────────────────────────┘
```

---

## 二、关键核心机制与性能优化

### 1. 基于 `requestAnimationFrame` (rAF) 的高性能打字机 (`useTypewriter`)
- **拒绝 React 重绘风暴**：摒弃传统 `setInterval` / 每个字符 `setState` 的低效方案，将文本吐字同步至显示器刷新率（60Hz/120Hz）。
- **自适应动态提速**：
  - 缓冲区文本较少时：每帧消费 1 个字符，保持优雅的打字动画；
  - 后端大段文本突发到达（积压 > 40~100 字符）时：动态提速至每帧消费 3~6 个字符，**既有打字视觉质感，又绝不导致界面严重滞后于后端实际进度**。
- **历史数据瞬时直出**：仅对当前正在推流的活跃步骤启用打字机动画；加载历史消息或刷新页面时直接瞬时输出。

### 2. 具有指数退避与增量续传的 SSE 客户端 (`useTaskStream`)
- **断线自动重试**：网络瞬断时触发 `1s → 2s → 4s → 8s → 15s` 指数退避重试（最多 6 次）。
- **无重复增量续传**：`latestStepRef` 动态记录已接收的最大 `step_index`，重连请求自动拼接 `from_step=${latestStep}`，服务端仅返回后续新增步骤，避免数据重复。
- **终态自锁**：收到 `task_completed`、`task_failed`、`task_cancelled` 事件后立即置为终止态，停止后续一切无意义的轮询重试。

### 3. 断点续传与会话热重连
- 用户刷新页面或切换会话时，`ChatWindow` 自动扫描最后一条消息；
- 若检测到 `status === 'streaming'` 的未完成任务，`StepContainer` 立即发起重连补发历史步骤，并自动通过 `GET /tasks/{id}/hitl/pending` 还原未完成的人工决策状态。

### 4. 人机协同卡片交互 (HITL)
- 支持 **单选选项（Choice）** 与 **自由文本输入（Text Input）** 两种决策形态；
- 用户提交决策后，界面立即更新为「已确认」锁定态，并展示 Toast 提示，服务端任务从断点自动恢复推流。

### 5. 生产级 Markdown 代码高亮与复制 (`CodeBlock`)
- 定制代码块组件，自动提取编程语言标签；
- 支持一键复制到剪贴板，带有「已复制」绿色勾选反馈动效；
- 对表格（Table）、引用（Blockquote）进行专属暗黑模式圆角排版美化。

---

## 三、目录结构

```
frontend/src/
├── types/                # TypeScript 领域实体与 API 响应接口定义
├── lib/
│   ├── api.ts            # 统一 API 客户端（Token 注入、401 自动失效处理、Retry-After 解析）
│   └── utils.ts          # clsx + tailwind-merge 类名与日期工具函数
├── store/
│   ├── useAuthStore.ts   # 认证与 Token 本地持久化
│   ├── useSessionStore.ts# 会话列表与消息流转
│   ├── useTaskStore.ts   # 步骤缓存 Map 与 HITL 状态
│   └── useToastStore.ts  # 全局轻量浮动通知 Store
├── hooks/
│   ├── useTaskStream.ts  # SSE 实时事件流与指数退避重连
│   └── useTypewriter.ts  # rAF 帧预算驱动的高性能打字机
├── components/
│   ├── auth/             # 登录/注册弹窗组件
│   ├── layout/           # 侧边栏（含会话搜索过滤）与顶部导航栏（含网络状态感知）
│   ├── chat/             # ChatWindow、MessageItem、ChatInput
│   ├── steps/            # ThinkingStep、ToolCallStep、ToolResultStep、HitlStep、FinalStep
│   └── ui/               # CodeBlock、ToastContainer
└── app/
    ├── layout.tsx        # 根布局与元数据配置
    ├── page.tsx          # 仪表盘主页面
    └── globals.css       # 暗黑模式、自定义精细滚动条与排版样式
```

---

## 四、本地运行指南

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器 (端口 3000)
npm run dev

# 生产环境打包构建校验
npm run build
```
