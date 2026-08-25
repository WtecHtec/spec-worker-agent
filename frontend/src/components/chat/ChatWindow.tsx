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

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
      {/* 消息滚动区域 */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-2 scrollbar-thin scrollbar-thumb-slate-800"
      >
        {!currentSessionId || messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-lg mx-auto">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white mb-4 shadow-xl shadow-indigo-950/50">
              <Bot className="w-7 h-7" />
            </div>
            <h2 className="text-lg font-bold text-slate-100 mb-1.5">欢迎使用 Antigravity Agent</h2>
            <p className="text-xs text-slate-400 mb-6 leading-relaxed">
              全链路企业级 Agent 交互平台。支持多步思维链推理、Docker 独立安全沙箱、工具调用与产物实时预览。
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full text-left">
              <button
                onClick={() => handleSend("请在沙箱中创建一个 demo.py 脚本并运行它，计算 2 的 16 次方")}
                className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 hover:bg-slate-800/50 transition-all text-xs text-slate-300"
              >
                <span className="font-semibold text-indigo-400 block mb-0.5">🐍 沙箱代码执行</span>
                创建 Python 脚本并在 Docker 中运行
              </button>
              <button
                onClick={() => handleSend("请帮我编写一个展示 Agent 执行状态的 HTML 仪表盘网页并保存")}
                className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 hover:bg-slate-800/50 transition-all text-xs text-slate-300"
              >
                <span className="font-semibold text-indigo-400 block mb-0.5">🌐 生成网页产物</span>
                编写 HTML 报表并通过 URL 实时预览
              </button>
            </div>
          </div>
        ) : isLoadingMessages ? (
          <div className="flex items-center justify-center h-full text-xs text-slate-500 animate-pulse">
            正在加载会话历史...
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
