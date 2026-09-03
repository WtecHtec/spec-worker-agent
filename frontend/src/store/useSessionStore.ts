import { create } from "zustand";
import { api } from "@/lib/api";
import { Session, Message } from "@/types";

interface SessionState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Message[];
  currentRunId: string | null;
  isLoadingSessions: boolean;
  isLoadingMessages: boolean;
  isSending: boolean;
  error: string | null;

  setCurrentRunId: (runId: string | null) => void;
  fetchSessions: (token: string) => Promise<void>;
  createSession: (token: string, title?: string) => Promise<Session>;
  deleteSession: (sessionId: string, token: string) => Promise<void>;
  selectSession: (sessionId: string, token: string) => Promise<void>;

  fetchMessages: (sessionId: string, token: string, silent?: boolean) => Promise<void>;
  sendMessage: (content: string, token: string) => Promise<{ taskId: string; messageId: string }>;
  appendMessage: (message: Message) => void;
  updateMessage: (messageId: string, updates: Partial<Message>) => void;
  updateMessageByTaskId: (taskId: string, updates: Partial<Message>) => void;
}

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  currentRunId: null,
  messages: [],
  isLoadingSessions: false,
  isLoadingMessages: false,
  isSending: false,
  error: null,

  setCurrentRunId: (runId: string | null) => set({ currentRunId: runId }),

  fetchSessions: async (token: string) => {
    set({ isLoadingSessions: true, error: null });
    try {
      const data = await api.getSessions(token);
      set({ sessions: data, isLoadingSessions: false });
      // 如果没有选中的会话，默认选第一个
      if (data.length > 0 && !get().currentSessionId) {
        get().selectSession(data[0].id, token);
      }
    } catch (err: any) {
      set({ isLoadingSessions: false, error: err.message });
    }
  },

  createSession: async (token: string, title?: string) => {
    const defaultTitle = title || `会话 ${new Date().toLocaleDateString()}`;
    const newSession = await api.createSession(defaultTitle, token);
    set((state) => ({
      sessions: [newSession, ...state.sessions],
      currentSessionId: newSession.id,
      messages: [],
    }));
    return newSession;
  },

  deleteSession: async (sessionId: string, token: string) => {
    await api.deleteSession(sessionId, token);
    const remaining = get().sessions.filter((s) => s.id !== sessionId);
    const isCurrent = get().currentSessionId === sessionId;
    const nextSessionId = isCurrent ? (remaining[0]?.id || null) : get().currentSessionId;
    
    set({
      sessions: remaining,
      currentSessionId: nextSessionId,
      messages: isCurrent ? [] : get().messages,
    });

    if (isCurrent && nextSessionId) {
      await get().selectSession(nextSessionId, token);
    }
  },

  selectSession: async (sessionId: string, token: string) => {

    set({ currentSessionId: sessionId, messages: [] });
    await get().fetchMessages(sessionId, token);
  },

  fetchMessages: async (sessionId: string, token: string, silent: boolean = false) => {
    if (!silent) {
      set({ isLoadingMessages: true, error: null });
    }
    try {
      const data = await api.getSessionMessages(sessionId, token);
      set({ messages: data, isLoadingMessages: false });
    } catch (err: any) {
      set({ isLoadingMessages: false, error: err.message });
    }
  },

  sendMessage: async (content: string, token: string) => {
    let sessionId = get().currentSessionId;
    if (!sessionId) {
      const autoTitle = content.length > 24 ? `${content.slice(0, 24)}...` : content;
      const created = await get().createSession(token, autoTitle);
      sessionId = created.id;
    }

    set({ isSending: true, error: null });

    try {
      const res = await api.sendMessage(sessionId, content, token);

      // 静默刷新消息列表，避免 isLoadingMessages 清空当前 DOM 导致页面跳顶
      await get().fetchMessages(sessionId, token, true);
      set({ isSending: false });

      return { taskId: res.task_id, messageId: res.message_id };
    } catch (err: any) {
      set({ isSending: false, error: err.message });
      throw err;
    }
  },


  appendMessage: (message: Message) => {
    set((state) => ({
      messages: [...state.messages, message],
    }));
  },

  updateMessage: (messageId: string, updates: Partial<Message>) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId ? { ...m, ...updates, content: { ...m.content, ...updates.content } } : m
      ),
    }));
  },

  updateMessageByTaskId: (taskId: string, updates: Partial<Message>) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.task_id === taskId ? { ...m, ...updates, content: { ...m.content, ...updates.content } } : m
      ),
    }));
  },
}));
