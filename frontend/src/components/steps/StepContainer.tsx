"use client";

import React, { useEffect } from "react";
import { useTaskStore } from "@/store/useTaskStore";
import { useTaskStream } from "@/hooks/useTaskStream";
import { useAuthStore } from "@/store/useAuthStore";
import { api } from "@/lib/api";
import { ThinkingStep } from "./ThinkingStep";
import { ToolCallStep } from "./ToolCallStep";
import { ToolResultStep } from "./ToolResultStep";
import { HitlStep } from "./HitlStep";
import { FinalStep } from "./FinalStep";

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

  if (steps.length === 0 && isStreaming) {
    return (
      <div className="flex items-center gap-2 py-3 text-xs text-slate-400 font-mono animate-pulse">
        <div className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
        <span>Agent 正在初始化执行环境...</span>
      </div>
    );
  }

  return (
    <div className="space-y-1 my-2">
      {steps.map((step, idx) => {
        const isLatest = idx === steps.length - 1 && isStreaming;

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
                toolName={step.content.tool_name || "unknown_tool"}
                args={step.content.arguments || {}}
              />
            );
          case "TOOL_RESULT":
            return (
              <ToolResultStep
                key={step.step_index}
                stepIndex={step.step_index}
                toolName={step.content.tool_name || "tool"}
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
                question={step.content.question || "需要人工决策"}
                options={step.content.options}
              />
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

      {connectionStatus === "reconnecting" && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-300 text-xs font-mono animate-pulse mt-2">
          <div className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
          <span>网络波动，正在重试连接 (第 {retryAttempt} 次)...</span>
        </div>
      )}
    </div>
  );
};
