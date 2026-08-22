"use client";

import React, { useState, useEffect } from "react";
import { Check, Loader2, ShieldAlert } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/useAuthStore";
import { useTaskStore } from "@/store/useTaskStore";
import { toast } from "@/store/useToastStore";
import { motion } from "framer-motion";

interface HitlStepProps {
  taskId: string;
  stepIndex: number;
  question: string;
  options?: Array<{ value: string; label: string }>;
}

export const HitlStep: React.FC<HitlStepProps> = React.memo(({
  taskId,
  stepIndex,
  question,
  options = [],
}) => {
  const token = useAuthStore((state) => state.token);
  const activeHitl = useTaskStore((state) => state.activeHitlByTask[taskId]);
  const setHitl = useTaskStore((state) => state.setHitl);

  const [selected, setSelected] = useState<string>("");
  const [customText, setCustomText] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedChoice, setSubmittedChoice] = useState<string | null>(null);

  const isChoiceMode = options && options.length > 0;
  const isFetchingRef = React.useRef(false);

  // 组件挂载时若未拿到 activeHitl.id，自动从服务端补齐（带防并发锁）
  useEffect(() => {
    if (!activeHitl?.id && taskId && token && !isFetchingRef.current) {
      isFetchingRef.current = true;
      api.getPendingHitl(taskId, token)
        .then((data) => {
          if (data) {
            setHitl(taskId, data);
          }
        })
        .catch((err) => console.warn("Failed to fetch pending HITL:", err))
        .finally(() => {
          isFetchingRef.current = false;
        });
    }
  }, [taskId, token, activeHitl?.id, setHitl]);

  const handleSubmit = async () => {
    const decision = isChoiceMode ? selected : customText.trim();
    if (!decision) {
      toast.warning("请先选择一个处理选项或输入您的决策", "未选择决策");
      return;
    }
    if (!token) {
      toast.error("未检测到登录状态，请先登录", "未授权");
      return;
    }

    setIsSubmitting(true);
    try {
      // 若本地 store 暂无 hitlId，动态从后端拉取
      let hitlId = activeHitl?.id;
      if (!hitlId) {
        const pending = await api.getPendingHitl(taskId, token);
        if (pending && pending.id) {
          hitlId = pending.id;
          setHitl(taskId, pending);
        }
      }

      if (!hitlId) {
        throw new Error("未找到待处理的审批请求，可能已被处理或已过期");
      }

      await api.respondHitl(
        taskId,
        hitlId,
        decision,
        token,
        !isChoiceMode ? { text: customText } : undefined
      );

      setSubmittedChoice(decision);
      setHitl(taskId, null);
      toast.success("人工决策已提交，Agent 正在继续执行", "决策已响应");
    } catch (err: any) {
      console.error("Failed to submit HITL response:", err);
      toast.error(err.message || "提交决策失败，请重试", "提交失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  const isResolved = submittedChoice !== null;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className="my-3 rounded-2xl border border-rose-500/30 bg-gradient-to-b from-rose-950/30 to-slate-900/60 p-4 shadow-xl backdrop-blur-md"
    >
      <div className="flex items-center gap-2.5 mb-3 text-rose-400 font-semibold text-xs tracking-wide uppercase">
        <div className="p-1 rounded-md bg-rose-500/20 text-rose-400 border border-rose-500/30">
          <ShieldAlert className="w-4 h-4" />
        </div>
        <span>步骤 {stepIndex}：需要人工确认 (Human In The Loop)</span>
      </div>

      <div className="text-sm font-medium text-slate-100 mb-4 leading-relaxed">
        {question}
      </div>

      {isChoiceMode ? (
        <div className="space-y-2 mb-4">
          {options.map((opt) => {
            const isChecked = isResolved ? submittedChoice === opt.value : selected === opt.value;
            return (
              <label
                key={opt.value}
                onClick={() => !isResolved && setSelected(opt.value)}
                className={`flex items-center justify-between p-3 rounded-xl border text-xs cursor-pointer transition-all duration-200 ${
                  isChecked
                    ? "border-rose-500/80 bg-rose-500/15 text-rose-100 font-medium shadow-sm shadow-rose-950/50"
                    : isResolved
                    ? "border-slate-800 bg-slate-900/30 text-slate-500 cursor-not-allowed"
                    : "border-slate-800/80 bg-slate-900/40 text-slate-300 hover:border-slate-700 hover:bg-slate-800/50"
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors ${
                      isChecked
                        ? "border-rose-500 bg-rose-500 text-white"
                        : "border-slate-600 bg-slate-800"
                    }`}
                  >
                    {isChecked && <div className="w-1.5 h-1.5 rounded-full bg-white" />}
                  </div>
                  <span>{opt.label}</span>
                </div>
              </label>
            );
          })}
        </div>
      ) : (
        <div className="mb-4">
          <textarea
            disabled={isResolved || isSubmitting}
            value={isResolved ? submittedChoice || "" : customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="请输入您的决策或补充信息..."
            rows={2}
            className="w-full rounded-xl border border-slate-700 bg-slate-950/80 p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-rose-500"
          />
        </div>
      )}

      {!isResolved ? (
        <button
          onClick={handleSubmit}
          disabled={(isChoiceMode ? !selected : !customText.trim()) || isSubmitting}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 shadow-md shadow-rose-950/40 active:scale-[0.99]"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>提交决策中...</span>
            </>
          ) : (
            <>
              <Check className="w-3.5 h-3.5" />
              <span>确认并继续执行</span>
            </>
          )}
        </button>
      ) : (
        <div className="flex items-center gap-2 text-xs text-emerald-400 bg-emerald-950/30 border border-emerald-900/40 px-3 py-2 rounded-xl">
          <Check className="w-3.5 h-3.5 text-emerald-400" />
          <span>已确认决策 ({submittedChoice})，任务正在恢复执行...</span>
        </div>
      )}
    </motion.div>
  );
});

HitlStep.displayName = "HitlStep";
