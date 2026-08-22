import { create } from "zustand";

export interface Toast {
  id: string;
  type: "info" | "success" | "warning" | "error";
  title?: string;
  message: string;
  duration?: number;
}

interface ToastState {
  toasts: Toast[];
  addToast: (toast: Omit<Toast, "id">) => void;
  removeToast: (id: string) => void;
}

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  addToast: (toast) => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: Toast = { ...toast, id, duration: toast.duration || 4000 };

    set((state) => ({ toasts: [...state.toasts, newToast] }));

    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    }, newToast.duration);
  },

  removeToast: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },
}));

export const toast = {
  info: (message: string, title?: string) => useToastStore.getState().addToast({ type: "info", message, title }),
  success: (message: string, title?: string) => useToastStore.getState().addToast({ type: "success", message, title }),
  warning: (message: string, title?: string) => useToastStore.getState().addToast({ type: "warning", message, title }),
  error: (message: string, title?: string) => useToastStore.getState().addToast({ type: "error", message, title }),
};
