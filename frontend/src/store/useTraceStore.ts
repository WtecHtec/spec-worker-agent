import { create } from "zustand";

export type TraceDrawerTab = "gantt" | "files";

interface TraceState {
  isOpen: boolean;
  currentIdentifier: string | null;
  activeTab: TraceDrawerTab;

  openTrace: (identifier: string, tab?: TraceDrawerTab) => void;
  closeTrace: () => void;
  toggleTrace: (identifier?: string) => void;
  setActiveTab: (tab: TraceDrawerTab) => void;
}

export const useTraceStore = create<TraceState>((set) => ({
  isOpen: false,
  currentIdentifier: null,
  activeTab: "gantt",

  openTrace: (identifier: string, tab: TraceDrawerTab = "gantt") =>
    set({ isOpen: true, currentIdentifier: identifier, activeTab: tab }),

  closeTrace: () =>
    set({ isOpen: false }),

  toggleTrace: (identifier?: string) =>
    set((state) => ({
      isOpen: !state.isOpen,
      currentIdentifier: identifier ?? state.currentIdentifier,
    })),

  setActiveTab: (tab: TraceDrawerTab) =>
    set({ activeTab: tab }),
}));
