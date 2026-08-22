import { create } from "zustand";
import { api } from "@/lib/api";

interface AuthState {
  token: string | null;
  userEmail: string | null;
  userId: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (email: string, pass: string) => Promise<void>;
  register: (email: string, pass: string, name?: string) => Promise<void>;
  logout: () => void;
  initAuth: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  userEmail: null,
  userId: null,
  isAuthenticated: false,
  isLoading: true,

  initAuth: () => {
    if (typeof window === "undefined") return;
    const token = localStorage.getItem("agent_token");
    const userEmail = localStorage.getItem("agent_email");
    const userId = localStorage.getItem("agent_user_id");

    window.addEventListener("agent_auth_expired", () => {
      set({
        token: null,
        userEmail: null,
        userId: null,
        isAuthenticated: false,
      });
    });

    if (token) {
      set({
        token,
        userEmail,
        userId,
        isAuthenticated: true,
        isLoading: false,
      });
    } else {
      set({ isLoading: false });
    }
  },

  login: async (email, password) => {
    const res = await api.login({ email, password });
    localStorage.setItem("agent_token", res.access_token);
    localStorage.setItem("agent_email", email);
    localStorage.setItem("agent_user_id", res.user_id);
    set({
      token: res.access_token,
      userEmail: email,
      userId: res.user_id,
      isAuthenticated: true,
    });
  },

  register: async (email, password, display_name) => {
    const res = await api.register({ email, password, display_name });
    localStorage.setItem("agent_token", res.access_token);
    localStorage.setItem("agent_email", email);
    localStorage.setItem("agent_user_id", res.user_id);
    set({
      token: res.access_token,
      userEmail: email,
      userId: res.user_id,
      isAuthenticated: true,
    });
  },

  logout: () => {
    localStorage.removeItem("agent_token");
    localStorage.removeItem("agent_email");
    localStorage.removeItem("agent_user_id");
    set({
      token: null,
      userEmail: null,
      userId: null,
      isAuthenticated: false,
    });
  },
}));
