"use client";

import React, { useState, useEffect, useMemo } from "react";
import dynamic from "next/dynamic";
import {
  X,
  Clock,
  Coins,
  Cpu,
  Wrench,
  Calendar,
  CheckCircle2,
  AlertCircle,
  ChevronRight,
  Layers,
  Sparkles,
  FileText,
  Terminal,
  Copy,
  Check,
  Loader2,
  RefreshCw,
  FolderArchive,
  Globe,
  FileCode,
  Image as ImageIcon,
  Download,
  Eye,
  Activity,
} from "lucide-react";
import { apiRequest, SANDBOX_BASE } from "@/lib/api";
import { useAuthStore } from "@/store/useAuthStore";
import { useTraceStore, TraceDrawerTab } from "@/store/useTraceStore";
import { useFileStore } from "@/store/useFileStore";
import { useSessionStore } from "@/store/useSessionStore";
import { SessionFile, FileCategory } from "@/types/file";

const DynamicVChartGantt = dynamic(() => import("./VChartGantt"), {
  ssr: false,
  loading: () => (
    <div className="h-44 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col items-center justify-center text-slate-500 font-mono text-xs gap-2">
      <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      <span>正在按需加载 VChart 甘特图引擎...</span>
    </div>
  ),
});

export interface SpanDetail {
  id: string;
  trace_id: string;
  parent_span_id?: string | null;
  name: string;
  type: string; // "node" | "llm" | "tool"
  status: string; // "success" | "error"
  start_time: string;
  end_time: string;
  duration_ms: number;
  tokens?: {
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    prompt?: number;
    completion?: number;
    total?: number;
  } | null;
  input_data?: any;
  output_data?: any;
  error_message?: string | null;
  reported_at: string;
}

