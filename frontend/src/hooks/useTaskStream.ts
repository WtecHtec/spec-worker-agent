import { useEffect, useRef, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useTaskStore } from "@/store/useTaskStore";
import { useSessionStore } from "@/store/useSessionStore";
import { useToastStore, toast } from "@/store/useToastStore";
import { TaskStep } from "@/types";

export type StreamConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "completed"
  | "disconnected";

interface UseTaskStreamOptions {
  fromStep?: number;
  token?: string | null;
  enabled?: boolean;
}

/**
 * P2 增强版 Task SSE 实时流式接收 Hook
 * 具备断线智能重试（指数退避）、最新 Step 增量续传与连接状态感知
 */
export function useTaskStream(
  taskId: string | null,
  options: UseTaskStreamOptions = {}
) {
  const { fromStep = 0, token, enabled = true } = options;

  const [connectionStatus, setConnectionStatus] = useState<StreamConnectionStatus>("idle");
  const [retryAttempt, setRetryAttempt] = useState<number>(0);

  const eventSourceRef = useRef<EventSource | null>(null);
  const isTerminatedRef = useRef<boolean>(false);
  const latestStepRef = useRef<number>(fromStep);
  const retryCountRef = useRef<number>(0);
  const maxRetries = 6;

  const addStep = useTaskStore((state) => state.addStep);
  const setHitl = useTaskStore((state) => state.setHitl);
  const setTaskStatus = useTaskStore((state) => state.setTaskStatus);
  const updateMessageByTaskId = useSessionStore((state) => state.updateMessageByTaskId);

  // 保持 latestStepRef 最新的 step_index
  useEffect(() => {
    if (fromStep > latestStepRef.current) {
      latestStepRef.current = fromStep;
    }
  }, [fromStep]);

  const connectStream = useCallback((startFrom: number) => {
    if (!taskId || isTerminatedRef.current) return;

    if (retryCountRef.current > 0) {
      setConnectionStatus("reconnecting");
    } else {
      setConnectionStatus("connecting");
    }

    const streamUrl = api.getStreamUrl(taskId, startFrom, token);
    const es = new EventSource(streamUrl);
    eventSourceRef.current = es;

    es.onopen = () => {
      setConnectionStatus("connected");
      retryCountRef.current = 0;
      setRetryAttempt(0);
      setTaskStatus(taskId, "RUNNING");
    };

    // 1. 监听新步骤
    es.addEventListener("new_step", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        const step: TaskStep = {
          step_index: data.step_index,
          type: data.step_type,
          content: data.content,
          created_at: data.created_at || new Date().toISOString(),
        };

        if (step.step_index > latestStepRef.current) {
          latestStepRef.current = step.step_index;
        }

        addStep(taskId, step);

        if (step.type === "FINAL" && step.content?.text) {
          updateMessageByTaskId(taskId, {
            content: { text: step.content.text, task_status: "RUNNING" },
          });
        }
      } catch (err) {
        console.error("Failed to parse new_step event:", err);
      }
    });

    // 2. 监听 HITL 请求创建
    es.addEventListener("hitl_created", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        setHitl(taskId, {
          id: data.hitl_id,
          task_id: taskId,
          step_index: data.step_index || latestStepRef.current,
          type: "choice",
          question: data.question,
          options: data.options,
          status: "PENDING",
          expires_at: "",
        });
        setTaskStatus(taskId, "WAITING_HUMAN");
        updateMessageByTaskId(taskId, {
          content: { task_status: "WAITING_HUMAN", hitl_question: data.question },
        });
      } catch (err) {
        console.error("Failed to parse hitl_created event:", err);
      }
    });

    // 3. 监听任务完成
    es.addEventListener("task_completed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        isTerminatedRef.current = true;
        setConnectionStatus("completed");
        setTaskStatus(taskId, "COMPLETED");
        const summary = data?.result?.summary || "任务已顺利完成。";
        updateMessageByTaskId(taskId, {
          status: "done",
          content: { task_status: "COMPLETED", summary },
        });
        es.close();
      } catch (err) {
        console.error("Failed to parse task_completed event:", err);
      }
    });

    // 4. 监听任务失败
    es.addEventListener("task_failed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        isTerminatedRef.current = true;
        setConnectionStatus("completed");
        setTaskStatus(taskId, "FAILED");
        updateMessageByTaskId(taskId, {
          status: "failed",
          content: { task_status: "FAILED", error: data?.error },
        });
        es.close();
      } catch (err) {
        console.error("Failed to parse task_failed event:", err);
      }
    });

    // 5. 监听任务取消
    es.addEventListener("task_cancelled", () => {
      isTerminatedRef.current = true;
      setConnectionStatus("completed");
      setTaskStatus(taskId, "CANCELLED");
      updateMessageByTaskId(taskId, {
        status: "failed",
        content: { text: "任务已被取消。", task_status: "CANCELLED" },
      });
      es.close();
    });

    // 6. 异常与断线重试（指数退避）
    es.onerror = () => {
      es.close();
      if (!isTerminatedRef.current && retryCountRef.current < maxRetries) {
        setConnectionStatus("reconnecting");
        const delay = Math.min(1000 * 2 ** retryCountRef.current, 15000);
        retryCountRef.current += 1;
        setRetryAttempt(retryCountRef.current);

        setTimeout(() => {
          if (!isTerminatedRef.current) {
            connectStream(latestStepRef.current);
          }
        }, delay);
      } else {
        setConnectionStatus("disconnected");
        if (!isTerminatedRef.current) {
          toast.error("实时步骤流连接中断，请检查网络或刷新页面", "SSE 连接失败");
        }
      }
    };
  }, [taskId, addStep, setHitl, setTaskStatus, updateMessageByTaskId]);

  useEffect(() => {
    if (!taskId || !enabled) return;

    isTerminatedRef.current = false;
    retryCountRef.current = 0;
    setRetryAttempt(0);
    connectStream(latestStepRef.current || fromStep);

    return () => {
      isTerminatedRef.current = true;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [taskId, enabled, connectStream]);

  return {
    connectionStatus,
    retryAttempt,
    closeStream: () => {
      isTerminatedRef.current = true;
      eventSourceRef.current?.close();
    },
  };
}
