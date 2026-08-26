"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  X,
  RefreshCw,
  ExternalLink,
  Monitor,
  Smartphone,
  Tablet,
  Globe,
  Lock,
  ArrowLeft,
  ArrowRight,
  Maximize2,
  Minimize2,
  Terminal,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Package,
  RotateCcw,
  Download,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useWebContainer } from "@/hooks/useWebContainer";
import { useFileStore } from "@/store/useFileStore";
import { useAuthStore } from "@/store/useAuthStore";
import { toast } from "@/store/useToastStore";
import { api, SANDBOX_BASE } from "@/lib/api";
import { downloadSessionFilesAsZip } from "@/lib/zipHelper";

interface WebPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  previewUrl: string;
  title?: string;
  fileName?: string;
  sessionId?: string;
  isWebContainer?: boolean;
}

type ViewportMode = "desktop" | "tablet" | "mobile";

export const WebPreviewModal: React.FC<WebPreviewModalProps> = ({
  isOpen,
  onClose,
  previewUrl: staticPreviewUrl,
  title = "Web 页面预览",
  fileName = "index.html",
  sessionId,
  isWebContainer = false,
}) => {
  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);
  const [isTerminalExpanded, setIsTerminalExpanded] = useState<boolean>(false);
  const [isRestarting, setIsRestarting] = useState<boolean>(false);
  const [isZipping, setIsZipping] = useState<boolean>(false);
  const [htmlDocContent, setHtmlDocContent] = useState<string>("");

  const token = useAuthStore((state) => state.token);
  const terminalBottomRef = useRef<HTMLDivElement>(null);

  // WebContainer hook
  const {
    status: wcStatus,
    logs: wcLogs,
    previewUrl: wcPreviewUrl,
    port: wcPort,
    error: wcError,
    isSupported: wcSupported,
    runProject,
    stopProject,
  } = useWebContainer();

  // 自动滚动控制台到底部
  useEffect(() => {
    if (isTerminalExpanded && terminalBottomRef.current) {
      terminalBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [wcLogs, isTerminalExpanded]);

  // 当处于纯静态 HTML 模式时，拉取 HTML 文本并通过 srcDoc 渲染（完全规避跨域 iframe 拦截）
  useEffect(() => {
    if (isOpen && !isWebContainer && staticPreviewUrl) {
      let isCancelled = false;
      setIsIframeLoading(true);

      async function fetchStaticHtml() {
        try {
          const resp = await fetch(staticPreviewUrl);
          if (resp.ok) {
            let htmlText = await resp.text();
            // 若包含相对路径资源，注入 base 标签
            const urlObj = new URL(staticPreviewUrl, typeof window !== "undefined" ? window.location.origin : "http://localhost:5050");
            const sessionIdParam = urlObj.searchParams.get("session_id") || "";
            const basePath = `${urlObj.origin}${urlObj.pathname}?session_id=${sessionIdParam}&path=`;
            if (htmlText.includes("<head>")) {
              htmlText = htmlText.replace("<head>", `<head><base href="${basePath}">`);
            } else if (htmlText.includes("<html>")) {
              htmlText = htmlText.replace("<html>", `<html><head><base href="${basePath}"></head>`);
            } else {
              htmlText = `<base href="${basePath}">` + htmlText;
            }

            if (!isCancelled) {
              setHtmlDocContent(htmlText);
            }
          }
        } catch (err) {
          console.error("Failed to fetch static html for srcDoc", err);
        } finally {
          if (!isCancelled) {
            setIsIframeLoading(false);
          }
        }
      }

      fetchStaticHtml();

      return () => {
        isCancelled = true;
      };
    }
  }, [isOpen, isWebContainer, staticPreviewUrl, refreshKey]);

  // 当弹窗打开且为 WebContainer 模式时，自动拉取会话文件并拉起开发服务
  useEffect(() => {
    if (isOpen && isWebContainer && sessionId) {
      let isCancelled = false;

      async function bootProject() {
        try {
          // 1. 从后端获取当前会话的所有文件
          const res = await api.getSessionFiles(sessionId!, token || "");
          const sessionFiles = res.items || [];

          // 2. 转换为 VirtualFile 结构
          const virtualFiles: Array<{ file_path: string; content: string }> = [];
          for (const f of sessionFiles) {
            try {
              // 优先从沙箱原始流地址直拉内容
              const rawSandboxUrl = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(
                f.file_path.replace(/^\.?\//, "")
              )}&session_id=${encodeURIComponent(sessionId!)}`;

              let content = "";
              const rawResp = await fetch(rawSandboxUrl);
              if (rawResp.ok) {
                content = await rawResp.text();
              } else {
                // 回退到后端代理接口
                const fileStreamUrl = api.getFilePreviewUrl(sessionId!, f.id, token);
                const fileResp = await fetch(fileStreamUrl);
                if (fileResp.ok) {
                  content = await fileResp.text();
                }
              }

              // 过滤错误文本
              if (content && !content.startsWith("Error: Failed to stream")) {
                virtualFiles.push({
                  file_path: f.file_path,
                  content,
                });
              }
            } catch (e) {
              console.warn(`Failed to fetch content for ${f.file_path}`, e);
            }
          }

          if (!isCancelled && virtualFiles.length > 0) {
            await runProject(sessionId!, virtualFiles);
          }
        } catch (err) {
          console.error("Failed to start WebContainer session", err);
        }
      }

      bootProject();

      return () => {
        isCancelled = true;
      };
    }
  }, [isOpen, isWebContainer, sessionId, token, runProject]);

  const handleRestartWebContainer = async () => {
    if (!sessionId) return;
    setIsRestarting(true);
    try {
      await stopProject();
      const res = await api.getSessionFiles(sessionId, token || "");
      const sessionFiles = res.items || [];
      const virtualFiles: Array<{ file_path: string; content: string }> = [];
      for (const f of sessionFiles) {
        try {
          const rawSandboxUrl = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(
            f.file_path.replace(/^\.?\//, "")
          )}&session_id=${encodeURIComponent(sessionId)}`;

          let content = "";
          const rawResp = await fetch(rawSandboxUrl);
          if (rawResp.ok) {
            content = await rawResp.text();
          } else {
            const fileStreamUrl = api.getFilePreviewUrl(sessionId, f.id, token);
            const fileResp = await fetch(fileStreamUrl);
            if (fileResp.ok) {
              content = await fileResp.text();
            }
          }

          if (content && !content.startsWith("Error: Failed to stream")) {
            virtualFiles.push({
              file_path: f.file_path,
              content,
            });
          }
        } catch (e) {
          console.warn(`Failed to fetch content for ${f.file_path}`, e);
        }
      }

      if (virtualFiles.length > 0) {
        await runProject(sessionId, virtualFiles);
      }
      toast.success("WebContainer 服务已重新启动！", "重启成功");
    } catch (err: any) {
      console.error("Failed to restart WebContainer:", err);
      toast.error(err.message || "重启失败，请重试", "重启失败");
    } finally {
      setIsRestarting(false);
    }
  };

  const handleDownloadZip = async () => {
    if (!sessionId) return;
    setIsZipping(true);
    try {
      await downloadSessionFilesAsZip(sessionId, token || "", `${title || "project"}.zip`);
      toast.success("当前会话产出与工程源码已打包为 ZIP 下载！", "下载完成");
    } catch (err: any) {
      console.error("Failed to download zip:", err);
      toast.error(err.message || "打包源码下载失败", "下载失败");
    } finally {
      setIsZipping(false);
    }
  };

  // 弹窗关闭时停止 WebContainer 进程
  const handleClose = () => {
    if (isWebContainer) {
      stopProject();
    }
    onClose();
  };

  if (!isOpen) return null;

  const activePreviewUrl = isWebContainer ? wcPreviewUrl : staticPreviewUrl;

  const handleRefresh = () => {
    setIsIframeLoading(true);
    setRefreshKey((prev) => prev + 1);
  };

  const getViewportWidth = () => {
    switch (viewport) {
      case "mobile":
        return "max-w-[390px]";
      case "tablet":
        return "max-w-[768px]";
      case "desktop":
      default:
        return "max-w-full";
    }
  };

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-2 sm:p-4 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-200">
        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.96 }}
          transition={{ duration: 0.2 }}
          className={`relative w-full ${
            isFullScreen ? "h-[98vh] max-w-[99vw]" : "h-[90vh] max-w-6xl"
          } flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden transition-all duration-300`}
        >
          {/* 顶部模拟浏览器工具栏 */}
          <div className="flex flex-col border-b border-slate-800 bg-slate-950/80 shrink-0">
            {/* 顶层：窗口操作与设备模式切换 */}
            <div className="flex items-center justify-between px-4 py-2.5">
              {/* 左侧：交通灯窗口控制与标题 */}
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex items-center gap-1.5">
                  <div className="w-3 h-3 rounded-full bg-rose-500/80 border border-rose-600/40" />
                  <div className="w-3 h-3 rounded-full bg-amber-500/80 border border-amber-600/40" />
                  <div className="w-3 h-3 rounded-full bg-emerald-500/80 border border-emerald-600/40" />
                </div>
                <div className="h-4 w-[1px] bg-slate-800 mx-1" />
                <div className="flex items-center gap-2 truncate">
                  <Globe className="w-4 h-4 text-indigo-400 shrink-0" />
                  <span className="font-semibold text-slate-200 text-xs truncate">
                    {title}
                  </span>

                  {/* 状态徽标 */}
                  {isWebContainer ? (
                    <div className="flex items-center gap-1.5 font-mono">
                      {wcStatus === "booting" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-indigo-500/15 text-indigo-300 border border-indigo-500/20">
                          <Loader2 className="w-2.5 h-2.5 animate-spin" />
                          启动虚拟沙箱...
                        </span>
                      )}
                      {wcStatus === "mounting" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-amber-500/15 text-amber-300 border border-amber-500/20">
                          <Package className="w-2.5 h-2.5 animate-spin" />
                          挂载项目代码...
                        </span>
                      )}
                      {wcStatus === "installing" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-sky-500/15 text-sky-300 border border-sky-500/20 animate-pulse">
                          <Loader2 className="w-2.5 h-2.5 animate-spin" />
                          安装依赖 npm i...
                        </span>
                      )}
                      {wcStatus === "starting" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-violet-500/15 text-violet-300 border border-violet-500/20 animate-pulse">
                          <Sparkles className="w-2.5 h-2.5" />
                          拉起 Vite 服务...
                        </span>
                      )}
                      {wcStatus === "ready" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                          <CheckCircle2 className="w-2.5 h-2.5" />
                          Live (Port {wcPort || 3000})
                        </span>
                      )}
                      {wcStatus === "error" && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] bg-rose-500/15 text-rose-400 border border-rose-500/20">
                          <AlertCircle className="w-2.5 h-2.5" />
                          运行失败
                        </span>
                      )}
                    </div>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                      HTML5 Static
                    </span>
                  )}
                </div>
              </div>

              {/* 中间：响应式设备视口切换 */}
              <div className="hidden sm:flex items-center gap-1 bg-slate-900 p-1 rounded-xl border border-slate-800">
                <button
                  onClick={() => setViewport("desktop")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                    viewport === "desktop"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                  }`}
                  title="桌面端全宽视图"
                >
                  <Monitor className="w-3.5 h-3.5" />
                  <span>桌面</span>
                </button>
                <button
                  onClick={() => setViewport("tablet")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                    viewport === "tablet"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                  }`}
                  title="平板视图 (768px)"
                >
                  <Tablet className="w-3.5 h-3.5" />
                  <span>平板</span>
                </button>
                <button
                  onClick={() => setViewport("mobile")}
                  className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-all ${
                    viewport === "mobile"
                      ? "bg-indigo-600 text-white shadow-sm"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                  }`}
                  title="手机视图 (390px)"
                >
                  <Smartphone className="w-3.5 h-3.5" />
                  <span>手机</span>
                </button>
              </div>

              {/* 右侧：全屏、外部打开与关闭 */}
              <div className="flex items-center gap-1.5">
                {isWebContainer && (
                  <button
                    onClick={() => setIsTerminalExpanded((prev) => !prev)}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono transition-all border ${
                      isTerminalExpanded
                        ? "bg-indigo-600/30 text-indigo-300 border-indigo-500/40"
                        : "bg-slate-800/80 text-slate-400 hover:text-slate-200 border-slate-700/60"
                    }`}
                    title="展开/收起控制台输出"
                  >
                    <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                    <span>终端</span>
                    {isTerminalExpanded ? (
                      <ChevronDown className="w-3 h-3 ml-0.5" />
                    ) : (
                      <ChevronUp className="w-3 h-3 ml-0.5" />
                    )}
                  </button>
                )}

                <button
                  onClick={() => setIsFullScreen((prev) => !prev)}
                  className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg transition-colors"
                  title={isFullScreen ? "还原窗口" : "全屏放大"}
                >
                  {isFullScreen ? (
                    <Minimize2 className="w-4 h-4" />
                  ) : (
                    <Maximize2 className="w-4 h-4" />
                  )}
                </button>

                {/* 重启 WebContainer 服务 */}
                {isWebContainer && (
                  <button
                    onClick={handleRestartWebContainer}
                    disabled={isRestarting || wcStatus === "booting" || wcStatus === "installing"}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono transition-all border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-750 disabled:opacity-50"
                    title="重启 WebContainer 服务"
                  >
                    <RotateCcw className={`w-3.5 h-3.5 ${isRestarting ? "animate-spin text-indigo-400" : "text-amber-400"}`} />
                    <span className="hidden sm:inline">重启服务</span>
                  </button>
                )}

                {/* 源码打包下载 ZIP */}
                {sessionId && (
                  <button
                    onClick={handleDownloadZip}
                    disabled={isZipping}
                    className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-mono transition-all border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-750 disabled:opacity-50"
                    title="打包下载当前会话所有源码 (ZIP)"
                  >
                    {isZipping ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                    ) : (
                      <Download className="w-3.5 h-3.5 text-emerald-400" />
                    )}
                    <span className="hidden sm:inline">下载 ZIP</span>
                  </button>
                )}

                {/* 非 WebContainer 模式下支持新标签页打开 */}
                {!isWebContainer && activePreviewUrl && (
                  <a
                    href={activePreviewUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="p-1.5 text-slate-400 hover:text-indigo-300 hover:bg-slate-800 rounded-lg transition-colors"
                    title="新标签页打开"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}

                <button
                  onClick={handleClose}
                  className="p-1.5 text-slate-400 hover:text-white hover:bg-rose-500/20 rounded-lg transition-colors ml-1"
                  title="关闭预览"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* 底层：模拟浏览器 URL 地址栏与刷新 */}
            <div className="flex items-center gap-2 px-4 py-1.5 bg-slate-950/40 border-t border-slate-900">
              <div className="flex items-center gap-1 text-slate-500">
                <button className="p-1 rounded hover:bg-slate-800 disabled:opacity-40" disabled>
                  <ArrowLeft className="w-3.5 h-3.5" />
                </button>
                <button className="p-1 rounded hover:bg-slate-800 disabled:opacity-40" disabled>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={handleRefresh}
                  className={`p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors ${
                    isIframeLoading ? "animate-spin text-indigo-400" : ""
                  }`}
                  title="重新加载页面"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* 模拟 URL 栏 */}
              <div className="flex-1 flex items-center gap-2 px-3 py-1 bg-slate-900/90 border border-slate-800 rounded-lg text-xs text-slate-300 font-mono select-all truncate">
                <Lock className="w-3 h-3 text-emerald-400 shrink-0" />
                <span className="text-slate-400 truncate">
                  {activePreviewUrl || `http://localhost:${wcPort || 3000}/`}
                </span>
              </div>
            </div>
          </div>

          {/* 核心展示区：自适应设备视口 */}
          <div className="flex-1 w-full bg-slate-950/90 flex flex-col items-center justify-center p-2 sm:p-4 overflow-hidden relative">
            <div
              className={`w-full h-full ${getViewportWidth()} transition-all duration-300 shadow-2xl relative flex flex-col bg-white rounded-xl overflow-hidden border border-slate-800`}
            >
              {/* 加载等待遮罩 */}
              {isWebContainer && wcStatus !== "ready" && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-900/95 backdrop-blur-md gap-3 p-6 text-center">
                  <div className="w-10 h-10 rounded-full border-3 border-indigo-500 border-t-transparent animate-spin" />
                  <div className="space-y-1">
                    <p className="text-sm font-semibold text-slate-200 font-sans">
                      {wcStatus === "booting" && "正在启动 WebContainer 虚拟沙箱..."}
                      {wcStatus === "mounting" && "正在挂载会话文件结构..."}
                      {wcStatus === "installing" && "正在安装 NPM 依赖包 (npm install)..."}
                      {wcStatus === "starting" && "正在拉起 Vite 开发服务器..."}
                      {wcStatus === "error" && "沙箱启动异常，请检查代码或终端日志"}
                    </p>
                    <p className="text-xs text-slate-400 font-mono">
                      基于浏览器端 WebAssembly 运行，零服务器消耗
                    </p>
                  </div>

                  {/* 错误提示与重试 */}
                  {wcError && (
                    <div className="mt-3 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 font-mono max-w-md text-left">
                      {wcError}
                    </div>
                  )}
                </div>
              )}

              {/* 沙箱隔离 iframe */}
              {isWebContainer ? (
                wcPreviewUrl ? (
                  <iframe
                    key={refreshKey}
                    src={wcPreviewUrl}
                    title={title}
                    allow="cross-origin-isolated; autoplay"
                    sandbox="allow-scripts allow-forms allow-same-origin allow-modals allow-popups"
                    className="w-full h-full border-0 bg-white"
                    onLoad={() => setIsIframeLoading(false)}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-slate-900 text-slate-500 text-xs font-mono">
                    等待 Web 开发服务启动...
                  </div>
                )
              ) : (
                <iframe
                  key={refreshKey}
                  srcDoc={htmlDocContent || undefined}
                  src={htmlDocContent ? undefined : staticPreviewUrl}
                  title={title}
                  allow="cross-origin-isolated; autoplay"
                  sandbox="allow-scripts allow-forms allow-same-origin allow-modals allow-popups"
                  className="w-full h-full border-0 bg-white"
                  onLoad={() => setIsIframeLoading(false)}
                />
              )}
            </div>

            {/* 可折叠 Terminal 终端控制台面板 */}
            <AnimatePresence>
              {isTerminalExpanded && isWebContainer && (
                <motion.div
                  initial={{ opacity: 0, y: 150 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 150 }}
                  transition={{ duration: 0.2 }}
                  className="absolute bottom-2 left-2 right-2 sm:bottom-4 sm:left-4 sm:right-4 h-56 bg-slate-950/95 border border-slate-800 rounded-xl shadow-2xl flex flex-col overflow-hidden z-20 backdrop-blur-xl"
                >
                  <div className="flex items-center justify-between px-3 py-1.5 bg-slate-900 border-b border-slate-800 text-[11px] font-mono text-slate-400">
                    <div className="flex items-center gap-2">
                      <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                      <span>WebContainer 控制台日志</span>
                    </div>
                    <button
                      onClick={() => setIsTerminalExpanded(false)}
                      className="p-1 hover:text-white rounded"
                    >
                      <ChevronDown className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <div className="flex-1 p-3 overflow-y-auto font-mono text-xs text-slate-300 space-y-1 bg-black/50 select-text">
                    {wcLogs.length === 0 ? (
                      <p className="text-slate-600 italic">暂无输出日志...</p>
                    ) : (
                      wcLogs.map((line, idx) => (
                        <div key={idx} className="whitespace-pre-wrap leading-relaxed">
                          {line}
                        </div>
                      ))
                    )}
                    <div ref={terminalBottomRef} />
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
