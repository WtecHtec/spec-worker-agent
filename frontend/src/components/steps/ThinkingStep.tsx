"use client";

import React, { useState } from "react";
import { ChevronDown, ChevronRight, BrainCircuit } from "lucide-react";
import { useTypewriter } from "@/hooks/useTypewriter";
import { motion, AnimatePresence } from "framer-motion";

interface ThinkingStepProps {
  text: string;
  isStreaming?: boolean;
  stepIndex: number;
}

export const ThinkingStep: React.FC<ThinkingStepProps> = React.memo(({
  text,
  isStreaming = false,
  stepIndex,
}) => {
  const [isOpen, setIsOpen] = useState(true);
  const { displayedText, isTyping } = useTypewriter(text, {
    isStreaming,
    speed: 15,
  });

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="my-2 rounded-xl border border-slate-800/80 bg-slate-900/60 backdrop-blur-md overflow-hidden transition-all duration-300"
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800/40 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-md bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <BrainCircuit className="w-3.5 h-3.5 animate-pulse" />
          </div>
          <span className="text-slate-300 font-semibold">步骤 {stepIndex}：思考分析</span>
          {isTyping && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] bg-indigo-500/20 text-indigo-300 animate-pulse">
              思考中...
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
        ) : (
          <ChevronRight className="w-3.5 h-3.5 text-slate-500" />
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="px-3.5 pb-3 pt-1 text-xs text-slate-300 leading-relaxed font-sans border-t border-slate-800/50 bg-slate-950/40 overflow-hidden"
          >
            <div className="whitespace-pre-wrap">
              {displayedText}
              {isTyping && (
                <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-indigo-400 animate-pulse align-middle" />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

ThinkingStep.displayName = "ThinkingStep";