export interface TraceDetail {
  id: string;
  session_id: string;
  message_id?: string | null;
  run_id: string;
  status: string;
  total_duration_ms: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  model_name?: string | null;
  tool_calls_count: number;
  reported_at: string;
  created_at: string;
  spans: SpanDetail[];
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export const TraceDrawer: React.FC = () => {
  const isOpen = useTraceStore((state) => state.isOpen);
  const identifier = useTraceStore((state) => state.currentIdentifier);
  const activeTab = useTraceStore((state) => state.activeTab);
  const closeTrace = useTraceStore((state) => state.closeTrace);
  const setActiveTab = useTraceStore((state) => state.setActiveTab);

  const token = useAuthStore((state) => state.token);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const sessionFiles = useFileStore((state) => state.files);
  const openFilePreview = useFileStore((state) => state.openPreview);
  const fetchSessionFiles = useFileStore((state) => state.fetchFiles);

  const [loading, setLoading] = useState(false);
  const [trace, setTrace] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 加载 Trace 数据
  const fetchTraceData = () => {
    if (!identifier) return;
    setLoading(true);
    setError(null);

    apiRequest<TraceDetail>(`/traces/${identifier}`, { token })
      .then((data) => {
        setTrace(data);
        if (data.spans && data.spans.length > 0) {
          setSelectedSpanId(data.spans[0].id);
        }
      })
      .catch((err) => {
        console.error("Failed to fetch trace:", err);
        setError("未找到该会话/消息的 Trace 执行历程日志");
      })
      .finally(() => {
        setLoading(false);
      });
  };

  useEffect(() => {
    if (isOpen && identifier) {
      fetchTraceData();
    }
    if (isOpen && currentSessionId && token) {
      fetchSessionFiles(currentSessionId, token);
    }
  }, [isOpen, identifier, currentSessionId, token]);

  const selectedSpan = trace?.spans?.find((s) => s.id === selectedSpanId);

  const handleCopyJson = () => {
    if (!trace) return;
    navigator.clipboard.writeText(JSON.stringify(trace, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // 筛选与本轮或本次任务相关的产出文件
  const relevantFiles = useMemo(() => {
    if (!sessionFiles || sessionFiles.length === 0) return [];
    return sessionFiles;
  }, [sessionFiles]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/60 backdrop-blur-sm animate-in fade-in duration-200">
      {/* 点击遮罩关闭 */}
      <div className="absolute inset-0" onClick={closeTrace} />

      {/* 右侧滑出面板（参考 FileListDrawer 的尺寸与动画） */}
      <div className="relative w-full max-w-2xl h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-300 text-slate-200">
        {/* Header 顶栏 */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/70 shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-100">
                  执行历程与甘特图
                </h3>
                {trace && (
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-bold border ${trace.status === "success"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        : "bg-rose-500/10 text-rose-400 border-rose-500/20"
                      }`}
                  >
                    {trace.status.toUpperCase()}
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-400 font-mono mt-0.5 truncate max-w-sm">
                ID: {identifier || currentSessionId || "trace"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            {trace && (
              <button
                onClick={handleCopyJson}
                title="复制完整 Trace JSON"
                className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-700/60 transition-colors"
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
                <span>{copied ? "已复制" : "JSON"}</span>
              </button>
            )}

            <button
              onClick={fetchTraceData}
              title="刷新 Trace 数据"
              className={`p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors ${loading ? "animate-spin text-indigo-400" : ""
                }`}
            >
              <RefreshCw className="w-4 h-4" />
            </button>

            <button
              onClick={closeTrace}
              title="关闭抽屉"
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 交互切换 Tabs：时序甘特图 / 产出文件 */}
        <div className="px-6 pt-3 pb-2 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab("gantt")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === "gantt"
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent"
                }`}
            >
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              <span>时序甘特图 (Gantt)</span>
              {trace?.spans && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-slate-800 text-slate-300">
                  {trace.spans.length}
                </span>
              )}
            </button>

            <button
              onClick={() => setActiveTab("files")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${activeTab === "files"
                  ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent"
                }`}
            >
              <FolderArchive className="w-3.5 h-3.5 text-indigo-400" />
              <span>参考产出文件</span>
              {relevantFiles.length > 0 && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded-full bg-indigo-500/20 text-indigo-300 font-bold">
                  {relevantFiles.length}
                </span>
              )}
            </button>
          </div>

          <span className="text-[11px] text-slate-400 font-mono hidden sm:inline">
            {activeTab === "gantt" ? "点击甘特条联动查看单步详情" : "会话中生成与引用的文件"}
          </span>
        </div>

        {/* 内容区 */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading && (
            <div className="flex flex-col items-center justify-center h-64 text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-500 mb-3" />
              <p className="text-sm">正在加载 Trace 执行历程与甘特图数据...</p>
            </div>
          )}

          {error && !loading && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm flex items-center gap-3">
              <AlertCircle className="w-5 h-5 shrink-0" />
              <p>{error}</p>
            </div>
          )}

          {/* TAB 1: 甘特图历程 */}
          {activeTab === "gantt" && trace && !loading && (
            <>
              {/* KPI 关键指标卡片 */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Clock className="w-3.5 h-3.5 text-indigo-400" />
                    <span>总执行耗时</span>
                  </div>
                  <div className="text-lg font-bold text-slate-100 font-mono">
                    {(trace.total_duration_ms / 1000).toFixed(2)}s
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {trace.total_duration_ms} ms
                  </span>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Coins className="w-3.5 h-3.5 text-amber-400" />
                    <span>消耗 Token</span>
                  </div>
                  <div className="text-lg font-bold text-slate-100 font-mono">
                    {trace.total_tokens.toLocaleString()}
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    入: {trace.prompt_tokens} / 出: {trace.completion_tokens}
                  </span>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Wrench className="w-3.5 h-3.5 text-orange-400" />
                    <span>工具调用</span>
                  </div>
                  <div className="text-lg font-bold text-slate-100 font-mono">
                    {trace.tool_calls_count} 次
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {trace.model_name || "deepseek-chat"}
                  </span>
                </div>

                <div className="p-3.5 rounded-xl bg-slate-950/70 border border-slate-800 flex flex-col justify-between">
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                    <Calendar className="w-3.5 h-3.5 text-emerald-400" />
                    <span>上报时间 (东八区)</span>
                  </div>
                  <div
                    className="text-xs font-semibold text-slate-200 font-mono truncate"
                    title={trace.reported_at}
                  >
                    {trace.reported_at
                      ? trace.reported_at.includes("T")
                        ? trace.reported_at.split("T")[1]?.split("+")[0]?.split(".")[0]
                        : trace.reported_at.split(" ")[1] || trace.reported_at
                      : ""}
                  </div>
                  <span className="text-[10px] text-slate-500 font-mono">
                    {trace.reported_at
                      ? trace.reported_at.includes("T")
                        ? trace.reported_at.split("T")[0]
                        : trace.reported_at.split(" ")[0] || "UTC+8"
                      : "UTC+8"}
                  </span>
                </div>
              </div>

              {/* 专业时序甘特图 (VChart 懒加载) */}
              <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800/90 shadow-lg space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-indigo-400" />
                    <h3 className="text-sm font-semibold text-slate-200">
                      执行时序甘特图 (VChart Gantt Timeline)
                    </h3>
                  </div>
                  <span className="text-xs text-slate-400 font-mono">
                    共 {trace.spans.length} 个步骤
                  </span>
                </div>

                <div className="pt-1">
                  <DynamicVChartGantt
                    spans={trace.spans}
                    totalDurationMs={trace.total_duration_ms}
                    selectedSpanId={selectedSpanId}
                    onSelectSpan={(id) => setSelectedSpanId(id)}
                  />
                </div>
              </div>

              {/* 单步详情检查器 (Step Inspector) */}
              {selectedSpan && (
                <div className="p-5 rounded-2xl bg-slate-950/70 border border-slate-800 shadow-lg space-y-4 animate-in fade-in duration-200">
                  <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-4 h-4 text-indigo-400" />
                      <h3 className="text-sm font-semibold text-slate-200">
                        步骤详情: {selectedSpan.name}
                      </h3>
                    </div>
                    <span className="text-xs text-slate-400 font-mono">
                      耗时 {selectedSpan.duration_ms} ms · 上报于 {selectedSpan.reported_at}
                    </span>
                  </div>

                  {/* 步骤如果是 context_compressor，特别展示中期记忆提炼卡片 */}
                  {selectedSpan.name.includes("compressor") && selectedSpan.output_data && (
                    <div className="p-4 rounded-xl bg-purple-950/30 border border-purple-500/30 space-y-2">
                      <div className="flex items-center gap-2 text-xs font-semibold text-purple-300">
                        <Sparkles className="w-4 h-4 text-purple-400" />
                        <span>中期记忆压缩与上下文摘要决策</span>
                      </div>
                      <div className="text-xs text-slate-300 space-y-1 font-mono">
                        <p>动作: <span className="text-purple-300 font-semibold">{selectedSpan.output_data.action}</span></p>
                        {selectedSpan.output_data.reason && (
                          <p>原因说明: {selectedSpan.output_data.reason}</p>
                        )}
                        {selectedSpan.output_data.messages_compressed_count && (
                          <p>压缩历史消息: {selectedSpan.output_data.messages_compressed_count} 条</p>
                        )}
                      </div>
                      {selectedSpan.output_data.summary && (
                        <div className="mt-3 p-3 rounded-lg bg-slate-950/80 border border-purple-500/20 text-xs text-slate-200">
                          <span className="text-purple-400 font-semibold block mb-1">提炼出的滚动记忆摘要 (Summary):</span>
                          <p className="whitespace-pre-wrap leading-relaxed">{selectedSpan.output_data.summary}</p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 工具调用参数与输出展示 */}
                  {selectedSpan.type === "tool" && (
                    <div className="space-y-3">
                      {selectedSpan.input_data && (
                        <div>
                          <span className="text-xs text-slate-400 block mb-1">工具入参 (Input):</span>
                          <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-indigo-300 font-mono overflow-x-auto">
                            {JSON.stringify(selectedSpan.input_data, null, 2)}
                          </pre>
                        </div>
                      )}
                      {selectedSpan.output_data && (
                        <div>
                          <span className="text-xs text-slate-400 block mb-1">工具返回 (Output Preview):</span>
                          <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-emerald-300 font-mono whitespace-pre-wrap">
                            {typeof selectedSpan.output_data === "object"
                              ? selectedSpan.output_data.result_preview || JSON.stringify(selectedSpan.output_data, null, 2)
                              : String(selectedSpan.output_data)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  {/* LLM 决策与 Token 展示 */}
                  {selectedSpan.type === "llm" && (
                    <div className="space-y-3">
                      {selectedSpan.tokens && (
                        <div className="flex items-center gap-4 text-xs font-mono p-3 rounded-xl bg-slate-950 border border-slate-800">
                          <span>Prompt: {selectedSpan.tokens.prompt_tokens || selectedSpan.tokens.prompt || 0}</span>
                          <span>Completion: {selectedSpan.tokens.completion_tokens || selectedSpan.tokens.completion || 0}</span>
                          <span className="text-indigo-400 font-semibold">Total: {selectedSpan.tokens.total_tokens || selectedSpan.tokens.total || 0}</span>
                        </div>
                      )}
                      {selectedSpan.output_data && (
                        <div>
                          <span className="text-xs text-slate-400 block mb-1">推理决策 (Decision):</span>
                          <pre className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-slate-300 font-mono whitespace-pre-wrap">
                            {JSON.stringify(selectedSpan.output_data, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}

                  {/* 错误信息展示 */}
                  {selectedSpan.error_message && (
                    <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs font-mono">
                      <span className="font-semibold block mb-1">错误异常堆栈:</span>
                      <p>{selectedSpan.error_message}</p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}

          {/* TAB 2: 参考产出文件 (对齐 FileListDrawer 交互) */}
          {activeTab === "files" && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
                  <FolderArchive className="w-4 h-4 text-indigo-400" />
                  <span>当前会话所有生成与关联文件</span>
                </div>
                <span className="text-xs text-slate-400 font-mono">
                  共 {relevantFiles.length} 个资产
                </span>
              </div>

              {relevantFiles.length === 0 ? (
                <div className="p-8 rounded-2xl bg-slate-950/70 border border-slate-800 flex flex-col items-center justify-center text-slate-500 text-center">
                  <FolderArchive className="w-8 h-8 text-slate-600 mb-2" />
                  <p className="text-sm">暂无产出文件记录</p>
                  <p className="text-xs mt-1 text-slate-600">
                    当 Agent 执行写文件、生成 HTML/代码等操作后，将在此展示
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {relevantFiles.map((file) => {
                    const isHtml = file.category === "html" || file.file_name.endsWith(".html");
                    const isImage = file.category === "image" || file.file_name.match(/\.(png|jpg|jpeg|webp)$/i);
                    const isCode = file.category === "code" || file.file_name.match(/\.(js|ts|py|json|sh|css)$/i);

                    const FileIcon = isHtml ? Globe : isImage ? ImageIcon : isCode ? FileCode : FileText;

                    return (
                      <div
                        key={file.id}
                        className="p-3.5 rounded-xl bg-slate-950/80 border border-slate-800/80 hover:border-slate-700 transition-all flex items-center justify-between group shadow-sm"
                      >
                        <div className="flex items-center gap-3 min-w-0 pr-2">
                          <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-indigo-400 shrink-0">
                            <FileIcon className="w-4 h-4" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-semibold text-slate-200 truncate font-mono">
                                {file.file_name}
                              </span>
                              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-400">
                                {file.category}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-500 font-mono truncate mt-0.5">
                              {file.file_path} · {formatBytes(file.file_size)}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => openFilePreview(file)}
                            title="预览文件"
                            className="p-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          <a
                            href={`${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(file.file_path.replace(/^\.?\//, ""))}`}
                            download={file.file_name}
                            target="_blank"
                            rel="noopener noreferrer"
                            title="下载文件"
                            className="p-1.5 rounded-lg bg-slate-800/60 hover:bg-slate-800 text-slate-300 hover:text-white transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                          </a>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
