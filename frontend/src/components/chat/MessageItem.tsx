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
import remarkGfm from "remark-gfm";
import { Message } from "@/types";
import { StepContainer } from "../steps/StepContainer";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { WebPreviewCard } from "./WebPreviewCard";
import { HitlFormCard, FormField } from "./HitlFormCard";
import { formatDate } from "@/lib/utils";
import { SANDBOX_BASE } from "@/lib/api";
import { useSessionStore } from "@/store/useSessionStore";
import { normalizeRole, extractMessageText } from "@/lib/messageNormalizer";

export interface LangGraphMessage {
  id?: string;
  type?: string;     // "human" | "ai" | "tool" | "system"
  role?: string;     // 兼容旧格式 "USER" | "AGENT"
  content?: any;
  tool_calls?: Array<{
    id?: string;
    name: string;
    args: any;
  }>;
  status?: string;
  created_at?: string;
  [key: string]: any;
}

interface MessageItemProps {
  message: Message | LangGraphMessage | any;
}

export const MessageItem: React.FC<MessageItemProps> = React.memo(({ message }) => {
  // 工业级角色归一化：彻底抹平大小写与类名差异
  const role = normalizeRole(message);
  const isUser = role === "user";
  const isTool = role === "tool";

  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const activeSessionId = message.session_id || currentSessionId || undefined;
  const taskId = message.task_id || message.content?.task_id;
  const taskStatus = message.content?.task_status;
  const isStreaming =
    message.status === "streaming" &&
    taskStatus !== "COMPLETED" &&
    taskStatus !== "FAILED" &&
    taskStatus !== "CANCELLED";

  // 历史已完成任务默认折叠步骤，按需懒加载
  const [isDetailsExpanded, setIsDetailsExpanded] = useState(false);

  // 工业级文本提取函数：支持字符串、递归数组、对象
  const messageText = extractMessageText(message);

  // 提取消息中的 HTML 文件或预览链接
  const extractWebPreviewInfo = () => {
    const text = messageText;

    // 0. 优先检测是否生成了前端 NPM 工程 (package.json / React / Vite)
    if (text.includes("package.json") || (text.includes("vite") && text.includes("React"))) {
      return {
        previewUrl: "",
        fileName: "package.json",
        isWebContainer: true,
        title: "React / Vite 前端工程",
      };
    }

    // 1. 直接匹配 http://localhost:5050/fs/raw?path=...
    const urlMatch = text.match(/(https?:\/\/[^\s\)\"]+\/fs\/(?:raw|preview)\?path=([^\s\)\"]+\.html))/i);
    if (urlMatch) {
      const fullUrl = urlMatch[1];
      const filename = decodeURIComponent(urlMatch[2]);
      return { previewUrl: fullUrl, fileName: filename, isWebContainer: false, title: `Web 页面: ${filename}` };
    }

    // 2. 匹配相对路径 /fs/raw?path=...html
    const relMatch = text.match(/(\/fs\/(?:raw|preview)\?path=([^\s\)\"]+\.html))/i);
    if (relMatch) {
      const filename = decodeURIComponent(relMatch[2]);
      return { previewUrl: `${SANDBOX_BASE}${relMatch[1]}`, fileName: filename, isWebContainer: false, title: `Web 页面: ${filename}` };
    }

    // 3. 匹配文本中提到的 .html 文件名 (如 index.html, preview.html, game.html)
    const htmlFileMatch = text.match(/\b([\w\-_/]+\.html)\b/i);
    if (htmlFileMatch && (text.includes("写入") || text.includes("生成") || text.includes("创建") || text.includes("预览") || text.includes("HTML") || text.includes("网页") || text.includes("html"))) {
      const filename = htmlFileMatch[1];
      const previewUrl = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(filename.replace(/^\.?\//, ""))}`;
      return { previewUrl, fileName: filename, isWebContainer: false, title: `Web 页面: ${filename}` };
    }

    return null;
  };

  // 提取消息中的人机协同 (HITL) 表单结构（仅在包含合法结构化表单时解析，杜绝普通文本关键词误判）
  const extractHitlInfo = () => {
    const text = messageText;
    if (!text || !text.includes('"form_fields"')) {
      return null;
    }

    try {
      // 严格匹配 JSON 格式的表单定义
      const jsonMatch = text.match(/(\{[\s\S]*"form_fields"[\s\S]*\})/);
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[1]);
        if (Array.isArray(parsed.form_fields) && parsed.form_fields.length > 0) {
          return {
            title: parsed.title || "人机协同交互确认",
            description: parsed.description || "",
            riskLevel: parsed.risk_level || "medium",
            formFields: parsed.form_fields,
          };
        }
      }
    } catch (_) { }

    return null;
  };

  const webPreview = !isUser ? extractWebPreviewInfo() : null;
  const hitlInfo = !isUser ? extractHitlInfo() : null;

  const handleHitlSubmit = (formData: Record<string, any>) => {
    const lines = Object.entries(formData).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`);
    const replyText = `[人机协同审批结果提交]\n${lines.join("\n")}`;
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("submit_hitl_response", { detail: replyText }));
    }
  };

  const formattedTime = formatDate(message.created_at || message.response_metadata?.created_at);

  if (isTool) {
    return (
      <div className="flex justify-start my-2 max-w-[85%] animate-in fade-in duration-200">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] text-slate-400 font-mono">
          <span className="text-emerald-400 font-semibold">⚡ 工具产出:</span>
          <span className="truncate max-w-lg text-slate-300">{messageText}</span>
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex justify-end my-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="flex gap-3 max-w-[80%] items-start">
          <div className="rounded-2xl rounded-tr-sm bg-gradient-to-r from-indigo-600 to-indigo-700 px-4 py-3 text-white text-sm shadow-md shadow-indigo-950/30">
            <p className="whitespace-pre-wrap leading-relaxed">{messageText}</p>
            {formattedTime && (
              <div className="mt-1 text-[10px] text-indigo-200/80 text-right font-mono">
                {formattedTime}
              </div>
            )}
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
              <span className="font-semibold text-slate-200 text-xs">X Agent</span>
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

            {formattedTime && (
              <span className="text-[10px] text-slate-500 font-mono">{formattedTime}</span>
            )}
          </div>

          {/* 步骤伴随的 AI 思考/执行思路说明（展示 tool_calls 携带的说明正文） */}
          {message.steps && Array.isArray(message.steps) && message.steps.some((s: any) => s.thought) && (
            <div className="mb-3 space-y-2.5">
              {message.steps
                .filter((s: any) => s.thought)
                .map((step: any, idx: number) => (
                  <div key={step.toolCallId || idx} className="prose prose-invert prose-sm max-w-none text-slate-100 text-sm leading-relaxed font-sans">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        code({ className, children, ...props }) {
                          const match = /language-(\w+)/.exec(className || "");
                          const isInline = !match && !String(children).includes("\n");
                          if (isInline) {
                            return (
                              <code className="px-1.5 py-0.5 rounded-md bg-slate-800 text-indigo-300 font-mono text-xs border border-slate-700 select-text" {...props}>
                                {children}
                              </code>
                            );
                          }
                          return <CodeBlock language={match ? match[1] : ""} value={String(children).replace(/\n$/, "")} />;
                        },
                      }}
                    >
                      {step.thought}
                    </ReactMarkdown>
                  </div>
                ))}
            </div>
          )}

          {/* 整合工具步骤折叠栏（将 tool 产出与 tool_calls 步骤无缝缝合） */}
          {message.steps && Array.isArray(message.steps) && message.steps.length > 0 && (
            <div className="mb-3 rounded-xl border border-slate-800/80 bg-slate-950/60 overflow-hidden text-xs">
              <button
                type="button"
                onClick={() => setIsDetailsExpanded((prev) => !prev)}
                className="w-full flex items-center justify-between px-3 py-2 text-slate-300 hover:bg-slate-900/50 transition-colors font-mono"
              >
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-indigo-400" />
                  <span className="font-semibold text-indigo-300">
                    已执行 {message.steps.length} 个工具调用步骤
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-slate-500">
                  <span>{isDetailsExpanded ? "收起" : "展开详情"}</span>
                  {isDetailsExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </div>
              </button>

              {isDetailsExpanded && (
                <div className="px-3 pb-3 space-y-2 border-t border-slate-800/60 pt-2 font-mono">
                  {message.steps.map((step: any, idx: number) => (
                    <div key={step.toolCallId || idx} className="rounded-lg bg-slate-900/90 border border-slate-800 p-2.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-indigo-400 text-[11px]">🛠️ {step.toolName}</span>
                        <span className="text-[10px] text-emerald-400 font-semibold">✓ 成功执行</span>
                      </div>
                      {step.args && Object.keys(step.args).length > 0 && (
                        <div className="text-[10px] text-slate-400 bg-slate-950/70 p-1.5 rounded border border-slate-800/60 overflow-x-auto">
                          <span className="text-slate-500 block mb-0.5">调用入参：</span>
                          {JSON.stringify(step.args, null, 2)}
                        </div>
                      )}
                      {step.output && (
                        <div className="text-[10px] text-slate-300 bg-slate-950/90 p-1.5 rounded border border-slate-800/80 max-h-36 overflow-y-auto whitespace-pre-wrap">
                          <span className="text-emerald-500 font-semibold block mb-0.5">执行产出：</span>
                          {step.output}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* LangGraph 独立 tool_calls 工具执行卡片（无关联 steps 时的降级呈现） */}
          {(!message.steps || message.steps.length === 0) && message.tool_calls && Array.isArray(message.tool_calls) && message.tool_calls.length > 0 && (
            <div className="mb-2 space-y-1">
              {message.tool_calls.map((tc: any, idx: number) => (
                <div
                  key={tc.id || idx}
                  className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-indigo-950/40 border border-indigo-500/20 text-xs text-indigo-300 font-mono"
                >
                  <div className="flex items-center gap-2 truncate">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                    <span className="font-semibold text-indigo-200">🛠️ {tc.name}</span>
                    <span className="text-slate-400 text-[11px] truncate max-w-sm">
                      {tc.args ? JSON.stringify(tc.args) : ""}
                    </span>
                  </div>
                  <span className="text-[10px] text-indigo-400/80 shrink-0 ml-2">执行完毕</span>
                </div>
              ))}
            </div>
          )}

          {/* 渲染内容：区分流式中 vs 历史已完成 */}
          {isStreaming && taskId ? (
            // 1. 正在流式执行中的任务：直接展示动态 Step 容器与 SSE 流
            <StepContainer taskId={taskId} isStreaming={true} />
          ) : (
            // 2. 历史消息：Markdown 结构化渲染正文回复 + 折叠懒加载步骤详情
            <div className="space-y-3">
              {/* 正文 Markdown 渲染（若内容已在 step.thought 中展示，则避免重复呈现） */}
              {messageText && (!message.steps || !message.steps.some((s: any) => s.thought === messageText)) ? (
                <div className="prose prose-invert prose-sm max-w-none text-slate-100 text-sm leading-relaxed font-sans">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      code({ className, children, ...props }) {
                        const match = /language-(\w+)/.exec(className || "");
                        const isInline = !match && !String(children).includes("\n");

                        if (isInline) {
                          return (
                            <code
                              className="px-1.5 py-0.5 rounded-md bg-slate-800 text-indigo-300 font-mono text-xs border border-slate-700 select-text"
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
                        let targetHref = href || "#";
                        // 智能补全未带域名的沙箱文件链接或相对路径
                        if (!targetHref.startsWith("http://") && !targetHref.startsWith("https://") && !targetHref.startsWith("mailto:") && !targetHref.startsWith("#")) {
                          if (targetHref.startsWith("/fs/raw") || targetHref.startsWith("/fs/preview")) {
                            targetHref = `${SANDBOX_BASE}${targetHref}`;
                          } else if (targetHref.startsWith("screenshots/") || targetHref.startsWith("images/") || targetHref.endsWith(".png") || targetHref.endsWith(".jpg") || targetHref.endsWith(".jpeg") || targetHref.endsWith(".webp")) {
                            targetHref = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(targetHref.replace(/^\.?\//, ""))}`;
                          } else if (targetHref.startsWith("/")) {
                            targetHref = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(targetHref.replace(/^\//, ""))}`;
                          }
                        }

                        return (
                          <a
                            href={targetHref}
                            target="_blank"
                            rel="noopener noreferrer"
                            onClick={(e) => e.stopPropagation()}
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
                    {messageText}
                  </ReactMarkdown>
                </div>
              ) : null}

              {/* 渲染 Web 实时预览卡片 */}
              {webPreview && (
                <WebPreviewCard
                  fileName={webPreview.fileName}
                  previewUrl={webPreview.previewUrl}
                  title={webPreview.title || `Web 页面预览: ${webPreview.fileName}`}
                  sessionId={activeSessionId}
                  isWebContainer={webPreview.isWebContainer}
                />
              )}

              {/* 渲染 HITL 人机协同表单卡片 */}
              {hitlInfo && (
                <HitlFormCard
                  title={hitlInfo.title}
                  description={hitlInfo.description}
                  riskLevel={hitlInfo.riskLevel}
                  formFields={hitlInfo.formFields}
                  onSubmit={handleHitlSubmit}
                />
              )}

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
