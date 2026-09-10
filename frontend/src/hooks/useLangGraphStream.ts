"use client";

/**
 * useLangGraphStream - 封装官方 @langchain/langgraph-sdk/react 的 useStream Hook
 *
 * 设计原则（遵循 langgraph.md 方案）：
 * - apiUrl 指向后端 FastAPI 网关，不暴露真实 LangGraph 地址
 * - 网关代理转发至 LangGraph Runtime，负责鉴权注入与业务落库
 * - cancel() 同时调用 stream.stop()（停止前端渲染）+ 网关真实 Cancel 接口
 */

import { useMemo, useRef, useCallback, useState, useEffect } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import { Client, type ThreadState } from "@langchain/langgraph-sdk";
import { API_BASE } from "@/lib/api";

// LangGraph 消息格式（SDK 内部格式）
type LGMessage = {
  type: string;   // "human" | "ai" | "tool" | "system"
  content: string | Array<{ type: string; text?: string; [key: string]: unknown }>;
  id?: string;
  [key: string]: unknown;
};

type AgentState = {
  messages: LGMessage[];
  [key: string]: unknown;
};

interface UseLangGraphStreamOptions {
  threadId: string | null;
  token?: string | null;
  /** 每次 state 更新时，返回当前累积的 messages */
  onMessage?: (messages: LGMessage[]) => void;
  /** 流式完全结束时回调 */
  onFinish?: (messages: LGMessage[]) => void;
  /** 获得服务端 run_id */
  onRunCreated?: (runId: string) => void;
  onError?: (error: Error) => void;
}

