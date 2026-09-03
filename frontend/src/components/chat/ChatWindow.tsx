"use client";

import React, { useRef, useEffect, useCallback, useState } from "react";
import { MessageItem } from "./MessageItem";
import { ChatInput } from "./ChatInput";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useLangGraphStream } from "@/hooks/useLangGraphStream";
import { Bot } from "lucide-react";
import { HitlFormCard } from "./HitlFormCard";

import { groupMessagesIntoTurns } from "@/lib/messageNormalizer";

export const ChatWindow: React.FC = () => {
  const token = useAuthStore((state) => state.token);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const createSession = useSessionStore((state) => state.createSession);
  const setCurrentRunId = useSessionStore((state) => state.setCurrentRunId);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [submittedRequestIds, setSubmittedRequestIds] = useState<Record<string, boolean>>({});

  // 全面拥抱 LangGraph 原生 useStream：以 Thread 消息流为全局单一可信源
  const {
    isLoading,
    submit,
    resume,
    actionRequests,
    cancel,
    messages,
  } = useLangGraphStream({
    threadId: currentSessionId,
    token,
    onRunCreated: useCallback((runId: string) => {
      setCurrentRunId(runId);
    }, [setCurrentRunId]),
    onFinish: useCallback(() => {
      setCurrentRunId(null);
    }, [setCurrentRunId]),
  });

  // 按任务轮次聚合后的消息列表：工具调用、工具返回与大模型回复一体化呈现
  const renderedTurns = React.useMemo(() => groupMessagesIntoTurns(messages), [messages]);

  // 自动吸底滚动（内容变动时 auto 滚动，杜绝 smooth 频繁计算掉帧）
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
  }, [renderedTurns]);

  // 会话切换时重置已提交审批记录
  useEffect(() => {
    setSubmittedRequestIds({});
  }, [currentSessionId]);

  // 发送消息处理
  const handleSend = useCallback(async (text: string) => {
    if (!token || !text.trim() || isLoading) return;

    // 若无当前会话，先自动创建会话 Thread
    let sessionId = currentSessionId;
    if (!sessionId) {
      const autoTitle = text.length > 24 ? `${text.slice(0, 24)}...` : text;
      const created = await createSession(token, autoTitle);
      sessionId = created.id;
    }

    // 由 LangGraph SDK 官方 submit() 驱动整个单向数据流与乐观更新
    submit(text);
  }, [token, isLoading, currentSessionId, createSession, submit]);

  // 监听并处理 HITL 快捷提交事件
  useEffect(() => {
    const onHitlSubmit = (e: any) => {
      const text = e.detail;
      if (text) {
        handleSend(text);
      }
    };
    window.addEventListener("submit_hitl_response", onHitlSubmit);
    return () => window.removeEventListener("submit_hitl_response", onHitlSubmit);
  }, [handleSend]);

  const handleCancel = useCallback(async () => {
    await cancel();
    setCurrentRunId(null);
  }, [cancel, setCurrentRunId]);

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-2 scrollbar-thin scrollbar-thumb-slate-800">
        {!currentSessionId || renderedTurns.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-lg mx-auto">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white mb-4 shadow-xl shadow-indigo-950/50">
              <Bot className="w-7 h-7" />
            </div>
            <h2 className="text-lg font-bold text-slate-100 mb-1.5">欢迎使用 Antigravity Agent</h2>
            <p className="text-xs text-slate-400 mb-6 leading-relaxed">
              全链路企业级 Agent 交互平台，完全由 LangGraph 官方流式架构驱动。
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
        ) : (
          /* 遍历渲染聚合后的任务轮次卡片：工具消息与 AI 消息融为一体，彻底消灭空白与脱节 */
          renderedTurns.map((turn: any, idx: number) => (
            <MessageItem key={turn.id || `turn-${idx}`} message={turn} />
          ))
        )}

        {/* 官方 LangGraph HITL interrupt 待审批交互卡片 */}
        {actionRequests && actionRequests.length > 0 && actionRequests
          .filter((req: any, idx: number) => !submittedRequestIds[req.id || String(idx)])
          .map((req: any, idx: number) => {
            const reqKey = req.id || String(idx);
            return (
              <div key={reqKey} className="flex justify-start my-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <HitlFormCard
                  title={req.title || "人机协同操作审批"}
                  description={req.description || ""}
                  riskLevel={req.risk_level || "high"}
                  formFields={req.form_fields || []}
                  onSubmit={(formData) => {
                    // 1. 标记当前请求已提交，立即从待审批列表中移除
                    setSubmittedRequestIds((prev: Record<string, boolean>) => ({ ...prev, [reqKey]: true }));
                    // 2. 调用 resume 恢复中断（将人类决策送回 tools_node 中的 interrupt() 调用点）
                    resume(formData);
                  }}
                />
              </div>
            );
          })}

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
