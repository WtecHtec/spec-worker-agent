"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import {
  X,
  RefreshCw,
  ExternalLink,
  Monitor,
  Smartphone,
  Globe,
  Lock,
  ArrowLeft,
  ArrowRight,
  Terminal,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Package,
  GripVertical,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useWebContainer } from "@/hooks/useWebContainer";
import { usePreviewStore } from "@/store/usePreviewStore";
import { useAuthStore } from "@/store/useAuthStore";
import { api, SANDBOX_BASE } from "@/lib/api";

type ViewportMode = "desktop" | "mobile";

export const WebPreviewPanel: React.FC = () => {
  const {
    isOpen,
    width,
    title,
    fileName,
    previewUrl: staticPreviewUrl,
    sessionId,
    isWebContainer,
    closePreview,
    setWidth,
  } = usePreviewStore();

  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [isTerminalExpanded, setIsTerminalExpanded] = useState<boolean>(false);
  const [htmlDocContent, setHtmlDocContent] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const token = useAuthStore((state) => state.token);
  const terminalBottomRef = useRef<HTMLDivElement>(null);
  const dragStartXRef = useRef<number>(0);
  const dragStartWidthRef = useRef<number>(width);

  // WebContainer hook
  const {
    status: wcStatus,
    logs: wcLogs,
    previewUrl: wcPreviewUrl,
    port: wcPort,
    error: wcError,
    runProject,
    stopProject,
  } = useWebContainer();

  // 自动滚动控制台到底部
  useEffect(() => {
    if (isTerminalExpanded && terminalBottomRef.current) {
      terminalBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [wcLogs, isTerminalExpanded]);

  // 鼠标拖拽拉伸宽度事件处理
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = width;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      // 往左拖（clientX 变小），面板变宽
      const deltaX = dragStartXRef.current - moveEvent.clientX;
      setWidth(dragStartWidthRef.current + deltaX);
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // 双击重置宽度为 560px
  const handleDoubleClickResizer = () => {
    setWidth(560);
  };

  // 当处于纯静态 HTML 模式时，拉取 HTML 文本并通过 srcDoc 渲染
  useEffect(() => {
    if (isOpen && !isWebContainer && staticPreviewUrl) {
      let isCancelled = false;
      setIsIframeLoading(true);

      async function fetchStaticHtml() {
        try {
          const resp = await fetch(staticPreviewUrl);
          if (resp.ok) {
            let htmlText = await resp.text();
            // 注入 base 标签
            const urlObj = new URL(
              staticPreviewUrl,
              typeof window !== "undefined" ? window.location.origin : "http://localhost:5050"
            );
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

  // 当为 WebContainer 模式时，自动拉取会话文件并拉起开发服务
  useEffect(() => {
    if (isOpen && isWebContainer && sessionId) {
      let isCancelled = false;

      async function bootProject() {
        try {
          const res = await api.getSessionFiles(sessionId!, token || "");
          const sessionFiles = res.items || [];

          const virtualFiles: Array<{ file_path: string; content: string }> = [];
          for (const f of sessionFiles) {
            try {
              const rawSandboxUrl = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(
                f.file_path.replace(/^\.?\//, "")
              )}&session_id=${encodeURIComponent(sessionId!)}`;

              let content = "";
              const rawResp = await fetch(rawSandboxUrl);
              if (rawResp.ok) {
                content = await rawResp.text();
              } else {
                const fileStreamUrl = api.getFilePreviewUrl(sessionId!, f.id, token);
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

  const handleClose = () => {
    if (isWebContainer) {
      stopProject();
    }
    closePreview();
  };

  if (!isOpen) return null;

  const activePreviewUrl = isWebContainer ? wcPreviewUrl : staticPreviewUrl;

  const handleRefresh = () => {
    setIsIframeLoading(true);
    setRefreshKey((prev) => prev + 1);
  };

  return (
    <div
      style={{ width: `${width}px` }}
      className={`relative h-full flex flex-col bg-slate-900 border-l border-slate-800 shrink-0 z-20 shadow-2xl transition-all ${
        isDragging ? "select-none" : ""
      }`}
    >
      {/* 左侧可拖拽拉伸把手 */}
      <div
        onMouseDown={handleMouseDown}
        onDoubleClick={handleDoubleClickResizer}
        className="absolute left-0 top-0 bottom-0 w-2 -ml-1 cursor-col-resize z-30 flex items-center justify-center group hover:bg-indigo-500/40 active:bg-indigo-600 transition-colors"
        title="按住左右拖拽调整宽度，双击重置"
      >
        <div className="w-0.5 h-8 rounded-full bg-slate-600 group-hover:bg-indigo-300 transition-colors" />
      </div>

      {/* 顶部工具栏 */}
      <div className="flex flex-col border-b border-slate-800 bg-slate-950/80 shrink-0">
        <div className="flex items-center justify-between px-3.5 py-2">
          {/* 左侧：标题与状态 */}
          <div className="flex items-center gap-2 min-w-0">
            {isWebContainer ? (
              <Package className="w-4 h-4 text-violet-400 shrink-0" />
            ) : (
              <Globe className="w-4 h-4 text-indigo-400 shrink-0" />
            )}
            <span className="font-semibold text-slate-200 text-xs truncate max-w-[140px]">
              {title}
            </span>

            {/* 状态徽标 */}
            {isWebContainer ? (
              <div className="flex items-center gap-1 font-mono">
                {wcStatus === "booting" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-indigo-500/15 text-indigo-300 border border-indigo-500/20">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" />
                    沙箱启动...
                  </span>
                )}
                {wcStatus === "installing" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-sky-500/15 text-sky-300 border border-sky-500/20 animate-pulse">
                    <Loader2 className="w-2.5 h-2.5 animate-spin" />
                    npm i...
                  </span>
                )}
                {wcStatus === "starting" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-violet-500/15 text-violet-300 border border-violet-500/20 animate-pulse">
                    <Sparkles className="w-2.5 h-2.5" />
                    Vite 启动...
                  </span>
                )}
                {wcStatus === "ready" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
                    <CheckCircle2 className="w-2.5 h-2.5" />
                    Live
                  </span>
                )}
                {wcStatus === "error" && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] bg-rose-500/15 text-rose-400 border border-rose-500/20">
                    <AlertCircle className="w-2.5 h-2.5" />
                    错误
                  </span>
                )}
              </div>
            ) : (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                H5
              </span>
            )}
          </div>

          {/* 右侧：视口切换、终端、外部打开、关闭 */}
          <div className="flex items-center gap-1">
            <div className="flex items-center bg-slate-900 p-0.5 rounded-lg border border-slate-800 mr-1">
              <button
                onClick={() => setViewport("desktop")}
                className={`p-1 rounded text-xs transition-all ${
                  viewport === "desktop"
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                title="桌面全宽"
              >
                <Monitor className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewport("mobile")}
                className={`p-1 rounded text-xs transition-all ${
                  viewport === "mobile"
                    ? "bg-indigo-600 text-white"
                    : "text-slate-400 hover:text-slate-200"
                }`}
                title="手机视图 (375px)"
              >
                <Smartphone className="w-3.5 h-3.5" />
              </button>
            </div>

            {isWebContainer && (
              <button
                onClick={() => setIsTerminalExpanded((prev) => !prev)}
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-all border ${
                  isTerminalExpanded
                    ? "bg-indigo-600/30 text-indigo-300 border-indigo-500/40"
                    : "bg-slate-800/80 text-slate-400 hover:text-slate-200 border-slate-700/60"
                }`}
                title="控制台终端"
              >
                <Terminal className="w-3.5 h-3.5 text-indigo-400" />
                <span>终端</span>
                {isTerminalExpanded ? (
                  <ChevronDown className="w-3 h-3" />
                ) : (
                  <ChevronUp className="w-3 h-3" />
                )}
              </button>
            )}

            {activePreviewUrl && (
              <a
                href={activePreviewUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1.5 text-slate-400 hover:text-indigo-300 hover:bg-slate-800 rounded-lg transition-colors"
                title="新窗口打开"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}

            <button
              onClick={handleClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-rose-500/20 rounded-lg transition-colors"
              title="收起预览面板"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* 模拟 URL 地址栏 */}
        <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-950/40 border-t border-slate-900">
          <button
            onClick={handleRefresh}
            className={`p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-slate-200 transition-colors ${
              isIframeLoading ? "animate-spin text-indigo-400" : ""
            }`}
            title="刷新预览"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
          <div className="flex-1 flex items-center gap-1.5 px-2.5 py-0.5 bg-slate-900/90 border border-slate-800 rounded-md text-[11px] text-slate-300 font-mono select-all truncate">
            <Lock className="w-2.5 h-2.5 text-emerald-400 shrink-0" />
            <span className="text-slate-400 truncate">
              {activePreviewUrl || `http://localhost:${wcPort || 3000}/`}
            </span>
          </div>
        </div>
      </div>

      {/* 主展示区 */}
      <div className="flex-1 w-full bg-slate-950/90 flex flex-col items-center justify-center p-2 overflow-hidden relative">
        <div
          className={`w-full h-full ${
            viewport === "mobile" ? "max-w-[375px]" : "max-w-full"
          } transition-all duration-200 shadow-2xl relative flex flex-col bg-white rounded-lg overflow-hidden border border-slate-800`}
        >
          {/* WebContainer 等待遮罩 */}
          {isWebContainer && wcStatus !== "ready" && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-900/95 backdrop-blur-md gap-3 p-6 text-center">
              <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
              <div className="space-y-1">
                <p className="text-xs font-semibold text-slate-200 font-sans">
                  {wcStatus === "booting" && "正在启动 WebContainer 虚拟内核..."}
                  {wcStatus === "mounting" && "正在挂载会话文件结构..."}
                  {wcStatus === "installing" && "正在安装依赖包 (npm i)..."}
                  {wcStatus === "starting" && "正在拉起 Vite 开发服务器..."}
                  {wcStatus === "error" && "沙箱启动异常，请检查终端日志"}
                </p>
                <p className="text-[10px] text-slate-500 font-mono">
                  基于浏览器端 WebAssembly 运行
                </p>
              </div>

              {wcError && (
                <div className="mt-2 p-2 bg-rose-500/10 border border-rose-500/30 rounded text-[11px] text-rose-300 font-mono max-w-xs text-left">
                  {wcError}
                </div>
              )}
            </div>
          )}

          {/* iframe 渲染 */}
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
              className="absolute bottom-2 left-2 right-2 h-48 bg-slate-950/95 border border-slate-800 rounded-lg shadow-2xl flex flex-col overflow-hidden z-20 backdrop-blur-xl"
            >
              <div className="flex items-center justify-between px-3 py-1 bg-slate-900 border-b border-slate-800 text-[10px] font-mono text-slate-400">
                <div className="flex items-center gap-1.5">
                  <Terminal className="w-3 h-3 text-indigo-400" />
                  <span>WebContainer 控制台日志</span>
                </div>
                <button
                  onClick={() => setIsTerminalExpanded(false)}
                  className="p-0.5 hover:text-white rounded"
                >
                  <ChevronDown className="w-3 h-3" />
                </button>
              </div>

              <div className="flex-1 p-2.5 overflow-y-auto font-mono text-[11px] text-slate-300 space-y-1 bg-black/60 select-text">
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
    </div>
  );
};
