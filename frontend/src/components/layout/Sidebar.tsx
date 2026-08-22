"use client";

import React, { useState, useMemo } from "react";
import { Plus, MessageSquare, LogOut, User, Sparkles, Search, Trash2 } from "lucide-react";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuthStore } from "@/store/useAuthStore";
import { formatDate } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { EcosystemModal } from "@/components/settings/EcosystemModal";

export const Sidebar: React.FC = () => {
  const token = useAuthStore((state) => state.token);
  const userEmail = useAuthStore((state) => state.userEmail);
  const logout = useAuthStore((state) => state.logout);

  const sessions = useSessionStore((state) => state.sessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const selectSession = useSessionStore((state) => state.selectSession);
  const createSession = useSessionStore((state) => state.createSession);
  const isLoadingSessions = useSessionStore((state) => state.isLoadingSessions);

  const [searchQuery, setSearchQuery] = useState("");
  const [isEcosystemOpen, setIsEcosystemOpen] = useState(false);

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const q = searchQuery.toLowerCase();
    return sessions.filter((s) => (s.title || "未命名会话").toLowerCase().includes(q));
  }, [sessions, searchQuery]);

  const handleCreateSession = async () => {
    if (!token) return;
    try {
      await createSession(token);
    } catch (err: any) {
      alert(`创建会话失败: ${err.message}`);
    }
  };

  return (
    <aside className="w-72 h-full flex flex-col bg-slate-950 border-r border-slate-800/80 shrink-0">
      {/* 顶部 Logo & 新建按钮 */}
      <div className="p-4 border-b border-slate-800/80">
        <div className="flex items-center gap-2.5 mb-4 px-1">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-950">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-bold text-sm text-slate-100 tracking-tight">Antigravity Agent</h1>
            <span className="text-[10px] text-slate-500 font-mono">v1.0 (Full P0-P3)</span>
          </div>
        </div>

        <button
          onClick={handleCreateSession}
          className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-xs font-semibold bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white transition-all duration-200 shadow-md shadow-indigo-950/40 active:scale-[0.98]"
        >
          <Plus className="w-4 h-4" />
          <span>新建对话</span>
        </button>

        {/* 搜索框 */}
        <div className="mt-3 relative">
          <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="搜索会话..."
            className="w-full pl-8 pr-3 py-1.5 rounded-lg border border-slate-800/80 bg-slate-900/60 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500/50"
          />
        </div>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1 scrollbar-thin scrollbar-thumb-slate-800">
        <div className="px-3 py-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center justify-between">
          <span>历史会话</span>
          <span>{filteredSessions.length}</span>
        </div>

        {isLoadingSessions ? (
          <div className="px-3 py-4 text-xs text-slate-600 text-center animate-pulse">
            加载会话列表中...
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="px-3 py-8 text-center text-xs text-slate-600">
            {searchQuery ? "未找到匹配会话" : "暂无历史会话"}
          </div>
        ) : (
          <AnimatePresence>
            {filteredSessions.map((session) => {
              const isSelected = session.id === currentSessionId;
              return (
                <motion.button
                  key={session.id}
                  layout
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -8 }}
                  transition={{ duration: 0.2 }}
                  onClick={() => token && selectSession(session.id, token)}
                  className={`w-full flex items-start gap-3 p-3 rounded-xl text-left transition-all duration-200 ${
                    isSelected
                      ? "bg-indigo-600/15 border border-indigo-500/30 text-slate-100 shadow-sm"
                      : "hover:bg-slate-900/60 border border-transparent text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <MessageSquare className={`w-4 h-4 mt-0.5 shrink-0 ${isSelected ? "text-indigo-400" : "text-slate-500"}`} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium truncate">
                      {session.title || "未命名会话"}
                    </div>
                    <div className="flex items-center justify-between mt-1 text-[10px] text-slate-500">
                      <span>{session.message_count || 0} 条消息</span>
                      <span>{formatDate(session.created_at)}</span>
                    </div>
                  </div>
                </motion.button>
              );
            })}
          </AnimatePresence>
        )}
      </div>

      {/* 生态集成入口 */}
      <div className="px-3 py-2 border-t border-slate-800/80 bg-slate-950/40">
        <button
          onClick={() => setIsEcosystemOpen(true)}
          className="w-full flex items-center justify-between px-3 py-2 rounded-xl text-xs font-medium bg-slate-900/80 hover:bg-slate-800/80 border border-slate-800 text-slate-300 hover:text-white transition-all shadow-sm group"
        >
          <div className="flex items-center gap-2">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400 group-hover:scale-110 transition-transform" />
            <span>生态集成 (MCP / A2A)</span>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            配置
          </span>
        </button>
      </div>

      {/* 底部用户信息 & 登出 */}
      <div className="p-3 border-t border-slate-800/80 bg-slate-950/50">
        <div className="flex items-center justify-between p-2 rounded-xl bg-slate-900/80 border border-slate-800">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0">
              <User className="w-3.5 h-3.5" />
            </div>
            <div className="min-w-0">
              <div className="text-xs font-medium text-slate-200 truncate">
                {userEmail || "演示用户"}
              </div>
              <div className="text-[10px] text-slate-500 font-mono">Developer Plan</div>
            </div>
          </div>

          <button
            onClick={logout}
            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
            title="退出登录"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 生态配置弹窗 */}
      <EcosystemModal
        isOpen={isEcosystemOpen}
        onClose={() => setIsEcosystemOpen(false)}
      />
    </aside>
  );
};
