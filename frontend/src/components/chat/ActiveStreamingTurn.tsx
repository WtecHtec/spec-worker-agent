"use client";

import React, { useRef, useEffect, useState } from "react";
import { Bot, Clock, ChevronDown, ChevronUp } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { NormalizedTurn } from "@/lib/messageNormalizer";

interface ActiveStreamingTurnProps {
  turn: NormalizedTurn;
  onScrollBottom?: () => void;
}

/**
 * 独立的活动流式叶子组件：
 * 将高频 Token 拼装与步骤卡片完全隔离在此组件内部，历史消息 0 重绘！
 */
export const ActiveStreamingTurn: React.FC<ActiveStreamingTurnProps> = ({ turn, onScrollBottom }) => {
  const [isStepsExpanded, setIsStepsExpanded] = useState(true);
  const rafIdRef = useRef<number | null>(null);

  // 帧率对齐吸底（16.6ms rAF 批处理，杜绝高频掉帧）
  useEffect(() => {
    if (rafIdRef.current === null && onScrollBottom) {
      rafIdRef.current = requestAnimationFrame(() => {
        rafIdRef.current = null;
        onScrollBottom();
      });
    }
    return () => {
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [turn.content, turn.steps, onScrollBottom]);

  return (
    <div className="flex justify-start my-4 animate-in fade-in duration-200">
      <div className="flex gap-3 max-w-[92%] sm:max-w-[85%] items-start w-full">
        {/* Agent 头像 + 呼吸灯 */}
        <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shrink-0 shadow-md shadow-indigo-900/40 relative">
          <Bot className="w-4 h-4" />
          <span className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-slate-950 animate-pulse" />
        </div>

        <div className="flex-1 rounded-2xl rounded-tl-sm border border-indigo-500/30 bg-slate-900/90 backdrop-blur-xl p-4 text-slate-100 shadow-xl shadow-indigo-950/20">
          {/* 状态顶栏：高亮展示正在流式执行中 */}
          <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800/80 text-xs">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-200 text-xs">Antigravity Agent</span>
              <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 animate-pulse font-mono">
                <Clock className="w-2.5 h-2.5 animate-spin" />
                正在深度思考与执行...
              </span>
            </div>
            <span className="text-[10px] text-indigo-400/80 font-mono">实时流式</span>
          </div>

          {/* 正在执行的动态步骤折叠卡片 */}
          {turn.steps && turn.steps.length > 0 && (
            <div className="mb-3 rounded-xl border border-indigo-500/20 bg-slate-950/70 overflow-hidden text-xs">
              <button
                type="button"
                onClick={() => setIsStepsExpanded((prev) => !prev)}
                className="w-full flex items-center justify-between px-3 py-2 text-slate-300 hover:bg-slate-900/50 transition-colors font-mono"
              >
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse" />
                  <span className="font-semibold text-indigo-300">
                    执行工具步骤（{turn.steps.length} 个进行中）
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[11px] text-slate-500">
                  <span>{isStepsExpanded ? "收起" : "展开"}</span>
                  {isStepsExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                </div>
              </button>

              {isStepsExpanded && (
                <div className="px-3 pb-3 space-y-2 border-t border-slate-800/60 pt-2 font-mono">
                  {turn.steps.map((step, idx) => (
                    <div key={step.toolCallId || idx} className="rounded-lg bg-slate-900/90 border border-slate-800/80 p-2.5 space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-indigo-400 text-[11px]">🛠️ {step.toolName}</span>
                        <span className="text-[10px] text-indigo-300/80 font-mono">
                          {step.output ? "✓ 执行完毕" : "正在调用..."}
                        </span>
                      </div>
                      {step.args && Object.keys(step.args).length > 0 && (
                        <div className="text-[10px] text-slate-400 bg-slate-950/70 p-1.5 rounded border border-slate-800/60 overflow-x-auto">
                          <span className="text-slate-500 block mb-0.5">参数：</span>
                          {JSON.stringify(step.args, null, 2)}
                        </div>
                      )}
                      {step.output && (
                        <div className="text-[10px] text-slate-300 bg-slate-950/90 p-1.5 rounded border border-slate-800/80 max-h-36 overflow-y-auto whitespace-pre-wrap">
                          <span className="text-emerald-500 font-semibold block mb-0.5">产出：</span>
                          {step.output}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* 实时 Markdown 打字正文 */}
          {turn.content ? (
            <div className="prose prose-invert prose-sm max-w-none text-slate-100 text-sm leading-relaxed font-sans">
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
                {turn.content}
              </ReactMarkdown>
            </div>
          ) : (
            // 尚未生成文字时展示优雅的脉冲占位条
            <div className="flex items-center gap-1.5 py-2 text-indigo-400/70 text-xs font-mono animate-pulse">
              <span className="w-2 h-2 rounded-full bg-indigo-500" />
              <span>思考中...</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
