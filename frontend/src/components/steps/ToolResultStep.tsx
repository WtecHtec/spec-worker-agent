"use client";

import React, { useState } from "react";
import { CheckCircle2, Clock, ChevronDown, ChevronRight, FileCode2 } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface ToolResultStepProps {
  toolName: string;
  output: any;
  durationMs?: number;
  stepIndex: number;
}

export const ToolResultStep: React.FC<ToolResultStepProps> = React.memo(({
  toolName,
  output,
  durationMs,
  stepIndex,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="my-2 rounded-xl border border-emerald-900/40 bg-emerald-950/20 backdrop-blur-md overflow-hidden"
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs text-emerald-300 hover:bg-emerald-950/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" />
          </div>
          <span className="font-semibold text-slate-200">步骤 {stepIndex}：工具执行结果</span>
          <span className="text-slate-400 font-mono text-[11px]">({toolName})</span>
          {durationMs !== undefined && (
            <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono">
              <Clock className="w-2.5 h-2.5" />
              {durationMs}ms
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-3.5 h-3.5 text-emerald-500/60" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-emerald-500/60" />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="px-3.5 py-2.5 border-t border-emerald-900/30 bg-slate-950/70 font-mono text-[11px] overflow-hidden"
          >
            <div className="text-slate-400 mb-1 flex items-center gap-1.5">
              <FileCode2 className="w-3 h-3 text-emerald-400" />
              <span>返回数据：</span>
            </div>
            <pre className="text-emerald-200/90 overflow-x-auto p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
              {typeof output === "object" ? JSON.stringify(output, null, 2) : String(output)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

ToolResultStep.displayName = "ToolResultStep";
