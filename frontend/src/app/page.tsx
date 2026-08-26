"use client";

import React, { useEffect } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { AuthModal } from "@/components/auth/AuthModal";
import { ToastContainer } from "@/components/ui/ToastContainer";
import { FileListDrawer } from "@/components/files/FileListDrawer";
import { FilePreviewModal } from "@/components/files/FilePreviewModal";
import { useAuthStore } from "@/store/useAuthStore";
import { useSessionStore } from "@/store/useSessionStore";

export default function Home() {
  const token = useAuthStore((state) => state.token);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const isLoadingAuth = useAuthStore((state) => state.isLoading);
  const initAuth = useAuthStore((state) => state.initAuth);

  const fetchSessions = useSessionStore((state) => state.fetchSessions);

  useEffect(() => {
    initAuth();
  }, [initAuth]);

  useEffect(() => {
    if (token) {
      fetchSessions(token);
    }
  }, [token, fetchSessions]);

  if (isLoadingAuth) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-slate-950 text-slate-400 font-mono text-sm">
        <div className="flex items-center gap-3">
          <div className="w-2.5 h-2.5 rounded-full bg-indigo-500 animate-ping" />
          <span>正在启动 Antigravity 界面...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthModal />;
  }

  return (
    <main className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100 font-sans antialiased">
      <ToastContainer />
      <FileListDrawer />
      <FilePreviewModal />

      {/* 侧边栏 */}
      <Sidebar />

      {/* 主对话区 */}
      <div className="flex-1 flex flex-col h-full min-w-0">
        <Header />
        <ChatWindow />
      </div>
    </main>
  );
}
