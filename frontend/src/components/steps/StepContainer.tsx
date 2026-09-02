"use client";

import React, { useEffect } from "react";
import { useTaskStore } from "@/store/useTaskStore";
import { useSessionStore } from "@/store/useSessionStore";
import { useTaskStream } from "@/hooks/useTaskStream";
import { useAuthStore } from "@/store/useAuthStore";
import { api } from "@/lib/api";
import { ThinkingStep } from "./ThinkingStep";
import { ToolCallStep } from "./ToolCallStep";
import { ToolResultStep } from "./ToolResultStep";
import { HitlStep } from "./HitlStep";
import { FinalStep } from "./FinalStep";
import { PlanStep } from "./PlanStep";
import { BrainCircuit, Sparkles, Loader2, AlertCircle } from "lucide-react";

interface StepContainerProps {
  taskId: string;
  isStreaming?: boolean;
}

export const StepContainer: React.FC<StepContainerProps> = ({
  taskId,
  isStreaming = false,
}) => {
  const token = useAuthStore((state) => state.token);
  const stepsRaw = useTaskStore((state) => state.stepsByTask[taskId]);
  const steps = stepsRaw || [];
  const setSteps = useTaskStore((state) => state.setSteps);
  const taskStatus = useTaskStore((state) => state.taskStatus[taskId]);
  const agentMsg = useSessionStore((state) => state.messages.find((m) => m.task_id === taskId));
  const taskError = agentMsg?.content?.error;

  const setHitl = useTaskStore((state) => state.setHitl);

  // 1. 如果有活跃任务且处于流式模式，开启 SSE 监听
  const { connectionStatus, retryAttempt } = useTaskStream(isStreaming ? taskId : null, {
    fromStep: steps.length > 0 ? steps[steps.length - 1].step_index : 0,
    token,
    enabled: isStreaming,
  });

  // 2. 初始挂载时拉取已有步骤（针对刷新重开会话）
  useEffect(() => {
    if (!taskId || !token || steps.length > 0) return;

    api.getTaskSteps(taskId, token)
      .then((data) => {
        if (data && data.length > 0) {
          setSteps(taskId, data);
        }
      })
      .catch((err) => console.error("Failed to load task steps:", err));
  }, [taskId, token, steps.length, setSteps]);

  // 1. 初始等待阶段的动态加载卡片（流式任务）
  if (steps.length === 0 && isStreaming) {
    return (
      <div className="flex items-center gap-2.5 py-3.5 px-4 my-2 rounded-xl bg-indigo-950/40 border border-indigo-500/25 text-xs text-indigo-300 backdrop-blur-md">
        <div className="relative flex items-center justify-center">
          <BrainCircuit className="w-4 h-4 text-indigo-400 animate-pulse" />
          <span className="absolute -top-0.5 -right-0.5 w-1.5 h-1.5 bg-indigo-400 rounded-full animate-ping" />
        </div>
        <span className="font-medium tracking-wide">Agent 正在深度分析指令与思考规划中...</span>
        <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin ml-auto" />
      </div>
    );
  }

  // 2. 展开历史任务但步骤尚未拉取完成时的加载卡片
  if (steps.length === 0 && !isStreaming) {
    return (
      <div className="flex items-center gap-2 py-2.5 px-3.5 my-1.5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs text-slate-400 font-mono">
        <Loader2 className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
        <span>正在读取任务历史执行记录与工具调用数据...</span>
      </div>
    );
  }

  const lastStep = steps[steps.length - 1];
  const hasFinished = lastStep?.type === "FINAL";

  // 提取最新的规划状态对象（顶部固定单张动态更新的计划卡片）
  const latestPlanStep = [...steps]
    .reverse()
    .find((s) => s.type === "PLAN_GENERATED" || s.type === "PLAN_UPDATED");

  // 过滤出要在时间轴中展示的操作过程（排除中间穿插的重复 PLAN 记录）
  const executionSteps = steps.filter(
    (s) => s.type !== "PLAN_GENERATED" && s.type !== "PLAN_UPDATED"
  );

  return (
    <div className="space-y-1.5 my-2">
      {/* 1. 顶部固定的动态规划看板 */}
      {latestPlanStep && (
        <PlanStep
          key="living-plan-card"
          stepIndex={latestPlanStep.step_index}
          goal={latestPlanStep.content.goal || "任务宏观规划"}
          steps={latestPlanStep.content.steps || []}
          isReplan={latestPlanStep.type === "PLAN_UPDATED"}
        />
      )}

      {/* 2. 中间与底部的执行步骤时间轴 */}
      {executionSteps.map((step, idx) => {
        const isLatest = idx === executionSteps.length - 1 && isStreaming;

        switch (step.type) {
          case "THINKING":
            return (
              <ThinkingStep
                key={step.step_index}
                stepIndex={step.step_index}
                text={step.content.text || ""}
                isStreaming={isLatest}
              />
            );
          case "TOOL_CALL":
            return (
              <ToolCallStep
                key={step.step_index}
                stepIndex={step.step_index}
                toolName={step.content.tool_name || step.content.name || step.content.tool || "工具调用"}
                args={step.content.arguments || step.content.args || {}}
              />
            );
          case "TOOL_RESULT":
            return (
              <ToolResultStep
                key={step.step_index}
                stepIndex={step.step_index}
                toolName={step.content.tool_name || step.content.name || step.content.tool || "工具结果"}
                output={step.content.output}
                durationMs={step.content.duration_ms}
              />
            );

          case "HITL_REQUEST":
            return (
              <HitlStep
                key={step.step_index}
                taskId={taskId}
                stepIndex={step.step_index}
                question={step.content.question || step.content.title || "需要人工决策"}
                detail={step.content.detail || step.content.step_detail}
                options={step.content.options}
              />
            );

          case "USER_DECISION":
            return (
              <div
                key={step.step_index}
                className="my-3 rounded-xl border border-indigo-500/30 bg-gradient-to-r from-indigo-950/40 to-slate-900/60 p-4 shadow-lg backdrop-blur-md"
              >
                <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-indigo-300">
                  <span className="p-1 rounded-md bg-indigo-500/20 border border-indigo-500/30">👤</span>
                  <span>人机协同决策反馈 (步骤 #{step.step_index})</span>
                </div>
                <div className="text-xs text-slate-200 whitespace-pre-wrap leading-relaxed font-mono bg-slate-950/60 p-3 rounded-lg border border-slate-800/80">
                  {step.content.text || `用户决策：${step.content.decision}`}
                </div>
              </div>
            );



          case "FINAL":
            return (
              <FinalStep
                key={step.step_index}
                text={step.content.text || ""}
                isStreaming={isLatest}
              />
            );
          default:
            return null;
        }
      })}

      {/* 任务失败且未产出正常 FINAL 步骤时的错误提示卡片 */}
      {taskStatus === "FAILED" && !hasFinished && (
        <div className="flex items-start gap-2.5 px-4 py-3 my-2 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs font-mono animate-in fade-in">
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <div className="font-semibold text-rose-200">❌ 任务执行异常中断</div>
            <p className="text-[11px] text-rose-400/90 mt-1 break-words">
              {taskError || "后台执行引擎或 LLM 服务调用发生未捕获异常，任务已主动终止。"}
            </p>
          </div>
        </div>
      )}

      {/* 步骤推进中的动态 Thinking / Processing 提示 */}
      {isStreaming && !hasFinished && taskStatus !== "FAILED" && taskStatus !== "CANCELLED" && (
        <div className="flex items-center gap-2 px-3 py-2 my-1.5 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-300 text-xs font-mono backdrop-blur-sm">
          <Sparkles className="w-3.5 h-3.5 text-indigo-400 animate-spin" />
          <span className="text-slate-400">
            {lastStep?.type === "TOOL_CALL"
              ? "沙箱正在执行工具调用并等待返回..."
              : lastStep?.type === "TOOL_RESULT"
              ? "Agent 正在综合分析观察结果，规划下一步..."
              : "Agent 正在进行下一步推理..."}
          </span>
          <span className="flex space-x-1 ml-auto">
            <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.3s]" />
            <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce [animation-delay:-0.15s]" />
            <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-bounce" />
          </span>
        </div>
      )}

      {connectionStatus === "reconnecting" && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-mono animate-pulse mt-2">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
          <span>网络波动，正在重试连接 (第 {retryAttempt} 次)...</span>
        </div>
      )}
    </div>
  );
};

