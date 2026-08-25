"use client";

import React, { useState } from "react";
import {
  User,
  Bot,
  Clock,
  AlertCircle,
  CheckCircle2,
  XCircle,
  Layers,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { Message } from "@/types";
import { StepContainer } from "../steps/StepContainer";
import { CodeBlock } from "@/components/ui/CodeBlock";
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

  // 历史已完成任务默认折叠步骤，按需懒加载
  const [isDetailsExpanded, setIsDetailsExpanded] = useState(false);

  if (isUser) {
    return (
      <div className="flex justify-end my-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="flex gap-3 max-w-[80%] items-start">
          <div className="rounded-2xl rounded-tr-sm bg-gradient-to-r from-indigo-600 to-indigo-700 px-4 py-3 text-white text-sm shadow-md shadow-indigo-950/30">
            <p className="whitespace-pre-wrap leading-relaxed">{message.content.text}</p>
            <div className="mt-1 text-[10px] text-indigo-200/80 text-right font-mono">
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
          {/* 状态顶栏 */}
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800/80 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-200 text-xs">Antigravity Agent</span>
              {taskStatus === "RUNNING" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 animate-pulse font-mono">
                  <Clock className="w-2.5 h-2.5" />
                  执行中
                </span>
              )}
              {taskStatus === "WAITING_HUMAN" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-rose-500/20 text-rose-300 border border-rose-500/30 font-mono">
                  <AlertCircle className="w-2.5 h-2.5" />
                  等待人工决策
                </span>
              )}
              {taskStatus === "COMPLETED" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 font-mono">
                  <CheckCircle2 className="w-2.5 h-2.5" />
                  执行完毕
                </span>
              )}
              {taskStatus === "FAILED" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-rose-500/15 text-rose-400 border border-rose-500/20 font-mono">
                  <XCircle className="w-2.5 h-2.5" />
                  执行失败
                </span>
              )}
              {taskStatus === "CANCELLED" && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] bg-slate-800 text-slate-400 border border-slate-700 font-mono">
                  已取消
                </span>
              )}
            </div>

            <span className="text-[10px] text-slate-500 font-mono">{formatDate(message.created_at)}</span>
          </div>

          {/* 渲染内容：区分流式中 vs 历史已完成 */}
          {isStreaming && taskId ? (
            // 1. 正在流式执行中的任务：直接展示动态 Step 容器与 SSE 流
            <StepContainer taskId={taskId} isStreaming={true} />
          ) : (
            // 2. 历史消息：Markdown 结构化渲染正文回复 + 折叠懒加载步骤详情
            <div className="space-y-3">
              {/* 正文 Markdown 渲染 */}
              {message.content?.text ? (
                <div className="prose prose-invert prose-sm max-w-none text-slate-100 text-sm leading-relaxed font-sans">
                  <ReactMarkdown
                    components={{
                      code({ className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || "");
                        const isInline = !match && !String(children).includes("\n");

                        if (isInline) {
                          return (
                            <code
                              className="px-1.5 py-0.5 rounded-md bg-slate-800 text-indigo-300 font-mono text-xs border border-slate-700"
                              {...props}
                            >
                              {children}
                            </code>
                          );
                        }

                        return (
                          <CodeBlock
                            language={match ? match[1] : ""}
                            value={String(children).replace(/\n$/, "")}
                          />
                        );
                      },
                      table({ children }) {
                        return (
                          <div className="my-3 overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60">
                            <table className="min-w-full divide-y divide-slate-800 text-xs text-left">
                              {children}
                            </table>
                          </div>
                        );
                      },
                      th({ children }) {
                        return (
                          <th className="px-3.5 py-2.5 bg-slate-900 font-semibold text-slate-200">
                            {children}
                          </th>
                        );
                      },
                      td({ children }) {
                        return (
                          <td className="px-3.5 py-2 border-t border-slate-800/60 text-slate-300">
                            {children}
                          </td>
                        );
                      },
                      a({ href, children, ...props }) {
                        return (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-indigo-400 hover:text-indigo-300 underline underline-offset-4 decoration-indigo-500/50 hover:decoration-indigo-400 transition-colors font-medium cursor-pointer"
                            {...props}
                          >
                            <span>{children}</span>
                            <span className="text-[10px] opacity-80">↗</span>
                          </a>
                        );
                      },
                    }}
                  >
                    {message.content.text}
                  </ReactMarkdown>
                </div>
              ) : null}

              {/* 历史任务折叠步骤面板（仅在用户点击时懒加载请求，0 冗余开销） */}
              {taskId && (
                <div className="pt-2 border-t border-slate-800/60">
                  <div className="flex items-center justify-between">
                    <button
                      onClick={() => setIsDetailsExpanded((prev) => !prev)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-800/60 hover:bg-slate-800 text-[11px] text-slate-400 hover:text-indigo-300 transition-all font-mono border border-slate-700/50"
                    >
                      <Layers className="w-3.5 h-3.5 text-indigo-400" />
                      <span>{isDetailsExpanded ? "收起执行步骤与工具调用" : "展开执行过程与工具调用"}</span>
                      {isDetailsExpanded ? (
                        <ChevronUp className="w-3 h-3 ml-0.5" />
                      ) : (
                        <ChevronDown className="w-3 h-3 ml-0.5" />
                      )}
                    </button>
                    <span className="text-[10px] text-slate-500 font-mono">
                      Task: {taskId.slice(0, 8)}
                    </span>
                  </div>

                  {/* 展开内容：只有展开时才挂载 StepContainer 并触发接口拉取 */}
                  <AnimatePresence>
                    {isDetailsExpanded && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden mt-2.5 pl-1"
                      >
                        <StepContainer taskId={taskId} isStreaming={false} />
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

MessageItem.displayName = "MessageItem";
