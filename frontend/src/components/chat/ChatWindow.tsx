"use client";

import React, { useRef, useEffect, useMemo } from "react";
import { MessageItem } from "./MessageItem";
import { ChatInput } from "./ChatInput";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuthStore } from "@/store/useAuthStore";
import { Bot, Sparkles, MessageSquare } from "lucide-react";
import { toast } from "@/store/useToastStore";

export const ChatWindow: React.FC = () => {
  const token = useAuthStore((state) => state.token);
  const messages = useSessionStore((state) => state.messages);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const isLoadingMessages = useSessionStore((state) => state.isLoadingMessages);
  const isSending = useSessionStore((state) => state.isSending);
  const sendMessage = useSessionStore((state) => state.sendMessage);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // 1. 检查当前会话最后一条消息是否包含未完结的活跃任务
  const activeTaskId = useMemo(() => {
    if (messages.length === 0) return null;
    const lastMsg = messages[messages.length - 1];
    if (
      lastMsg.role === "AGENT" &&
      lastMsg.status === "streaming" &&
      lastMsg.content?.task_status !== "COMPLETED" &&
      lastMsg.content?.task_status !== "FAILED" &&
      lastMsg.content?.task_status !== "CANCELLED"
    ) {
      return lastMsg.task_id || lastMsg.content?.task_id || null;
    }
    return null;
  }, [messages]);

  // 2. 智能节流吸底滚动
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  const handleSend = async (text: string) => {
    if (!token) return;
    try {
      await sendMessage(text, token);
    } catch (err: any) {
      if (err.status === 409) {
        toast.warning(err.message || "当前会话已有正在运行的任务，请等待完成后再发送", "并发请求已拦截");
      } else if (err.status === 429) {
        toast.error(err.message || "用户并发任务数已达上限，请稍候", "并发配额限制");
      } else {
        toast.error(err.message || "发送失败，请检查网络", "请求错误");
      }
    }
  };

  if (!currentSessionId) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-slate-950">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white mb-4 shadow-xl shadow-indigo-950/50">
          <Bot className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-slate-100 mb-2">欢迎使用 Antigravity Agent</h2>
        <p className="text-sm text-slate-400 max-w-md mb-6 leading-relaxed">
          全链路企业级 Agent 交互平台。支持多步思维链推理、工具调用、人机协同（HITL）与断点续传。
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
      {/* 消息滚动区域 */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-2 scrollbar-thin scrollbar-thumb-slate-800"
      >
        {isLoadingMessages ? (
          <div className="flex items-center justify-center h-full text-xs text-slate-500 animate-pulse">
            正在加载会话历史...
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-slate-500 py-12">
            <MessageSquare className="w-12 h-12 text-slate-700 mb-3" />
            <p className="text-sm font-medium text-slate-400">会话暂无消息</p>
            <p className="text-xs text-slate-600 mt-1">在下方输入指令，开启 Agent 任务探索</p>
          </div>
        ) : (
          messages.map((msg) => <MessageItem key={msg.id} message={msg} />)
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* 底部输入框 */}
      <ChatInput
        onSendMessage={handleSend}
        isSending={isSending}
        activeTaskId={activeTaskId}
      />
    </div>
  );
};
