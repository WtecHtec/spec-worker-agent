"use client";

import React, { useState, useRef, useEffect } from "react";
import { Send, Square, Sparkles, Loader2 } from "lucide-react";
import { useSessionStore } from "@/store/useSessionStore";
import { useTaskStore } from "@/store/useTaskStore";
import { useAuthStore } from "@/store/useAuthStore";
import { toast } from "@/store/useToastStore";
import { api } from "@/lib/api";

interface ChatInputProps {
  onSendMessage: (text: string) => Promise<void>;
  onCancel?: () => Promise<void>;
  isSending?: boolean;
  isStreaming?: boolean;
  /** @deprecated 保留旧字段兼容，P0 阶段 LangGraph 模式无需 activeTaskId */
  activeTaskId?: string | null;
}

export const ChatInput: React.FC<ChatInputProps> = ({
  onSendMessage,
  onCancel,
  isSending = false,
  isStreaming = false,
  activeTaskId = null,
}) => {
  const [content, setContent] = useState("");
  const [isCancelling, setIsCancelling] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const token = useAuthStore((state) => state.token);

  const updateMessageByTaskId = useSessionStore((state) => state.updateMessageByTaskId);
  const setTaskStatus = useTaskStore((state) => state.setTaskStatus);

  // 自动调整输入框高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [content]);

  const handleSend = async () => {
    const busy = isSending || isStreaming || !!activeTaskId;
    if (!content.trim() || busy) return;
    const text = content.trim();
    setContent("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    await onSendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 优先使用新的 onCancel 回调（LangGraph 模式），降级到旧 Task 取消逻辑
  const handleCancelTask = async () => {
    if (isCancelling) return;
    setIsCancelling(true);
    try {
      if (onCancel) {
        await onCancel();
      } else if (activeTaskId && token) {
        // 旧版 Task Worker 兼容路径
        await api.cancelTask(activeTaskId, token);
        updateMessageByTaskId(activeTaskId, {
          status: "failed",
          content: { text: "任务已被取消。", task_status: "CANCELLED" },
        });
        setTaskStatus(activeTaskId, "CANCELLED");
      }
      toast.info("已停止生成", "已取消");
    } catch (err: any) {
      toast.error(err.message || "终止失败，请重试", "取消失败");
    } finally {
      setIsCancelling(false);
    }
  };

  const isActive = isStreaming || !!activeTaskId;

  const QUICK_PROMPTS = [
    { title: "📄 创建文件", text: "请在沙箱中帮我创建一个 utils.py 文件，编写常用日期格式化与字符串处理函数并打印输出。" },
    { title: "🌐 生成一个 HTML 页面", text: "请帮我生成一个具有精美动态视觉效果的 HTML 页面，包含响应式布局和可交互功能。" },
  ];

  return (
    <div className="p-4 border-t border-slate-800/80 bg-slate-950/80 backdrop-blur-xl">
      {/* 快捷推荐提示词 */}
      <div className="flex flex-wrap items-center gap-2 mb-3 max-w-4xl mx-auto">
        <span className="text-[11px] text-slate-500 flex items-center gap-1 mr-1">
          <Sparkles className="w-3 h-3 text-indigo-400" />
          快捷演示：
        </span>
        {QUICK_PROMPTS.map((p, idx) => (
          <button
            key={idx}
            onClick={() => setContent(p.text)}
            disabled={isActive}
            className="text-xs px-2.5 py-1 rounded-full border border-slate-800 bg-slate-900/60 text-slate-300 hover:border-indigo-500/50 hover:bg-indigo-500/10 hover:text-indigo-200 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {p.title}
          </button>
        ))}
      </div>

      {/* 输入框核心区域 */}
      <div className="max-w-4xl mx-auto relative rounded-2xl border border-slate-700/80 bg-slate-900/90 shadow-2xl focus-within:border-indigo-500/80 focus-within:ring-2 focus-within:ring-indigo-500/20 transition-all">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isActive}
          placeholder={
            isActive
              ? "正在生成中，点击右侧按钮可停止..."
              : "输入您想问的问题... (Enter 发送，Shift+Enter 换行)"
          }
          rows={1}
          className="w-full resize-none bg-transparent px-4 py-3.5 pr-24 text-sm text-slate-100 placeholder-slate-500 focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
        />

        <div className="absolute right-2.5 bottom-2.5 flex items-center gap-1.5">
          {isActive ? (
            <button
              onClick={handleCancelTask}
              disabled={isCancelling}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-rose-600/25 border border-rose-500/40 text-rose-300 hover:bg-rose-600/40 hover:text-rose-100 transition-all active:scale-95 shadow-sm"
              title="终止当前任务"
            >
              {isCancelling ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Square className="w-3.5 h-3.5 fill-current" />
              )}
              <span>{isCancelling ? "终止中..." : "终止"}</span>
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!content.trim() || isActive}
              className="w-9 h-9 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed transition-all duration-200 shadow-md shadow-indigo-900/40 active:scale-95"
            >
              {isSending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
