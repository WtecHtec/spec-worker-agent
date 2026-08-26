import { create } from "zustand";

interface OpenPreviewParams {
  title?: string;
  fileName?: string;
  previewUrl?: string;
  sessionId?: string;
  isWebContainer?: boolean;
}

interface PreviewState {
  isOpen: boolean;
  width: number; // 面板宽度，默认 560px
  title: string;
  fileName: string;
  previewUrl: string;
  sessionId: string | null;
  isWebContainer: boolean;

  openPreview: (params?: OpenPreviewParams) => void;
  closePreview: () => void;
  togglePreview: () => void;
  setWidth: (width: number) => void;
  switchTarget: (target: {
    title: string;
    fileName: string;
    previewUrl: string;
    isWebContainer: boolean;
  }) => void;
}

export const usePreviewStore = create<PreviewState>((set, get) => ({
  isOpen: false,
  width: 560,
  title: "Web 页面预览",
  fileName: "index.html",
  previewUrl: "",
  sessionId: null,
  isWebContainer: false,

  openPreview: (params) => {
    set((state) => ({
      isOpen: true,
      title: params?.title || state.title,
      fileName: params?.fileName || state.fileName,
      previewUrl: params?.previewUrl !== undefined ? params.previewUrl : state.previewUrl,
      sessionId: params?.sessionId !== undefined ? params.sessionId : state.sessionId,
      isWebContainer: params?.isWebContainer !== undefined ? params.isWebContainer : state.isWebContainer,
    }));
  },

  closePreview: () => {
    set({ isOpen: false });
  },

  togglePreview: () => {
    set((state) => ({ isOpen: !state.isOpen }));
  },

  switchTarget: (target) => {
    set({
      title: target.title,
      fileName: target.fileName,
      previewUrl: target.previewUrl,
      isWebContainer: target.isWebContainer,
    });
  },

  setWidth: (width: number) => {
    // 限制拖拽拉伸最小 360px，最大 1200px
    const clamped = Math.min(Math.max(width, 360), 1200);
    set({ width: clamped });
  },
}));
