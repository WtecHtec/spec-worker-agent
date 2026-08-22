"use client";

import React, { useState } from "react";
import { Terminal, Wrench, ChevronDown, ChevronRight } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface ToolCallStepProps {
  toolName: string;
  args: Record<string, any>;
  stepIndex: number;
}

export const ToolCallStep: React.FC<ToolCallStepProps> = React.memo(({
  toolName,
  args,
  stepIndex,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="my-2 rounded-xl border border-amber-900/40 bg-amber-950/20 backdrop-blur-md overflow-hidden"
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs text-amber-300 hover:bg-amber-950/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Wrench className="w-3.5 h-3.5" />
          </div>
          <span className="font-semibold text-slate-200">步骤 {stepIndex}：调用工具</span>
          <code className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-200 font-mono text-[11px] font-medium border border-amber-500/30">
            {toolName}
          </code>
        </div>
        {isOpen ? (
          <ChevronDown className="w-3.5 h-3.5 text-amber-500/60" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-amber-500/60" />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="px-3.5 py-2.5 border-t border-amber-900/30 bg-slate-950/70 font-mono text-[11px] overflow-hidden"
          >
            <div className="text-slate-400 mb-1 flex items-center gap-1.5">
              <Terminal className="w-3 h-3 text-amber-400" />
              <span>输入参数：</span>
            </div>
            <pre className="text-amber-200/90 overflow-x-auto p-2.5 rounded-lg bg-slate-900/90 border border-slate-800">
              {JSON.stringify(args, null, 2)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

ToolCallStep.displayName = "ToolCallStep";
