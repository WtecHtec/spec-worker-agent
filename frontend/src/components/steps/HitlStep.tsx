"use client";

import React, { useState, useEffect } from "react";
import { Check, Loader2, ShieldAlert, XCircle, Lock } from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/useAuthStore";
import { useTaskStore } from "@/store/useTaskStore";
import { toast } from "@/store/useToastStore";
import { motion } from "framer-motion";

interface HitlStepProps {
  taskId: string;
  stepIndex: number;
  question: string;
  detail?: any;
  options?: Array<{ value: string; label: string }>;
}

export const HitlStep: React.FC<HitlStepProps> = React.memo(({
  taskId,
  stepIndex,
  question,
  detail,
  options = [],
}) => {

  const token = useAuthStore((state) => state.token);
  const activeHitl = useTaskStore((state) => state.activeHitlByTask?.[taskId]);
  const taskStatus = useTaskStore((state) => state.taskStatus?.[taskId]);
  const setHitl = useTaskStore((state) => state.setHitl);


  const [selected, setSelected] = useState<string>("approve");
  const [customText, setCustomText] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submittedChoice, setSubmittedChoice] = useState<string | null>(null);
  const [isServerResolved, setIsServerResolved] = useState<boolean>(false);
  const [mounted, setMounted] = useState(false);

  const isFetchingRef = React.useRef(false);

  useEffect(() => {
    setMounted(true);
    // 优先读取本地持久化标记
    try {
      if (typeof window !== "undefined" && localStorage.getItem(`hitl_resolved_${taskId}`)) {
        setIsServerResolved(true);
      }
    } catch (_) {}
  }, [taskId]);

  // 判断任务是否已结束或已完成审批（客户端 mounted 后判定）
  const isTaskFinished = mounted && (taskStatus === "COMPLETED" || taskStatus === "FAILED" || taskStatus === "CANCELLED");
  const isResolved = submittedChoice !== null || isServerResolved || (mounted && activeHitl && activeHitl.status !== "PENDING");
  const isLocked = isResolved || isTaskFinished;

  // 组件挂载时拉取服务端待审批状态
  useEffect(() => {
    if (taskId && token && !isFetchingRef.current && !isTaskFinished && !isServerResolved) {
      isFetchingRef.current = true;
      api.getPendingHitl(taskId, token)
        .then((data) => {
          if (data && data.status === "PENDING") {
            setHitl(taskId, data);
          } else {
            // 服务端已经没有 PENDING 的审批，标记为已解决并锁定
            setIsServerResolved(true);
            setHitl(taskId, null);
          }
        })
        .catch((err) => console.warn("Failed to fetch pending HITL:", err))
        .finally(() => {
          isFetchingRef.current = false;
        });
    }
  }, [taskId, token, isTaskFinished, isServerResolved, setHitl]);


  const handleSubmit = async (decisionOverride?: string) => {
    if (isLocked || isSubmitting) return;

    const decision = decisionOverride || selected || (customText.trim() ? "approve" : "");
    if (!decision) {
      toast.warning("请选择或输入您的决策", "未选择决策");
      return;
    }
    if (!token) {
      toast.error("未检测到登录状态，请先登录", "未授权");
      return;
    }

    setIsSubmitting(true);
    try {
      let hitlId = activeHitl?.id;
      if (!hitlId) {
        const pending = await api.getPendingHitl(taskId, token);
        if (pending?.id) {
          hitlId = pending.id;
          setHitl(taskId, pending);
        }
      }

      if (!hitlId) {
        throw new Error("未找到关联的待审批请求，可能任务已处理或已恢复");
      }

      await api.respondHitl(
        taskId,
        hitlId,
        decision,
        token,
        customText.trim() ? { text: customText.trim() } : undefined
      );

      setSubmittedChoice(decision === "reject" ? "已驳回" : "已确认通过");
      setIsServerResolved(true);
      try {
        if (typeof window !== "undefined") {
          localStorage.setItem(`hitl_resolved_${taskId}`, "true");
        }
      } catch (_) {}
      setHitl(taskId, null);
      toast.success("人工决策已提交，Agent 正在继续执行", "决策已响应");

    } catch (err: any) {
      console.error("Failed to submit HITL response:", err);
      toast.error(err.message || "提交决策失败，请重试", "提交失败");
    } finally {
      setIsSubmitting(false);
    }
  };

  // 提取事项标题并对 null 做全方位安全兜底
  const safeQuestion = String(question || detail?.title || detail?.question || detail?.description || "需要人工确认关键步骤");
  const cleanTitle = safeQuestion.replace(/^需要人工审批高危步骤:\s*/, "").replace(/^请确认是否执行步骤：\s*/, "") || "关键操作人工审查";
  const displayOptions = (options && Array.isArray(options) && options.length > 0) ? options : [
    { value: "approve", label: "批准并继续执行" },
    { value: "reject", label: "驳回并要求调整" },
  ];


  const [showSupplement, setShowSupplement] = useState(false);
  const inputRef = React.useRef<HTMLTextAreaElement>(null);

  const handleOpenSupplement = () => {
    setShowSupplement(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleSupplementSubmit = () => {
    if (!customText.trim()) {
      toast.warning("请填写您的具体补充要求或调整建议", "补充内容为空");
      inputRef.current?.focus();
      return;
    }
    handleSubmit("feedback");
  };


  if (!mounted) {
    return (
      <div className="my-3.5 rounded-2xl border border-amber-500/30 bg-slate-900/60 p-5 shadow-xl">
        <div className="flex items-center gap-2 text-xs font-bold text-amber-400">
          <ShieldAlert className="w-4 h-4" />
          <span>步骤 {stepIndex} · 人机协同确认 (HITL)</span>
        </div>
        <div className="text-sm font-semibold text-slate-200 mt-2">{cleanTitle}</div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.97 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      className={`my-3.5 rounded-2xl border p-5 shadow-2xl backdrop-blur-xl transition-all duration-300 ${
        isLocked
          ? "border-slate-800 bg-slate-900/40 text-slate-400 opacity-80"
          : "border-amber-500/40 bg-gradient-to-b from-amber-950/40 via-slate-900/70 to-slate-950/80 shadow-amber-950/30 ring-1 ring-amber-500/20"
      }`}
    >
      {/* 头部：醒目状态条 + 序号 */}


      <div className="flex items-center justify-between gap-3 mb-3 border-b border-amber-500/20 pb-3">
        <div className="flex items-center gap-2.5">
          <div className={`p-1.5 rounded-lg border ${
            isLocked
              ? "bg-slate-800 text-slate-400 border-slate-700"
              : "bg-amber-500/20 text-amber-400 border-amber-500/30 animate-pulse"
          }`}>
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold uppercase tracking-wider text-amber-400">
                步骤 {stepIndex} · 人机协同确认 (HITL)
              </span>
              {!isLocked && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">
                  等待您的审批
                </span>
              )}
            </div>
          </div>
        </div>

        {isLocked && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium bg-slate-800 text-slate-400 border border-slate-700">
            <Lock className="w-3 h-3" />
            <span>{isTaskFinished ? "任务已完结" : "已完成决议"}</span>
          </div>
        )}
      </div>

      {/* 核心处理事项标题与详细描述区 */}
      <div className="mb-4">
        <div className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-1.5 flex items-center justify-between">
          <span>待审批关键事项：</span>
          {detail?.id && (
            <span className="font-mono text-[10px] text-amber-400/80 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
              步骤序号 #{detail.id}
            </span>
          )}
        </div>
        
        <div className="rounded-xl border border-amber-500/30 bg-slate-950/70 p-4 space-y-2.5">
          {/* 主标题 */}
          <div className="text-sm font-bold text-amber-300 flex items-center gap-2">
            <span>📌</span>
            <span>{detail?.title || cleanTitle}</span>
          </div>

          {/* 详细描述（如有） */}
          {detail?.description && (
            <div className="text-xs text-slate-300 bg-slate-900/60 p-3 rounded-lg border border-slate-800/80 leading-relaxed font-normal whitespace-pre-wrap">
              {detail.description}
            </div>
          )}

          {/* 补充问题说明（如不同于标题） */}
          {cleanTitle && cleanTitle !== detail?.title && (
            <div className="text-[11px] text-slate-400 italic">
              提示说明：{cleanTitle}
            </div>
          )}
        </div>
      </div>

      {/* 用户补充意见输入框（点击补充后展开） */}
      {!isLocked && showSupplement && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mb-4"
        >
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-[11px] font-semibold text-indigo-300">
              ✍️ 补充具体要求 / 修改建议 (必填)：
            </label>
            <button
              type="button"
              onClick={() => setShowSupplement(false)}
              className="text-[11px] text-slate-500 hover:text-slate-300 underline"
            >
              收起
            </button>
          </div>
          <textarea
            ref={inputRef}
            disabled={isLocked || isSubmitting}
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            placeholder="例如：同意执行，但将端口号改为 8080；或请换用轻量化迁移方案..."
            rows={2}
            className="w-full rounded-xl border border-indigo-500/40 bg-slate-950/90 p-3 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-400 focus:ring-1 focus:ring-indigo-400/40 transition-all"
          />
        </motion.div>
      )}

      {/* 操作按钮区：【确定】、【补充】、【取消】 */}
      {!isLocked ? (
        <div className="flex flex-wrap items-center gap-2.5">
          {!showSupplement ? (
            <>
              {/* 1. 确定 */}
              <button
                type="button"
                onClick={() => handleSubmit("approve")}
                disabled={isSubmitting}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-md shadow-emerald-950/40 active:scale-[0.99]"
              >
                {isSubmitting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                <span>确定 (批准执行)</span>
              </button>

              {/* 2. 补充 */}
              <button
                type="button"
                onClick={handleOpenSupplement}
                disabled={isSubmitting}
                className="flex items-center justify-center gap-1.5 py-2.5 px-3.5 rounded-xl text-xs font-medium bg-indigo-950/60 hover:bg-indigo-900/70 border border-indigo-500/40 text-indigo-300 hover:text-indigo-200 transition-all active:scale-[0.99]"
              >
                <span>💬 补充要求</span>
              </button>

              {/* 3. 取消 */}
              <button
                type="button"
                onClick={() => handleSubmit("reject")}
                disabled={isSubmitting}
                className="flex items-center justify-center gap-1.5 py-2.5 px-3.5 rounded-xl text-xs font-medium bg-rose-950/50 hover:bg-rose-900/60 border border-rose-800/60 text-rose-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-[0.99]"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>取消 (终止)</span>
              </button>
            </>
          ) : (
            <div className="w-full flex items-center gap-2.5">
              <button
                type="button"
                onClick={handleSupplementSubmit}
                disabled={isSubmitting || !customText.trim()}
                className="flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-md shadow-indigo-950/40 active:scale-[0.99]"
              >
                {isSubmitting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Check className="w-3.5 h-3.5" />
                )}
                <span>提交补充要求并执行</span>
              </button>

              <button
                type="button"
                onClick={() => setShowSupplement(false)}
                disabled={isSubmitting}
                className="py-2.5 px-4 rounded-xl text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 transition-all"
              >
                返回
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-950/40 border border-slate-800/80 px-3.5 py-2.5 rounded-xl">
          <Check className="w-4 h-4 text-emerald-400" />
          <span>{submittedChoice || "该人机审批步骤已处理完毕，流程已归档不可重复提交。"}</span>
        </div>
      )}
    </motion.div>
  );
});


HitlStep.displayName = "HitlStep";
