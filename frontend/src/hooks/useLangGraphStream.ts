"use client";

/**
 * useLangGraphStream - 封装官方 @langchain/langgraph-sdk/react 的 useStream Hook
 *
 * 设计原则（遵循 langgraph.md 方案）：
 * - apiUrl 指向后端 FastAPI 网关，不暴露真实 LangGraph 地址
 * - 网关代理转发至 LangGraph Runtime，负责鉴权注入与业务落库
 * - cancel() 同时调用 stream.stop()（停止前端渲染）+ 网关真实 Cancel 接口
 */

import { useRef, useCallback } from "react";
import { useStream } from "@langchain/langgraph-sdk/react";
import type { ThreadState } from "@langchain/langgraph-sdk";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders["Authorization"] = `Bearer ${token}`;
  }

  const stream = useStream<AgentState>({
    apiUrl: API_BASE,
    assistantId: "agent",           // 与 langgraph.json graph key 对应
    threadId: threadId ?? undefined,
    defaultHeaders: authHeaders,

    onCreated: useCallback((run: { run_id: string }) => {
      activeRunIdRef.current = run.run_id;
      onRunCreated?.(run.run_id);
    }, [onRunCreated]),

    // 每次 state chunk 更新时触发（对齐 LangGraph event: updates 协议：data 为 {"llm_node": {"messages": [...]}}）
    onUpdateEvent: useCallback((data: any) => {
      let extracted: any[] = [];
      if (Array.isArray(data?.messages)) {
        extracted = data.messages;
      } else if (data && typeof data === "object") {
        for (const key of Object.keys(data)) {
          const val = data[key];
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
    }, [onFinish]),

    onError: useCallback((err: unknown) => {
      const error = err instanceof Error ? err : new Error(String(err));
      onError?.(error);
      activeRunIdRef.current = null;
    }, [onError]),
  });

  /**
   * 发送用户消息（触发新一轮 LLM 推理）
   * 使用 unknown 中间转换绕过 SDK 内部 Message 类型约束（自定义格式）
   */
  const submit = useCallback(
    (text: string) => {
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

    const runId = activeRunIdRef.current;
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
  }, [stream, threadId, token]);

  return {
    /** 当前 LLM 推理是否正在进行 */
    isLoading: stream.isLoading,
    /** 当前流式消息列表（由 SDK 内部自动合并维护） */
    messages: stream.messages,
    /** 发送用户消息 */
    submit,
    /** 停止生成（前端 + 服务端双重终止） */
    cancel,
    /** 当前 run_id */
    currentRunId: activeRunIdRef.current,
    /** 原始 stream 对象（供高级用途） */
    rawStream: stream,
  };
}
