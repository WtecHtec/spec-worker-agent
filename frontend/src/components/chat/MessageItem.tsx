"use client";

import React from "react";
import { User, Bot, Clock, AlertCircle } from "lucide-react";
import { Message } from "@/types";
import { StepContainer } from "../steps/StepContainer";
import { formatDate } from "@/lib/utils";

interface MessageItemProps {
  message: Message;
}

export const MessageItem: React.FC<MessageItemProps> = React.memo(({ message }) => {
  const isUser = message.role === "USER";
  const taskId = message.task_id || message.content?.task_id;
  const taskStatus = message.content?.task_status;
  const isStreaming =
    message.status === "streaming" &&
    taskStatus !== "COMPLETED" &&
    taskStatus !== "FAILED" &&
    taskStatus !== "CANCELLED";

  if (isUser) {
    return (
      <div className="flex justify-end my-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="flex gap-3 max-w-[80%] items-start">
          <div className="rounded-2xl rounded-tr-sm bg-gradient-to-r from-indigo-600 to-indigo-700 px-4 py-3 text-white text-sm shadow-md shadow-indigo-950/30">
            <p className="whitespace-pre-wrap leading-relaxed">{message.content.text}</p>
            <div className="mt-1 text-[10px] text-indigo-200/80 text-right">
              {formatDate(message.created_at)}
            </div>
          </div>
          <div className="w-8 h-8 rounded-full bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-300 shrink-0">
            <User className="w-4 h-4" />
          </div>
        </div>
      </div>
    );
  }

  // AGENT 消息
  return (
    <div className="flex justify-start my-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <div className="flex gap-3 max-w-[92%] sm:max-w-[85%] items-start w-full">
        <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shrink-0 shadow-md shadow-indigo-900/40">
          <Bot className="w-4 h-4" />
        </div>

        <div className="flex-1 rounded-2xl rounded-tl-sm border border-slate-800 bg-slate-900/80 backdrop-blur-xl p-4 text-slate-100 shadow-xl">
          {/* 状态徽标 */}
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800/80 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-200 text-xs">Antigravity Agent</span>
              {taskStatus === "RUNNING" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 animate-pulse">
                  <Clock className="w-2.5 h-2.5" />
                  执行中
                </span>
              )}
              {taskStatus === "WAITING_HUMAN" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  <AlertCircle className="w-2.5 h-2.5" />
                  等待人工决策
                </span>
              )}
              {taskStatus === "COMPLETED" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 font-medium">
                  执行完毕
                </span>
              )}
              {taskStatus === "CANCELLED" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-400 border border-slate-700">
                  已取消
                </span>
              )}
            </div>

            <span className="text-[10px] text-slate-500">{formatDate(message.created_at)}</span>
          </div>

          {/* 如果有任务 ID，渲染步骤容器 */}
          {taskId ? (
            <StepContainer taskId={taskId} isStreaming={isStreaming} />
          ) : (
            <div className="text-sm leading-relaxed whitespace-pre-wrap text-slate-200">
              {message.content.text}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

MessageItem.displayName = "MessageItem";
