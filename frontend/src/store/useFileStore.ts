import { create } from "zustand";
import { SessionFile, FileCategory } from "@/types/file";
import { api } from "@/lib/api";

interface FileState {
  files: SessionFile[];
  total: number;
  isLoading: boolean;
  activeCategory: FileCategory;
  isDrawerOpen: boolean;
  previewingFile: SessionFile | null;
  customDomain: string;

  // Actions
  fetchFiles: (sessionId: string, token: string, category?: FileCategory) => Promise<void>;
  setCategory: (category: FileCategory) => void;
  openDrawer: () => void;
  closeDrawer: () => void;
  toggleDrawer: () => void;
  openPreview: (file: SessionFile) => void;
  closePreview: () => void;
  deleteFile: (sessionId: string, fileId: string, token: string) => Promise<void>;
  setCustomDomain: (domain: string) => void;
  initSettings: () => void;
}

export const useFileStore = create<FileState>((set, get) => ({
  files: [],
  total: 0,
  isLoading: false,
  activeCategory: "all",
  isDrawerOpen: false,
  previewingFile: null,
  customDomain: "",

  initSettings: () => {
    if (typeof window !== "undefined") {
      const savedDomain = localStorage.getItem("agent_custom_file_domain") || "";
      set({ customDomain: savedDomain });
    }
  },

  setCustomDomain: (domain: string) => {
    if (typeof window !== "undefined") {
      localStorage.setItem("agent_custom_file_domain", domain);
    }
    set({ customDomain: domain });
  },

  setCategory: (category: FileCategory) => {
    set({ activeCategory: category });
  },

  openDrawer: () => set({ isDrawerOpen: true }),
  closeDrawer: () => set({ isDrawerOpen: false }),
  toggleDrawer: () => set((state) => ({ isDrawerOpen: !state.isDrawerOpen })),

  openPreview: (file: SessionFile) => set({ previewingFile: file }),
  closePreview: () => set({ previewingFile: null }),

  fetchFiles: async (sessionId: string, token: string, category?: FileCategory) => {
    const currentCat = category !== undefined ? category : get().activeCategory;
    set({ isLoading: true });
    try {
      const res = await api.getSessionFiles(sessionId, token, currentCat);
      set({ files: res.items || [], total: res.total || 0 });
    } catch (error) {
      console.error("Failed to fetch session files:", error);
    } finally {
      set({ isLoading: false });
    }
  },

  deleteFile: async (sessionId: string, fileId: string, token: string) => {
    try {
      await api.deleteFile(sessionId, fileId, token);
      set((state) => ({
        files: state.files.filter((f) => f.id !== fileId),
        total: Math.max(0, state.total - 1),
        previewingFile: state.previewingFile?.id === fileId ? null : state.previewingFile,
      }));
    } catch (error) {
      console.error("Failed to delete file:", error);
      throw error;
    }
  },
}));
