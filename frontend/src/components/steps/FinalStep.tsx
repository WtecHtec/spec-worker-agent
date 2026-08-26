"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Sparkles } from "lucide-react";
import { useTypewriter } from "@/hooks/useTypewriter";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { motion } from "framer-motion";
import { SANDBOX_BASE } from "@/lib/api";

interface FinalStepProps {
  text: string;
  isStreaming?: boolean;
}

export const FinalStep: React.FC<FinalStepProps> = React.memo(({
  text,
  isStreaming = false,
}) => {
  const { displayedText, isTyping } = useTypewriter(text, {
    isStreaming,
    speed: 12,
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: "easeOut" }}
      className="rounded-2xl border border-indigo-500/20 bg-slate-900/90 backdrop-blur-md p-4 shadow-lg shadow-indigo-950/20 select-text"
    >
      <div className="flex items-center gap-2 mb-2 text-indigo-400 font-semibold text-xs">
        <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
        <span>最终回复</span>
      </div>

      <div className="prose prose-invert prose-sm max-w-none text-slate-100 text-sm leading-relaxed font-sans select-text">
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
          {displayedText}
        </ReactMarkdown>
        {isTyping && (
          <span className="inline-block w-2 h-4 ml-0.5 bg-indigo-400 animate-pulse align-middle" />
        )}
      </div>
    </motion.div>
  );
});

FinalStep.displayName = "FinalStep";
