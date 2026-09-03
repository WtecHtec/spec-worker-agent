"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Wrench, RefreshCw, ChevronDown, ChevronUp, Sparkles, Terminal, Box, Globe, Shield } from "lucide-react";
import { useAuthStore } from "@/store/useAuthStore";

interface ToolItem {
  name: string;
  description: string;
  category: "builtin" | "sandbox" | "mcp" | "a2a" | "browser";
}

interface ActiveToolsResponse {
  user_id: string;
  total_count: number;
  tools: ToolItem[];
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const categoryStyles: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  builtin: { label: "内置", color: "bg-blue-500/10 text-blue-400 border-blue-500/20", icon: <Sparkles className="w-3 h-3 mr-1" /> },
  sandbox: { label: "沙箱", color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20", icon: <Terminal className="w-3 h-3 mr-1" /> },
  mcp: { label: "MCP", color: "bg-purple-500/10 text-purple-400 border-purple-500/20", icon: <Box className="w-3 h-3 mr-1" /> },
  a2a: { label: "A2A", color: "bg-amber-500/10 text-amber-400 border-amber-500/20", icon: <Globe className="w-3 h-3 mr-1" /> },
  browser: { label: "浏览器", color: "bg-cyan-500/10 text-cyan-400 border-cyan-500/20", icon: <Shield className="w-3 h-3 mr-1" /> },
};

export const ActiveToolsBar: React.FC = () => {
  const token = useAuthStore((state) => state.token);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);

  const fetchActiveTools = useCallback(async () => {
    if (!token) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/ecosystem/active-tools`, {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
      });
      if (res.ok) {
        const data: ActiveToolsResponse = await res.json();
        setTools(data.tools || []);
      }
    } catch (err) {
      console.error("[ActiveToolsBar] Failed to load active tools:", err);
    } finally {
      setLoading(false);
    }
  }, [token]);

  // 初次加载及 Token 变更时拉取
  useEffect(() => {
    fetchActiveTools();
  }, [fetchActiveTools]);

  // 监听生态配置更新全局事件（当用户在 EcosystemModal 新增/启停/删除工具时触发）
  useEffect(() => {
    const handleEcosystemUpdated = () => {
      fetchActiveTools();
    };
    window.addEventListener("ecosystem_updated", handleEcosystemUpdated);
    return () => {
      window.removeEventListener("ecosystem_updated", handleEcosystemUpdated);
    };
  }, [fetchActiveTools]);

  if (tools.length === 0) return null;

  return (
    <div className="px-4 py-2 border-b border-white/5 bg-black/20 text-xs select-none">
      <div className="flex items-center justify-between">
        <div
          className="flex items-center space-x-2 cursor-pointer group"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <div className="flex items-center px-2 py-1 rounded bg-white/5 border border-white/10 group-hover:border-white/20 transition-colors">
            <Wrench className="w-3.5 h-3.5 text-blue-400 mr-1.5" />
            <span className="text-zinc-300 font-medium">可用工具</span>
            <span className="ml-1.5 px-1.5 py-0.2 rounded-full text-[10px] bg-blue-500/20 text-blue-300 border border-blue-500/30">
              {tools.length}
            </span>
          </div>

          {/* 简要滚动预览前 4 个工具 */}
          <div className="hidden sm:flex items-center space-x-1.5 overflow-hidden max-w-md">
            {tools.slice(0, 4).map((t) => {
              const meta = categoryStyles[t.category] || categoryStyles.builtin;
              return (
                <span
                  key={t.name}
                  className={`inline-flex items-center px-1.5 py-0.5 rounded text-[11px] border ${meta.color}`}
                  title={t.description}
                >
                  {meta.icon}
                  {t.name}
                </span>
              );
            })}
            {tools.length > 4 && (
              <span className="text-zinc-500 text-[11px]">+{tools.length - 4}...</span>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-1.5">
          <button
            onClick={fetchActiveTools}
            disabled={loading}
            className="p-1 text-zinc-400 hover:text-zinc-200 rounded hover:bg-white/5 transition-colors"
            title="刷新活跃工具列表"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          </button>
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="p-1 text-zinc-400 hover:text-zinc-200 rounded hover:bg-white/5 transition-colors"
          >
            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* 展开的完整工具面板 */}
      {isExpanded && (
        <div className="mt-2.5 pt-2.5 border-t border-white/5 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2 max-h-56 overflow-y-auto pr-1">
          {tools.map((t) => {
            const meta = categoryStyles[t.category] || categoryStyles.builtin;
            return (
              <div
                key={t.name}
                className="p-2 rounded bg-zinc-900/60 border border-white/5 hover:border-white/10 transition-colors"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-zinc-200 font-medium text-[11px] truncate">
                    {t.name}
                  </span>
                  <span className={`inline-flex items-center px-1 py-0.2 rounded text-[9px] border ${meta.color}`}>
                    {meta.label}
                  </span>
                </div>
                <p className="text-zinc-400 text-[10px] line-clamp-2 leading-relaxed">
                  {t.description}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
