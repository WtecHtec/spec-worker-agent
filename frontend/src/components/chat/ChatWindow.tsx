"use client";

import React, { useRef, useEffect, useCallback } from "react";
import { MessageItem } from "./MessageItem";
import { ChatInput } from "./ChatInput";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useLangGraphStream } from "@/hooks/useLangGraphStream";
import { Bot } from "lucide-react";
import { toast } from "@/store/useToastStore";
import { Message } from "@/types";


// 生成本地临时 ID（用于乐观渲染占位）
const tempId = () => `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;

/** 从 LangGraph message（any）中提取纯文本 */
function extractText(msg: any): string {
  if (!msg) return "";
  if (typeof msg.content === "string") return msg.content;
  if (Array.isArray(msg.content)) {
    return msg.content
      .map((c: any) => (typeof c === "string" ? c : c?.text ?? ""))
      .join("");
  }
  return "";
}

/** 判断是否为 AI 回复消息（兼容 ai / assistant / AIMessage / AIMessageChunk） */
function isAiMessage(msg: any): boolean {
  if (!msg) return false;
  const t = String(msg.type || msg.role || "").toLowerCase();
  return t === "ai" || t === "assistant" || t === "aimessage" || t === "aimessagechunk";
}

export const ChatWindow: React.FC = () => {
  const token = useAuthStore((state) => state.token);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const storeMessages = useSessionStore((state) => state.messages);
  const isLoadingMessages = useSessionStore((state) => state.isLoadingMessages);
  const createSession = useSessionStore((state) => state.createSession);
  const appendMessage = useSessionStore((state) => state.appendMessage);
  const updateMessage = useSessionStore((state) => state.updateMessage);
  const fetchMessages = useSessionStore((state) => state.fetchMessages);
  const setCurrentRunId = useSessionStore((state) => state.setCurrentRunId);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamingMsgIdRef = useRef<string | null>(null);

  // 自动吸底滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [storeMessages]);

  const { isLoading, submit, cancel, messages: streamMessages } = useLangGraphStream({
    threadId: currentSessionId,
    token,

    onRunCreated: useCallback((runId: string) => {
      setCurrentRunId(runId);
    }, [setCurrentRunId]),

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

    // 流结束：将占位消息标记为 done，后台同步数据库
    onFinish: useCallback((lgMessages: any[]) => {
      const msgId = streamingMsgIdRef.current;
      if (msgId) {
        const aiMsg = Array.isArray(lgMessages)
          ? [...lgMessages].reverse().find(isAiMessage)
          : null;
        const finalText = aiMsg ? extractText(aiMsg) : "";
        if (finalText) {
          updateMessage(msgId, { content: { text: finalText }, status: "done" });
        } else {
          updateMessage(msgId, { status: "done" });
        }
        streamingMsgIdRef.current = null;
        setCurrentRunId(null);
      }
      const sid = useSessionStore.getState().currentSessionId;
      if (sid && token) fetchMessages(sid, token, true);
    }, [updateMessage, fetchMessages, setCurrentRunId, token]),

    onError: useCallback((err: Error) => {
      const msgId = streamingMsgIdRef.current;
      if (msgId) {
        updateMessage(msgId, { content: { text: "⚠️ 请求出错，请重试。" }, status: "failed" });
        streamingMsgIdRef.current = null;
      }
      toast.error(err.message || "LLM 请求失败", "错误");
    }, [updateMessage]),
  });

  // 监听 SDK 原生响应式 messages 状态（双重保障）
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

  const handleSend = async (text: string) => {
    if (!token || isLoading) return;

    // 1. 无会话时自动创建
    let sessionId = currentSessionId;
    if (!sessionId) {
      const autoTitle = text.length > 24 ? `${text.slice(0, 24)}...` : text;
      const created = await createSession(token, autoTitle);
      sessionId = created.id;
    }

    // 2. 乐观追加用户消息
    appendMessage({
      id: tempId(),
      role: "USER",
      content_type: "text",
      content: { text },
      task_id: null,
      status: "done",
      seq: Date.now(),
      created_at: new Date().toISOString(),
    });

    // 3. 追加 Agent 流式占位
    const agentMsgId = tempId();
    streamingMsgIdRef.current = agentMsgId;
    appendMessage({
      id: agentMsgId,
      role: "AGENT",
      content_type: "text",
      content: { text: "" },
      task_id: null,
      status: "streaming",
      seq: Date.now() + 1,
      created_at: new Date().toISOString(),
    });

    // 4. 触发 LangGraph 官方 useStream 推理
    submit(text);
  };

  const handleCancel = useCallback(async () => {
    await cancel();
    const msgId = streamingMsgIdRef.current;
    if (msgId) {
      updateMessage(msgId, { status: "failed" });
      streamingMsgIdRef.current = null;
    }
    setCurrentRunId(null);
  }, [cancel, updateMessage, setCurrentRunId]);

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-2 scrollbar-thin scrollbar-thumb-slate-800">
        {!currentSessionId || storeMessages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-lg mx-auto">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white mb-4 shadow-xl shadow-indigo-950/50">
              <Bot className="w-7 h-7" />
            </div>
            <h2 className="text-lg font-bold text-slate-100 mb-1.5">欢迎使用 Antigravity Agent</h2>
            <p className="text-xs text-slate-400 mb-6 leading-relaxed">
              全链路企业级 Agent 交互平台，P0 阶段支持基础 LLM 对话与流式实时回复。
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full text-left">
              <button
                onClick={() => handleSend("什么是事件驱动架构？请简要介绍一下。")}
                className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 hover:bg-slate-800/50 transition-all text-xs text-slate-300"
              >
                <span className="font-semibold text-indigo-400 block mb-0.5">🧠 LLM 问答</span>
                问一个技术概念问题
              </button>
              <button
                onClick={() => handleSend("请用中文写一段 50 字以内的自我介绍。")}
                className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 hover:bg-slate-800/50 transition-all text-xs text-slate-300"
              >
                <span className="font-semibold text-indigo-400 block mb-0.5">✍️ 生成文本</span>
                让 LLM 生成一段介绍
              </button>
            </div>
          </div>
        ) : isLoadingMessages ? (
          <div className="flex items-center justify-center h-full text-xs text-slate-500 animate-pulse">
            正在加载会话历史...
          </div>
        ) : (
          storeMessages.map((msg) => <MessageItem key={msg.id} message={msg} />)
        )}
        <div ref={messagesEndRef} />
      </div>

      <ChatInput
        onSendMessage={handleSend}
        onCancel={handleCancel}
        isSending={isLoading}
        isStreaming={isLoading}
      />
    </div>
  );
};