export function useLangGraphStream({
  threadId,
  token,
  onMessage,
  onFinish,
  onRunCreated,
  onError,
}: UseLangGraphStreamOptions) {
  const activeRunIdRef = useRef<string | null>(null);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [isThreadBusy, setIsThreadBusy] = useState<boolean>(false);
  const joiningRunIdRef = useRef<string | null>(null);

  const authHeaders: Record<string, string> = useMemo(() => {
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    return headers;
  }, [token]);

  // 官方 LangGraph SDK 客户端实例：直连后端网关代理与底层 Checkpointer 数据库
  const client = useMemo(() => {
    return new Client({
      apiUrl: API_BASE,
      defaultHeaders: authHeaders,
    });
  }, [authHeaders]);

  // 获取数据库真实持久化的 Thread Checkpoint 历史快照
  const getHistory = useCallback(
    async (options?: Parameters<Client["threads"]["getHistory"]>[1]) => {
      if (!threadId) return [];
      try {
        return await client.threads.getHistory(threadId, options);
      } catch (err) {
        console.error("[useLangGraphStream] client.threads.getHistory failed:", err);
        return [];
      }
    },
    [client, threadId]
  );

  // 获取数据库当前 Thread 的最新完整状态快照
  const getState = useCallback(async () => {
    if (!threadId) return null;
    try {
      return await client.threads.getState(threadId);
    } catch (err) {
      console.error("[useLangGraphStream] client.threads.getState failed:", err);
      return null;
    }
  }, [client, threadId]);

  const stream = useStream<AgentState>({
    apiUrl: API_BASE,
    assistantId: "agent",           // 与 langgraph.json graph key 对应
    threadId: threadId ?? undefined,
    defaultHeaders: authHeaders,
    reconnectOnMount: true,         // 开启官方 SDK 页面刷新/重连断点续传
    fetchStateHistory: { limit: 15 }, // 载入历史记录，确保恢复连接时初始状态完备

    onCreated: useCallback((run: { run_id: string }) => {
      activeRunIdRef.current = run.run_id;
      setIsThreadBusy(true);
      onRunCreated?.(run.run_id);
    }, [onRunCreated]),

    // 监听 LangGraph 派发的自定义生命周期事件（仅当历史对话超阈值触发压缩时生效）
    onCustomEvent: useCallback((event: any) => {
      const eventName = event?.name || event?.type || (typeof event === "string" ? event : "");
      if (eventName === "memory_compression_started") {
        setActiveNode("context_compressor");
      } else if (eventName === "memory_compression_finished") {
        setActiveNode(null);
      }
    }, []),

    // 每次 state chunk 更新时触发（对齐 LangGraph event: updates 协议：data 为 {"node_name": {...}}）
    onUpdateEvent: useCallback((data: any) => {
      let extracted: any[] = [];
      if (Array.isArray(data?.messages)) {
        extracted = data.messages;
      } else if (data && typeof data === "object") {
        for (const key of Object.keys(data)) {
          const val = data[key];
          // 捕获活跃节点名称（如 agent_node, tools_node）
          if (key && key !== "messages") {
            if (key === "context_compressor") {
              // 关键防护：只有当 context_compressor 真正产出了 summary 或游标，才显示记忆提炼；短路跳过返回 {} 时坚决不设
              if (val && typeof val === "object" && (val.summary || val.active_cut_index)) {
                setActiveNode("context_compressor");
              }
            } else {
              setActiveNode(key);
            }
          }
          if (val && typeof val === "object" && Array.isArray(val.messages)) {
            extracted.push(...val.messages);
          }
        }
      }
      if (extracted.length > 0) {
        onMessage?.(extracted);
      }
    }, [onMessage]),

    onFinish: useCallback((state: ThreadState<AgentState>) => {
      let extracted: any[] = [];
      const values = state?.values;
      if (Array.isArray(values?.messages)) {
        extracted = values.messages;
      } else if (values && typeof values === "object") {
        for (const key of Object.keys(values)) {
          const val = (values as any)[key];
          if (val && typeof val === "object" && Array.isArray(val.messages)) {
            extracted.push(...val.messages);
          }
        }
      }
      onFinish?.(extracted);
      activeRunIdRef.current = null;
      joiningRunIdRef.current = null;
      setIsThreadBusy(false);
      setActiveNode(null);
    }, [onFinish]),

    onError: useCallback((err: unknown) => {
      const error = err instanceof Error ? err : new Error(String(err));
      // 防御性清理当前失效/已不存在的 run 标记，避免页面持续抛错重试
      if (typeof window !== "undefined" && threadId) {
        try {
          window.sessionStorage.removeItem(`lg:stream:${threadId}`);
        } catch {
          // ignore
        }
      }
      onError?.(error);
      activeRunIdRef.current = null;
      joiningRunIdRef.current = null;
      setIsThreadBusy(false);
      setActiveNode(null);
    }, [onError, threadId]),
  });

  const streamRef = useRef(stream);
  streamRef.current = stream;
  const lastCheckedThreadIdRef = useRef<string | null>(null);

  // 主动探查服务端权威线程运行状态（仅在会话挂载或切换时执行一次，防并发保护与接力续流）
  useEffect(() => {
    if (!threadId || !token) {
      setIsThreadBusy(false);
      lastCheckedThreadIdRef.current = null;
      return;
    }

    // 同一会话若已探查过，不再重复请求
    if (lastCheckedThreadIdRef.current === threadId) {
      return;
    }

    const currentThreadId = threadId;
    let isMounted = true;

    async function checkThreadAndRuns() {
      // 若当前本地流式 Hook 已经在推流运行中，无需额外请求 runs.list
      if (streamRef.current.isLoading) {
        lastCheckedThreadIdRef.current = currentThreadId;
        return;
      }

      try {
        const runs = await client.runs.list(currentThreadId, { limit: 5 });
        if (!isMounted) return;

        lastCheckedThreadIdRef.current = currentThreadId;

        const activeRun = runs.find((r) => r.status === "running" || r.status === "pending");
        if (activeRun) {
          activeRunIdRef.current = activeRun.run_id;
          setIsThreadBusy(true);

          // 若当前流式 Hook 未在推流状态且尚未针对该 run_id 发起过续流，主动接力续流！
          if (!streamRef.current.isLoading && joiningRunIdRef.current !== activeRun.run_id) {
            joiningRunIdRef.current = activeRun.run_id;
            try {
              await streamRef.current.joinStream(activeRun.run_id);
            } catch (joinErr) {
              console.warn("[useLangGraphStream] joinStream failed:", joinErr);
            }
          }
        } else {
          setIsThreadBusy(false);
          joiningRunIdRef.current = null;
        }
      } catch (err) {
        console.warn("[useLangGraphStream] checkThreadAndRuns error:", err);
      }
    }

    void checkThreadAndRuns();

    return () => {
      isMounted = false;
    };
  }, [client, threadId, token]);

  /**
   * 发送用户消息（触发新一轮 LLM 推理）
   * 使用 unknown 中间转换绕过 SDK 内部 Message 类型约束（自定义格式）
   */
  const submit = useCallback(
    (text: string) => {
      setActiveNode(null);
      setIsThreadBusy(true);
      const payload = {
        messages: [{ type: "human", content: text }],
      } as unknown as Partial<AgentState>;
      stream.submit(payload);
    },
    [stream]
  );

  /**
   * 停止生成：
   * 1. stop() 终止前端 SSE 连接渲染
   * 2. 调用网关 Cancel 接口，中断 LangGraph 后台 Worker
   */
  const cancel = useCallback(async () => {
    stream.stop();
    setIsThreadBusy(false);
    joiningRunIdRef.current = null;

    let runId = activeRunIdRef.current;
    if (!runId && typeof window !== "undefined" && threadId) {
      runId = window.sessionStorage.getItem(`lg:stream:${threadId}`);
    }

    // 若本地尚无 runId，尝试直接向服务端查询最新活跃 Run
    if (!runId && threadId) {
      const currentThreadId = threadId;
      try {
        const runs = await client.runs.list(currentThreadId, { limit: 1 });
        const runningRun = runs.find((r) => r.status === "running" || r.status === "pending");
        if (runningRun) {
          runId = runningRun.run_id;
        }
      } catch {
        // ignore
      }
    }

    if (threadId && runId) {
      try {
        const headers: Record<string, string> = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = `Bearer ${token}`;
        await fetch(`${API_BASE}/threads/${threadId}/runs/${runId}/cancel`, {
          method: "POST",
          headers,
        });
      } catch (err) {
        console.error("[useLangGraphStream] Cancel upstream run failed:", err);
      }
    }
    activeRunIdRef.current = null;
    setActiveNode(null);
  }, [client, stream, threadId, token]);

  /**
   * 响应并恢复 HITL 中断（传递人类审批/表单填写决策）
   */
  const resume = useCallback(
    (decision: any) => {
      // 触发 SDK 官方 command.resume
      (stream as any).submit(null, {
        command: {
          resume: decision,
        },
      });
    },
    [stream]
  );

  // 提取官方 LangGraph HITL interrupt 数据与操作请求
  const interruptData: any = (stream.interrupt as any)?.value || stream.interrupt;
  const actionRequests: any[] = Array.isArray(interruptData?.action_requests)
    ? interruptData.action_requests
    : [];

  const isBusy = stream.isLoading || isThreadBusy;

  return {
    /** 当前 LLM 推理是否正在进行（结合 SDK 流式态与服务端权威运行态） */
    isLoading: isBusy,
    isBusy,
    isThreadBusy,
    /** 当前活跃执行的 LangGraph 节点名称（如 context_compressor, agent_node, tools_node） */
    activeNode,
    /** 当前流式消息列表（由 SDK 内部自动合并维护） */
    messages: stream.messages,
    /** 发送用户消息 */
    submit,
    /** 恢复 HITL 中断 */
    resume,
    /** 当前中断信息 */
    interrupt: stream.interrupt,
    /** 解析出的待审批请求列表 */
    actionRequests,
    /** 停止生成（前端 + 服务端双重终止） */
    cancel,
    /** 官方 Client 实例 */
    client,
    /** 从数据库拉取历史 Checkpoint 状态列表 */
    getHistory,
    /** 获取当前 Thread 最新状态快照 */
    getState,
    /** 当前 run_id */
    currentRunId: activeRunIdRef.current,
    /** 原始 stream 对象（供高级用途） */
    rawStream: stream,
  };
}

