"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  Puzzle,
  Network,
  Plus,
  Trash2,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Terminal,
  Globe,
  Layers,
  Sparkles,
  ShieldCheck,
  Code2,
  BookOpen,
  RefreshCw,
  Wifi,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useAuthStore } from "@/store/useAuthStore";
import { API_BASE } from "@/lib/api";

interface McpServer {
  id: string;
  name: string;
  transport: "stdio" | "sse" | "streamable_http";
  server_url?: string;
  command?: string;
  args?: string[];
  namespace: string;
  description?: string;
  status: "active" | "failed" | "disabled";
  tools_count: number;
  tools?: { name: string; description?: string }[];
}

interface A2AAgent {
  id?: string;
  agent_id?: string;
  name: string;
  endpoint_url?: string;
  description: string;
  version?: string;
  skills: { name: string; description: string }[];
}

interface EcosystemModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const EcosystemModal: React.FC<EcosystemModalProps> = ({ isOpen, onClose }) => {
  const token = useAuthStore((state) => state.token);
  const [activeTab, setActiveTab] = useState<"mcp" | "a2a">("mcp");

  // MCP 状态
  const [mcpServers, setMcpServers] = useState<McpServer[]>([]);
  const [isLoadingMcp, setIsLoadingMcp] = useState(false);
  const [isAddingMcp, setIsAddingMcp] = useState(false);
  const [mcpName, setMcpName] = useState("");
  const [mcpTransport, setMcpTransport] = useState<"stdio" | "sse" | "streamable_http">("stdio");
  const [mcpCommand, setMcpCommand] = useState("python");
  const [mcpArgs, setMcpArgs] = useState("mcp-servers/sqlite_server/server.py");
  const [mcpUrl, setMcpUrl] = useState(`${API_BASE}/sse`);
  const [mcpNamespace, setMcpNamespace] = useState("custom");
  const [mcpDesc, setMcpDesc] = useState("");
  const [testResult, setTestResult] = useState<{
    success: boolean;
    connected: boolean;
    tools_count?: number;
    tools?: any[];
    error?: string;
  } | null>(null);
  const [isTesting, setIsTesting] = useState(false);

  // A2A 状态
  const [a2aAgents, setA2aAgents] = useState<A2AAgent[]>([]);
  const [isLoadingA2a, setIsLoadingA2a] = useState(false);
  const [isAddingA2a, setIsAddingA2a] = useState(false);
  const [a2aUrl, setA2aUrl] = useState("http://localhost:8090");
  const [a2aNamespace, setA2aNamespace] = useState("a2a");
  const [a2aDesc, setA2aDesc] = useState("");
  const [a2aTestResult, setA2aTestResult] = useState<{
    success: boolean;
    connected: boolean;
    agent_card?: { name: string; description: string; version?: string; skills: { name: string; description: string }[] };
    error?: string;
  } | null>(null);
  const [isTestingA2a, setIsTestingA2a] = useState(false);

  const getHeaders = () => ({
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  });

