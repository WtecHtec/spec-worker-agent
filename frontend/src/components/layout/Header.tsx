"use client";

import React, { useState, useEffect } from "react";
import { useSessionStore } from "@/store/useSessionStore";
import { Wifi, WifiOff, Activity, CheckCircle2 } from "lucide-react";

export const Header: React.FC = () => {
  const sessions = useSessionStore((state) => state.sessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const currentSession = sessions.find((s) => s.id === currentSessionId);

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
