"use client";

import React, { useState } from "react";
import { ListOrdered, ChevronDown, ChevronRight, CheckCircle2, Circle, Clock, RefreshCw } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface PlanItem {
  id: number;
  title: string;
  description: string;
  status: "pending" | "in_progress" | "completed" | "failed" | "skipped";
  result_summary?: string | null;
}

interface PlanStepProps {
  goal: string;
  steps: PlanItem[];
  isReplan?: boolean;
  stepIndex: number;
}

export const PlanStep: React.FC<PlanStepProps> = React.memo(({
  goal,
  steps = [],
  isReplan = false,
  stepIndex,
}) => {
  const [isOpen, setIsOpen] = useState(true);

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className={`my-2 rounded-xl border backdrop-blur-md overflow-hidden transition-all ${
        isReplan
          ? "border-amber-500/30 bg-amber-950/20"
          : "border-indigo-500/30 bg-indigo-950/20"
      }`}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between px-3.5 py-2.5 text-xs font-medium text-slate-300 hover:bg-indigo-950/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div
            className={`p-1 rounded-md border ${
              isReplan
                ? "bg-amber-500/10 text-amber-400 border-amber-500/20"
                : "bg-indigo-500/10 text-indigo-400 border-indigo-500/20"
            }`}
          >
            {isReplan ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin [animation-duration:4s]" />
            ) : (
              <ListOrdered className="w-3.5 h-3.5" />
            )}
          </div>
          <span className="font-semibold text-slate-200">
            {isReplan ? "动态重规划：计划已自适应调整" : `步骤 ${stepIndex}：宏观规划分解清单`}
          </span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 font-mono">
            {steps.length} 个子任务
          </span>
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
            className="px-3.5 pb-3 pt-1 border-t border-slate-800/60 bg-slate-950/60 space-y-2"
          >
            <div className="text-[11px] text-slate-400 mb-2">
              <span className="font-semibold text-slate-300">目标：</span>
              {goal}
            </div>

            <div className="space-y-1.5">
              {steps.map((s) => {
                const isDone = s.status === "completed";
                const isDoing = s.status === "in_progress";
                const isFail = s.status === "failed";

                return (
                  <div
                    key={s.id}
                    className={`flex items-start gap-2.5 p-2 rounded-lg border text-xs transition-all ${
                      isDone
                        ? "bg-emerald-950/20 border-emerald-900/40 text-emerald-300"
                        : isDoing
                        ? "bg-indigo-950/30 border-indigo-500/40 text-indigo-200 shadow-sm shadow-indigo-950"
                        : isFail
                        ? "bg-rose-950/20 border-rose-900/40 text-rose-300"
                        : "bg-slate-900/40 border-slate-800/80 text-slate-400"
                    }`}
                  >
                    <div className="mt-0.5 shrink-0">
                      {isDone ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      ) : isDoing ? (
                        <Clock className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
                      ) : isFail ? (
                        <Circle className="w-3.5 h-3.5 text-rose-400 fill-rose-500/20" />
                      ) : (
                        <Circle className="w-3.5 h-3.5 text-slate-600" />
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between font-medium">
                        <span>
                          {s.id}. {s.title}
                        </span>
                        <span className="text-[10px] font-mono capitalize opacity-70">
                          {s.status}
                        </span>
                      </div>
                      {s.description && (
                        <div className="text-[11px] text-slate-400 mt-0.5 leading-snug">
                          {s.description}
                        </div>
                      )}
                      {s.result_summary && (
                        <div className="text-[11px] text-emerald-400/90 mt-1 font-mono bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-900/30">
                          产出: {s.result_summary}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
});

PlanStep.displayName = "PlanStep";
