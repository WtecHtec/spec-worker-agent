# 03. LangGraph 流式消息协议与前端对齐规范

## 1. 协议演进概览

前端交互架构从原有的 **“任务创建 + EventSource 轮询式监听”** 正式演化升级为基于 **`@langchain/langgraph-sdk/react` 的标准 `useStream` 响应式流**。

### 1.1 架构对比一览

```
【旧版协议链路】
User Input ──> POST /tasks (获取 task_id)
                   │
                   └──> new EventSource(/tasks/{id}/stream) ──> new_step / hitl_created / task_completed

【改造后 LangGraph 协议链路】
User Input ──> useStream.submit(text)
                   │
                   └──> POST /threads/{thread_id}/runs/stream (SSE 单连接长直出)
                            ├── metadata (首帧获知 run_id)
                            ├── updates (Node 级增量产出: {"llm_node": {"messages": [...]}})
                            ├── values (线程全量快照)
                            └── onFinish (结束信号，双端状态对齐)
```

---

## 2. 端点与通信模型完整映射表

| 维度 | 旧版协议（Task 架构） | 改造后协议（LangGraph 架构） | 前端整合方案 |
|---|---|---|---|
| **请求入口** | `POST /tasks` | `POST /threads/{thread_id}/runs/stream` | 舍弃先行建任务步骤，统一通过 `useStream.submit` 一次性建连 |
| **流式连接** | `GET /tasks/{task_id}/stream?from_step=0` | `POST /threads/{thread_id}/runs/stream` (SSE) | 使用 Fetch ReadableStream，自动携带 Bearer 鉴权头 |
| **会话模型** | `session_id` | `thread_id`（UUID 规范） | `currentSessionId` 直接作为 `thread_id`，保持 1:1 对齐 |
| **运行标识** | `task_id` | `run_id` | 从 `metadata` 事件中提取存入 `useSessionStore.currentRunId` |
| **任务中断** | `POST /tasks/{task_id}/cancel` | `POST /threads/{thread_id}/runs/{run_id}/cancel` | 点击终止时调用 `cancel()`：停止前端流读取 + 服务端中断物理 Run |
| **状态回溯** | 调数据库 `GET /tasks/{id}/steps` | `GET /threads/{thread_id}/state` | SDK 自动拉取线程 Checkpoint 状态并填充到本地状态 |

---

## 3. SSE 消息事件与数据载荷（Payload）映射表

| 业务含义 | 旧版事件 (`event`) | 旧版载荷 (`data`) | 新版 LangGraph 事件 (`event`) | 新版 LangGraph 载荷 (`data`) | 前端消费与处理逻辑 |
|---|---|---|---|---|---|
| **首帧元数据** | `es.onopen` | 无 | `metadata` | `{"run_id": "01a065...", "attempt": 1}` | 触发 `onCreated(run)` 回调，记录 `run_id` 备用 |
| **增量状态更新 (Node 产出)** | `new_step` (`FINAL` / `THINKING`) | `{"step_type": "FINAL", "content": {"text": "..."}}` | `updates` | `{"llm_node": {"messages": [{"type": "ai", "content": "你好！", "id": "..."}]}}` | 从 `data[node_name].messages` 递归抽取 AI 消息文本，更新流式占位气泡 |
| **全量状态镜像** | 无（前端本地自累加） | 无 | `values` | `{"messages": [{"type": "human", "content": "..."}, {"type": "ai", "content": "..."}]}` | 全量快照覆盖校准，用于页面刷新或重连时的状态恢复 |
| **Token 级流式** | 依赖高频 `new_step` | 节流文本 | `messages/partial` | `[{"type": "AIMessageChunk", "content": "新词"}]` | 追加打字机字词 |
| **人工审核 (HITL)** | `hitl_created` | `{"hitl_id": "...", "question": "确认执行?", "options": [...]}` | `updates` (触发 `__interrupt__`) | `{"__interrupt__": [{"value": {"question": "..."}, "resumable": true}]}` | 捕获中断信号，将消息状态设为 `WAITING_HUMAN`，渲染 `HitlStep` 审核卡片 |
| **任务结束** | `task_completed` | `{"result": {"summary": "完成"}}` | `onFinish` (流关闭 EOF) | 流正常断开信号 | 占位气泡标记为 `done`，静默触发 `fetchMessages` 与后台同步 |
| **任务异常** | `task_failed` | `{"error": "报错信息"}` | `error` | `{"error": "TypeError", "message": "报错信息"}` | 气泡标记为 `failed`，弹出系统全局 Toast 警报 |
| **任务中断** | `task_cancelled` | `{"status": "CANCELLED"}` | HTTP 200 取消响应 + 流断开 | `{"status": "cancelled", "run_id": "..."}` | 保留已输出文本，气泡标为已取消，停止动画 |

