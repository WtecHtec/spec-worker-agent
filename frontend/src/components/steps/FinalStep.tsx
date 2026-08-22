"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import { Sparkles } from "lucide-react";
import { useTypewriter } from "@/hooks/useTypewriter";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { motion } from "framer-motion";

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
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mt-3 pt-3 border-t border-slate-800/80"
    >
      <div className="flex items-center gap-2 mb-2 text-indigo-400 font-semibold text-xs">
        <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
        <span>最终回复</span>
      </div>

      <div className="prose prose-invert prose-sm max-w-none text-slate-100 text-sm leading-relaxed font-sans">
        <ReactMarkdown
          components={{
            code({ className, children, ...props }) {
              const match = /language-(\w+)/.exec(className || "");
              const isInline = !match && !String(children).includes("\n");

              if (isInline) {
                return (
                  <code className="px-1.5 py-0.5 rounded-md bg-slate-800 text-indigo-300 font-mono text-xs border border-slate-700" {...props}>
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
