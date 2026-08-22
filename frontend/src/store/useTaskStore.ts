import { create } from "zustand";
import { TaskStep, HitlRequest } from "@/types";

interface TaskState {
  stepsByTask: Record<string, TaskStep[]>;
  activeHitlByTask: Record<string, HitlRequest | null>;
  taskStatus: Record<string, string>;

  setSteps: (taskId: string, steps: TaskStep[]) => void;
  addStep: (taskId: string, step: TaskStep) => void;
  setHitl: (taskId: string, hitl: HitlRequest | null) => void;
  setTaskStatus: (taskId: string, status: string) => void;
  clearTask: (taskId: string) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  stepsByTask: {},
  activeHitlByTask: {},
  taskStatus: {},

  setSteps: (taskId, steps) => {
    // 按 step_index 排序并去重
    const map = new Map<number, TaskStep>();
    steps.forEach((s) => map.set(s.step_index, s));
    const sorted = Array.from(map.values()).sort((a, b) => a.step_index - b.step_index);

    set((state) => ({
      stepsByTask: {
        ...state.stepsByTask,
        [taskId]: sorted,
      },
    }));
  },

  addStep: (taskId, step) => {
    set((state) => {
      const current = state.stepsByTask[taskId] || [];
      const map = new Map<number, TaskStep>();
      current.forEach((s) => map.set(s.step_index, s));
      map.set(step.step_index, step);
      const sorted = Array.from(map.values()).sort((a, b) => a.step_index - b.step_index);

      return {
        stepsByTask: {
          ...state.stepsByTask,
          [taskId]: sorted,
        },
      };
    });
  },

  setHitl: (taskId, hitl) => {
    set((state) => ({
      activeHitlByTask: {
        ...state.activeHitlByTask,
        [taskId]: hitl,
      },
    }));
  },

  setTaskStatus: (taskId, status) => {
    set((state) => ({
      taskStatus: {
        ...state.taskStatus,
        [taskId]: status,
      },
    }));
  },

  clearTask: (taskId) => {
    set((state) => {
      const newSteps = { ...state.stepsByTask };
      const newHitl = { ...state.activeHitlByTask };
      const newStatus = { ...state.taskStatus };
      delete newSteps[taskId];
      delete newHitl[taskId];
      delete newStatus[taskId];
      return {
        stepsByTask: newSteps,
        activeHitlByTask: newHitl,
        taskStatus: newStatus,
      };
    });
  },
}));