---

## 4. 前端数据模型转换（SDK Message -> Session Store Message）

前端组件统一消费项目核心实体 `Message`，转换规则如下：

```typescript
// 判断是否为 AI 回复类型（兼容大小写与多种库版本）
export function isAiMessage(msg: any): boolean {
  if (!msg) return false;
  const t = String(msg.type || msg.role || "").toLowerCase();
  return t === "ai" || t === "assistant" || t === "aimessage" || t === "aimessagechunk";
}

// 提取文本（兼容直接字符串或复合 content 数组）
export function extractText(msg: any): string {
  if (!msg) return "";
  if (typeof msg.content === "string") return msg.content;
  if (Array.isArray(msg.content)) {
    return msg.content
      .map((c: any) => (typeof c === "string" ? c : c?.text ?? ""))
      .join("");
  }
  return "";
}
```

---

## 5. 组件层更新与双通道监听保障机制

在 `ChatWindow.tsx` 中实施**双通道监听策略**，彻底避免由于不同 stream_mode 配置导致丢失消息气泡更新：

```typescript
const { isLoading, submit, cancel, messages: streamMessages } = useLangGraphStream({
  threadId: currentSessionId,
  token,

  // 通道 1：由 onUpdateEvent 提取的实时节点更新
  onMessage: useCallback((lgMessages: any[]) => {
    const msgId = streamingMsgIdRef.current;
    if (!msgId || !Array.isArray(lgMessages) || lgMessages.length === 0) return;
    const aiMsg = [...lgMessages].reverse().find(isAiMessage);
    if (!aiMsg) return;
    const text = extractText(aiMsg);
    if (text) {
      updateMessage(msgId, { content: { text }, status: "streaming" });
    }
  }, [updateMessage]),

  // 流结束触发
  onFinish: useCallback((lgMessages: any[]) => {
    const msgId = streamingMsgIdRef.current;
    if (msgId) {
      const aiMsg = Array.isArray(lgMessages) ? [...lgMessages].reverse().find(isAiMessage) : null;
      const finalText = aiMsg ? extractText(aiMsg) : "";
      updateMessage(msgId, { content: { text: finalText }, status: "done" });
      streamingMsgIdRef.current = null;
      setCurrentRunId(null);
    }
    if (currentSessionId && token) fetchMessages(currentSessionId, token, true);
  }, [updateMessage, fetchMessages, setCurrentRunId, token, currentSessionId]),
});

// 通道 2：监听 SDK 原生响应式 streamMessages 状态变化（确保兜底捕获）
useEffect(() => {
  const msgId = streamingMsgIdRef.current;
  if (!msgId || !Array.isArray(streamMessages) || streamMessages.length === 0) return;
  const aiMsg = [...streamMessages].reverse().find(isAiMessage);
  if (aiMsg) {
    const text = extractText(aiMsg);
    if (text) {
      updateMessage(msgId, { content: { text }, status: "streaming" });
    }
  }
}, [streamMessages, updateMessage]);
```
