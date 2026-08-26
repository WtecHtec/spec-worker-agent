"use client";

import React, { useState, useEffect } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { useFileStore } from "@/store/useFileStore";
import { useAuthStore } from "@/store/useAuthStore";
import { Wifi, WifiOff, Activity, FolderArchive } from "lucide-react";

export const Header: React.FC = () => {
  const sessions = useSessionStore((state) => state.sessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const currentSession = sessions.find((s) => s.id === currentSessionId);

  const token = useAuthStore((state) => state.token);
  const toggleDrawer = useFileStore((state) => state.toggleDrawer);
  const fileTotal = useFileStore((state) => state.total);
  const fetchFiles = useFileStore((state) => state.fetchFiles);

  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setIsOnline(navigator.onLine);

    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  useEffect(() => {
    if (currentSessionId && token) {
      fetchFiles(currentSessionId, token);
    }
  }, [currentSessionId, token, fetchFiles]);

  return (
    <header className="h-14 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-xl flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-3">
        <h2 className="text-sm font-semibold text-slate-100 truncate max-w-sm">
          {currentSession?.title || "选择或新建会话"}
        </h2>
        {currentSession && (
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-900 border border-slate-800 text-slate-400 font-mono">
            {currentSession.message_count || 0} msgs
          </span>
        )}
      </div>

      <div className="flex items-center gap-3">
        {/* 会话产出文件抽屉快捷入口 */}
        {currentSessionId && (
          <button
            onClick={toggleDrawer}
            title="查看会话产出文件"
            className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white text-xs font-medium transition-all group shadow-sm"
          >
            <FolderArchive className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
            <span>产出文件</span>
            {fileTotal > 0 && (
              <span className="ml-1 px-1.5 py-0.2 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-300 text-[10px] font-mono font-bold">
                {fileTotal}
              </span>
            )}
          </button>
        )}

        {/* 网络状态指示器 */}
        {isOnline ? (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[11px] font-mono font-medium">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <Wifi className="w-3 h-3" />
            <span>在线</span>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-rose-500/10 border border-rose-500/20 text-rose-400 text-[11px] font-mono font-medium">
            <WifiOff className="w-3 h-3" />
            <span>网络断开</span>
          </div>
        )}

        <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-slate-400 text-[11px] font-mono">
          <Activity className="w-3 h-3 text-indigo-400" />
          <span>API 8000</span>
        </div>
      </div>
    </header>
  );
};