  const fetchMcpServers = async () => {
    setIsLoadingMcp(true);
    try {
      const res = await fetch(`${API_BASE}/api/ecosystem/mcp`, {
        headers: getHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        setMcpServers(data.servers || []);
      }
    } catch (e) {
      console.error("Failed to fetch MCP servers", e);
    } finally {
      setIsLoadingMcp(false);
    }
  };

  const fetchA2aAgents = async () => {
    setIsLoadingA2a(true);
    try {
      const res = await fetch(`${API_BASE}/api/ecosystem/a2a`, {
        headers: getHeaders(),
      });
      const data = await res.json();
      if (data.success) {
        setA2aAgents(data.agents || []);
      }
    } catch (e) {
      console.error("Failed to fetch A2A agents", e);
    } finally {
      setIsLoadingA2a(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchMcpServers();
      fetchA2aAgents();
    }
  }, [isOpen]);

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const payload: any = { transport: mcpTransport };
      if (mcpTransport === "stdio") {
        payload.command = mcpCommand;
        payload.args = mcpArgs ? mcpArgs.split(" ").filter(Boolean) : [];
      } else {
        payload.server_url = mcpUrl;
      }

      const res = await fetch(`${API_BASE}/api/ecosystem/mcp/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      setTestResult(data);
    } catch (e: any) {
      setTestResult({ success: false, connected: false, error: e.message });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveMcp = async () => {
    if (!mcpName.trim() || !mcpNamespace.trim()) {
      alert("请填写服务名称与命名空间");
      return;
    }

    try {
      const payload: any = {
        name: mcpName,
        transport: mcpTransport,
        namespace: mcpNamespace,
        description: mcpDesc,
      };
      if (mcpTransport === "stdio") {
        payload.command = mcpCommand;
        payload.args = mcpArgs ? mcpArgs.split(" ").filter(Boolean) : [];
      } else {
        payload.server_url = mcpUrl;
      }

      const res = await fetch(`${API_BASE}/api/ecosystem/mcp`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.success) {
        setIsAddingMcp(false);
        setTestResult(null);
        fetchMcpServers();
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("ecosystem_updated"));
        }
      }
    } catch (e: any) {
      alert(`保存失败: ${e.message}`);
    }
  };

  const handleDeleteMcp = async (id: string) => {
    if (!confirm("确定要卸载该 MCP 服务吗？")) return;
    try {
      await fetch(`${API_BASE}/api/ecosystem/mcp/${id}`, {
        method: "DELETE",
        headers: getHeaders(),
      });
      fetchMcpServers();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("ecosystem_updated"));
      }
    } catch (e: any) {
      alert(`删除失败: ${e.message}`);
    }
  };

  const handleTestA2aConnection = async () => {
    setIsTestingA2a(true);
    setA2aTestResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/ecosystem/a2a/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint_url: a2aUrl }),
      });
      const data = await res.json();
      setA2aTestResult(data);
    } catch (e: any) {
      setA2aTestResult({ success: false, connected: false, error: e.message });
    } finally {
      setIsTestingA2a(false);
    }
  };

  const handleSaveA2a = async () => {
    if (!a2aUrl.trim()) {
      alert("请填写 A2A 服务端点 URL");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/ecosystem/a2a`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          name: a2aTestResult?.agent_card?.name || "A2A Agent",
          endpoint_url: a2aUrl,
          namespace: a2aNamespace,
          description: a2aDesc || a2aTestResult?.agent_card?.description || "",
        }),
      });
      const data = await res.json();
      if (data.success) {
        setIsAddingA2a(false);
        setA2aTestResult(null);
        setA2aUrl("http://localhost:8090");
        fetchA2aAgents();
        if (typeof window !== "undefined") {
          window.dispatchEvent(new Event("ecosystem_updated"));
        }
      } else {
        alert(`添加失败: ${JSON.stringify(data)}`);
      }
    } catch (e: any) {
      alert(`保存失败: ${e.message}`);
    }
  };

  const handleDeleteA2a = async (id: string) => {
    if (!confirm("确定要移除该 A2A 智能体服务吗？")) return;
    try {
      await fetch(`${API_BASE}/api/ecosystem/a2a/${id}`, {
        method: "DELETE",
        headers: getHeaders(),
      });
      fetchA2aAgents();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event("ecosystem_updated"));
      }
    } catch (e: any) {
      alert(`删除失败: ${e.message}`);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        className="w-full max-w-3xl max-h-[85vh] flex flex-col bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden font-sans text-slate-200"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-900/40">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-600 text-white shadow-md shadow-indigo-950">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-100 tracking-tight">
                生态集成与多智能体配置中心
              </h2>
              <p className="text-xs text-slate-400">
                管理 MCP 外部生态协议与 Google A2A 专家智能体能力
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-2 px-6 pt-3 border-b border-slate-800/60 bg-slate-950">
          <button
            onClick={() => setActiveTab("mcp")}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === "mcp"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Puzzle className="w-4 h-4" />
            <span>MCP 外部协议服务 (stdio / SSE / HTTP)</span>
            <span className="px-1.5 py-0.2 text-[10px] rounded-full bg-slate-800 text-slate-300">
              {mcpServers.length}
            </span>
          </button>

          <button
            onClick={() => setActiveTab("a2a")}
            className={`flex items-center gap-2 pb-3 px-3 text-xs font-semibold border-b-2 transition-all ${
              activeTab === "a2a"
                ? "border-indigo-500 text-indigo-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            <Network className="w-4 h-4" />
            <span>Google A2A 专家智能体</span>
            <span className="px-1.5 py-0.2 text-[10px] rounded-full bg-slate-800 text-slate-300">
              {a2aAgents.length}
            </span>
          </button>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {activeTab === "mcp" ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-slate-300">已挂载 MCP 服务</h3>
                  <p className="text-[11px] text-slate-500">
                    支持三种官方传输模式：stdio 本地子进程、SSE 长连接、streamable_http 流式 HTTP
                  </p>
                </div>
                {!isAddingMcp && (
                  <button
                    onClick={() => setIsAddingMcp(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-sm"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>添加 MCP 服务</span>
                  </button>
                )}
              </div>

              {/* Add MCP Form */}
              {isAddingMcp && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-950/20 space-y-3"
                >
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                    <span className="text-xs font-bold text-indigo-300">配置新 MCP 服务</span>
                    <button
                      onClick={() => {
                        setIsAddingMcp(false);
                        setTestResult(null);
                      }}
                      className="text-slate-400 hover:text-slate-200 text-xs"
                    >
                      取消
                    </button>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-[11px] font-medium text-slate-400">服务名称</label>
                      <input
                        type="text"
                        value={mcpName}
                        onChange={(e) => setMcpName(e.target.value)}
                        placeholder="例如: SQLite Local DB"
                        className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                    <div>
                      <label className="text-[11px] font-medium text-slate-400">工具命名空间</label>
                      <input
                        type="text"
                        value={mcpNamespace}
                        onChange={(e) => setMcpNamespace(e.target.value)}
                        placeholder="例如: sqlite"
                        className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-[11px] font-medium text-slate-400">传输模式 (Transport)</label>
                    <div className="flex gap-2 mt-1">
                      {([
                        { key: "stdio", icon: <Terminal className="w-3.5 h-3.5" />, label: "stdio" },
                        { key: "sse", icon: <Globe className="w-3.5 h-3.5" />, label: "SSE" },
                        { key: "streamable_http", icon: <Globe className="w-3.5 h-3.5" />, label: "streamable_http" },
                      ] as const).map(({ key, icon, label }) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setMcpTransport(key)}
                          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-medium border transition-colors ${
                            mcpTransport === key
                              ? "bg-indigo-600/30 border-indigo-500 text-indigo-300"
                              : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          {icon}
                          <span>{label}</span>
                        </button>
                      ))}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-1.5">
                      {mcpTransport === "stdio" && "本地子进程模式，通过命令行启动 MCP Server"}
                      {mcpTransport === "sse" && "HTTP Server-Sent Events 长连接，适用于传统 SSE MCP Server"}
                      {mcpTransport === "streamable_http" && "官方最新推荐：HTTP POST 流式响应，兼容 ModelScope、Anthropic 等在线 MCP 平台"}
                    </p>
                  </div>

                  {mcpTransport === "stdio" ? (
                    <div className="grid grid-cols-3 gap-2">
                      <div>
                        <label className="text-[11px] font-medium text-slate-400">可执行命令</label>
                        <input
                          type="text"
                          value={mcpCommand}
                          onChange={(e) => setMcpCommand(e.target.value)}
                          placeholder="例如: python 或 uvx"
                          className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                        />
                      </div>
                      <div className="col-span-2">
                        <label className="text-[11px] font-medium text-slate-400">启动参数 (Args)</label>
                        <input
                          type="text"
                          value={mcpArgs}
                          onChange={(e) => setMcpArgs(e.target.value)}
                          placeholder="mcp-servers/sqlite_server/server.py"
                          className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                        />
                      </div>
                    </div>
                  ) : (
                    <div>
                      <label className="text-[11px] font-medium text-slate-400">
                        {mcpTransport === "streamable_http" ? "streamable_http 服务端点" : "SSE 服务端点"}
                      </label>
                      <input
                        type="text"
                        value={mcpUrl}
                        onChange={(e) => setMcpUrl(e.target.value)}
                        placeholder={
                          mcpTransport === "streamable_http"
                            ? "https://mcp.api-inference.modelscope.net/mcp"
                            : `${API_BASE}/sse`
                        }
                        className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                    </div>
                  )}

                  {/* Test Connection Output */}
                  {testResult && (
                    <div
                      className={`p-3 rounded-lg text-xs border ${
                        testResult.connected
                          ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
                          : "bg-rose-950/30 border-rose-500/40 text-rose-300"
                      }`}
                    >
                      <div className="flex items-center gap-2 font-semibold">
                        {testResult.connected ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <AlertCircle className="w-4 h-4 text-rose-400" />
                        )}
                        <span>
                          {testResult.connected
                            ? `连通性测试成功！发现 ${testResult.tools_count || 0} 个可用工具`
                            : `连接失败: ${testResult.error || "无法连接至指定 MCP 服务"}`}
                        </span>
                      </div>
                      {testResult.tools && testResult.tools.length > 0 && (
                        <div className="mt-2 pl-6 space-y-1">
                          {testResult.tools.map((t: any, idx: number) => (
                            <div key={idx} className="font-mono text-[11px] text-slate-300">
                              • <span className="font-semibold text-emerald-400">{t.name}</span>:{" "}
                              {t.description || "无描述"}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={handleTestConnection}
                      disabled={isTesting}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
                    >
                      {isTesting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                      <span>测试连通性</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleSaveMcp}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-sm"
                    >
                      <span>保存并挂载工具</span>
                    </button>
                  </div>
                </motion.div>
              )}

              {/* MCP Servers List */}
              {isLoadingMcp ? (
                <div className="py-8 text-center text-xs text-slate-500 animate-pulse">
                  加载 MCP 配置中...
                </div>
              ) : mcpServers.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-600">
                  暂无挂载的 MCP 服务，点击上方“添加 MCP 服务”接入外部生态。
                </div>
              ) : (
                <div className="space-y-2">
                  {mcpServers.map((server) => (
                    <div
                      key={server.id}
                      className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700/80 transition-all flex items-start justify-between gap-4"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-slate-200">{server.name}</span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                            {server.transport.toUpperCase()}
                          </span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            {server.tools_count} 个工具
                          </span>
                        </div>
                        <div className="text-[11px] font-mono text-slate-400">
                          {server.transport === "stdio"
                            ? `$ ${server.command} ${(server.args || []).join(" ")}`
                            : server.server_url}
                        </div>
                        {server.description && (
                          <div className="text-xs text-slate-400">{server.description}</div>
                        )}
                      </div>

                      <button
                        onClick={() => handleDeleteMcp(server.id)}
                        className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                        title="卸载服务"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-xs font-bold text-slate-300">Google A2A 专家智能体清单</h3>
                  <p className="text-[11px] text-slate-500">
                    基于 Google 官方 A2A SDK (<code className="font-mono">a2a.server.agent_execution.AgentExecutor</code>) 实现的外部专家服务
                  </p>
                </div>
                {!isAddingA2a && (
                  <button
                    onClick={() => setIsAddingA2a(true)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-sm"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>添加 A2A 服务</span>
                  </button>
                )}
              </div>

              {/* Add A2A Form */}
              {isAddingA2a && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 rounded-xl border border-indigo-500/30 bg-indigo-950/20 space-y-3"
                >
                  <div className="flex items-center justify-between pb-2 border-b border-slate-800/80">
                    <span className="text-xs font-bold text-indigo-300">连接 Google A2A 专家服务</span>
                    <button
                      onClick={() => { setIsAddingA2a(false); setA2aTestResult(null); }}
                      className="text-slate-400 hover:text-slate-200 text-xs"
                    >
                      取消
                    </button>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div className="col-span-2">
                      <label className="text-[11px] font-medium text-slate-400">A2A 服务端点 URL</label>
                      <input
                        type="text"
                        value={a2aUrl}
                        onChange={(e) => setA2aUrl(e.target.value)}
                        placeholder="http://localhost:8090"
                        className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
                      />
                      <p className="text-[10px] text-slate-500 mt-1">客户端将自动请求 <code className="font-mono">/.well-known/agent-card.json</code> 获取 AgentCard</p>
                    </div>
                    <div>
                      <label className="text-[11px] font-medium text-slate-400">工具命名空间</label>
                      <input
                        type="text"
                        value={a2aNamespace}
                        onChange={(e) => setA2aNamespace(e.target.value)}
                        placeholder="a2a"
                        className="w-full mt-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  {/* Test Result */}
                  {a2aTestResult && (
                    <div className={`p-3 rounded-lg text-xs border ${
                      a2aTestResult.connected
                        ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
                        : "bg-rose-950/30 border-rose-500/40 text-rose-300"
                    }`}>
                      <div className="flex items-center gap-2 font-semibold">
                        {a2aTestResult.connected ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        ) : (
                          <AlertCircle className="w-4 h-4 text-rose-400" />
                        )}
                        <span>
                          {a2aTestResult.connected
                            ? `AgentCard 获取成功：${a2aTestResult.agent_card?.name}`
                            : `连接失败: ${a2aTestResult.error || "无法获取 AgentCard"}`}
                        </span>
                      </div>
                      {a2aTestResult.agent_card && (
                        <div className="mt-2 space-y-1 pl-6">
                          <p className="text-slate-400">{a2aTestResult.agent_card.description}</p>
                          <div className="flex flex-wrap gap-1 pt-1">
                            {a2aTestResult.agent_card.skills.map((s, i) => (
                              <span key={i} className="px-2 py-0.5 rounded bg-indigo-900/40 text-indigo-300 border border-indigo-500/20 text-[10px]">
                                {s.name}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  <div className="flex items-center gap-2 pt-1">
                    <button
                      onClick={handleTestA2aConnection}
                      disabled={isTestingA2a || !a2aUrl.trim()}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-indigo-500/40 text-indigo-300 hover:bg-indigo-500/10 transition-colors disabled:opacity-50"
                    >
                      {isTestingA2a ? (
                        <><RefreshCw className="w-3.5 h-3.5 animate-spin" /><span>测试中...</span></>
                      ) : (
                        <><Wifi className="w-3.5 h-3.5" /><span>测试连通性</span></>
                      )}
                    </button>
                    <button
                      onClick={handleSaveA2a}
                      disabled={!a2aTestResult?.connected}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors shadow-sm disabled:opacity-40"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>保存并挂载</span>
                    </button>
                  </div>
                </motion.div>
              )}

              {isLoadingA2a ? (
                <div className="py-8 text-center text-xs text-slate-500 animate-pulse">加载 A2A 智能体清单中...</div>
              ) : (
                <div className="space-y-3">
                  {a2aAgents.map((agent, idx) => {
                    const agentId = agent.id || agent.agent_id || `agent-${idx}`;
                    const identifier = agent.agent_id || agent.name || agentId;
                    return (
                      <div
                        key={agentId}
                        className="p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 hover:border-slate-700/80 transition-all space-y-2.5"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="p-1.5 rounded-lg bg-indigo-600/15 text-indigo-400 border border-indigo-500/20">
                              {identifier.includes("researcher") ? (
                                <BookOpen className="w-4 h-4" />
                              ) : identifier.includes("coder") ? (
                                <Code2 className="w-4 h-4" />
                              ) : (
                                <ShieldCheck className="w-4 h-4" />
                              )}
                            </div>
                            <div>
                              <div className="text-xs font-bold text-slate-200">{agent.name}</div>
                              <div className="text-[10px] font-mono text-slate-500">{agent.endpoint_url || identifier}</div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="px-2 py-0.5 rounded-md text-[10px] bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">A2A Ready</span>
                            <button
                              onClick={() => handleDeleteA2a(agentId)}
                              className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                              title="移除服务"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                        <p className="text-xs text-slate-400 leading-relaxed">{agent.description}</p>
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {agent.skills.map((skill, si) => (
                            <span
                              key={si}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] bg-slate-800/80 text-slate-300 border border-slate-700/60"
                              title={skill.description}
                            >
                              <Layers className="w-3 h-3 text-indigo-400" />
                              <span>{skill.name}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
};
