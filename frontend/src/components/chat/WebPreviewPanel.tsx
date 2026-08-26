"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
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
  RotateCcw,
  Download,
  Folder,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useWebContainer } from "@/hooks/useWebContainer";
import { usePreviewStore } from "@/store/usePreviewStore";
import { useAuthStore } from "@/store/useAuthStore";
import { toast } from "@/store/useToastStore";
import { api, SANDBOX_BASE } from "@/lib/api";
import { downloadSessionFilesAsZip } from "@/lib/zipHelper";
import { WebContainerFileTree } from "./WebContainerFileTree";

type ViewportMode = "desktop" | "mobile";

interface PreviewTarget {
  id: string;
  title: string;
  fileName: string;
  type: "webcontainer" | "html";
  filePath?: string;
  previewUrl?: string;
}

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
    switchTarget,
  } = usePreviewStore();

  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [isTerminalExpanded, setIsTerminalExpanded] = useState<boolean>(false);
  const [isFileTreeExpanded, setIsFileTreeExpanded] = useState<boolean>(false);
  const [htmlDocContent, setHtmlDocContent] = useState<string>("");
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [isRestarting, setIsRestarting] = useState<boolean>(false);
  const [isZipping, setIsZipping] = useState<boolean>(false);
  const [isTargetDropdownOpen, setIsTargetDropdownOpen] = useState<boolean>(false);
  const [sessionFiles, setSessionFiles] = useState<Array<{ id: string; file_name: string; file_path: string; category: string }>>([]);

  const token = useAuthStore((state) => state.token);
  const terminalBottomRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const dragStartXRef = useRef<number>(0);
  const dragStartWidthRef = useRef<number>(width);

  // 监听点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsTargetDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // 当面板打开时拉取会话文件列表用于构建预览目标列表
  useEffect(() => {
    if (isOpen && sessionId) {
      api.getSessionFiles(sessionId, token || "")
        .then((res) => {
          if (res && res.items) {
            setSessionFiles(res.items);
          }
        })
        .catch((err) => console.warn("Failed to fetch session files for targets", err));
    }
  }, [isOpen, sessionId, token, refreshKey]);

  // WebContainer hook
  const {
    status: wcStatus,
    logs: wcLogs,
    previewUrl: wcPreviewUrl,
    port: wcPort,
    error: wcError,
    fileTree: wcFileTree,
    refreshFileTree,
    readFile,
    runProject,
    stopProject,
  } = useWebContainer();

  // 自动滚动控制台到底部
  useEffect(() => {
    if (isTerminalExpanded && terminalBottomRef.current) {
      terminalBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [wcLogs, isTerminalExpanded]);

  // 鼠标拖拽拉伸宽度事件处理（使用 rAF 节流 + 禁用 iframe 捕获）
  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = width;

    let rafId: number | null = null;

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = requestAnimationFrame(() => {
        // 往左拖（clientX 变小），面板变宽
        const deltaX = dragStartXRef.current - moveEvent.clientX;
        setWidth(dragStartWidthRef.current + deltaX);
      });
    };

    const handleMouseUp = () => {
      if (rafId) cancelAnimationFrame(rafId);
      setIsDragging(false);
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
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
      toast.success("WebContainer 服务已重启并重新加载工程！", "重启成功");
    } catch (err: any) {
      console.error("Failed to restart WebContainer:", err);
      toast.error(err.message || "重启失败，请重试", "重启异常");
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

  // 计算当前会话可预览的所有目标（包含 React 工程与所有 HTML 静态页面）
  const availableTargets = useMemo<PreviewTarget[]>(() => {
    const targets: PreviewTarget[] = [];
    const hasPackageJson = sessionFiles.some(
      (f) => f.file_name === "package.json" || f.file_path.endsWith("package.json")
    );
    if (hasPackageJson) {
      targets.push({
        id: "webcontainer",
        title: "React Web 工程 (Vite)",
        fileName: "package.json",
        type: "webcontainer",
      });
    }

    const htmlFiles = sessionFiles.filter(
      (f) => f.category === "html" || f.file_name.endsWith(".html") || f.file_path.endsWith(".html")
    );

    htmlFiles.forEach((f) => {
      const cleanPath = f.file_path.replace(/^\.?\//, "");
      const rawSandboxUrl = `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(cleanPath)}&session_id=${encodeURIComponent(sessionId || "")}`;
      targets.push({
        id: `html:${cleanPath}`,
        title: f.file_name,
        fileName: f.file_name,
        filePath: cleanPath,
        type: "html",
        previewUrl: rawSandboxUrl,
      });
    });

    if (targets.length === 0 && !isWebContainer) {
      targets.push({
        id: `html:${fileName || "index.html"}`,
        title: title || "HTML 页面",
        fileName: fileName || "index.html",
        type: "html",
        previewUrl: staticPreviewUrl,
      });
    }

    return targets;
  }, [sessionFiles, sessionId, isWebContainer, title, fileName, staticPreviewUrl]);

  const handleSelectTarget = (target: PreviewTarget) => {
    setIsTargetDropdownOpen(false);
    if (target.type === "webcontainer") {
      switchTarget({
        title: target.title,
        fileName: target.fileName,
        previewUrl: "",
        isWebContainer: true,
      });
    } else {
      if (isWebContainer) {
        stopProject();
      }
      switchTarget({
        title: target.title,
        fileName: target.fileName,
        previewUrl: target.previewUrl || "",
        isWebContainer: false,
      });
    }
  };

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
      className={`relative h-full flex flex-col bg-slate-900 border-l border-slate-800 shrink-0 z-20 shadow-2xl ${
        isDragging ? "transition-none select-none" : "transition-[width] duration-150 ease-out"
      }`}
    >
      {/* 拖拽全局事件捕获遮罩，防止 iframe 吞掉 mousemove */}
      {isDragging && (
        <div className="fixed inset-0 z-50 cursor-col-resize select-none bg-transparent" />
      )}

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
          {/* 左侧：目标选择器与状态徽标 */}
          <div className="flex items-center gap-2 min-w-0">
            {/* 目标切换下拉框 */}
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setIsTargetDropdownOpen((prev) => !prev)}
                className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-700/80 text-slate-200 text-xs font-semibold transition-all max-w-[200px] group shadow-sm"
                title="点击切换渲染目标（多个 HTML 页面或 React 工程）"
              >
                {isWebContainer ? (
                  <Package className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                ) : (
                  <Globe className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                )}
                <span className="truncate">{title}</span>
                {availableTargets.length > 1 && (
                  <span className="px-1 py-0.2 rounded text-[10px] font-mono bg-slate-800 text-indigo-300 border border-slate-700 shrink-0">
                    {availableTargets.length}
                  </span>
                )}
                <ChevronDown className={`w-3 h-3 text-slate-400 shrink-0 transition-transform duration-200 ${isTargetDropdownOpen ? "rotate-180 text-indigo-400" : "group-hover:text-slate-200"}`} />
              </button>

              {/* 下拉目标列表 */}
              {isTargetDropdownOpen && (
                <div className="absolute top-full left-0 mt-1.5 w-64 rounded-xl bg-slate-900/95 border border-slate-700 shadow-2xl backdrop-blur-xl p-1.5 z-50 animate-in fade-in zoom-in-95">
                  <div className="text-[10px] font-semibold text-slate-400 px-2 py-1 uppercase tracking-wider flex items-center justify-between">
                    <span>可预览目标</span>
                    <span className="font-mono text-indigo-400">{availableTargets.length} 个</span>
                  </div>
                  <div className="space-y-0.5 max-h-60 overflow-y-auto">
                    {availableTargets.map((t: PreviewTarget) => {
                      const isSelected = isWebContainer
                        ? t.type === "webcontainer"
                        : (!isWebContainer && (fileName === t.fileName || title === t.title));
                      return (
                        <button
                          key={t.id}
                          onClick={() => handleSelectTarget(t)}
                          className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs transition-colors ${
                            isSelected
                              ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30 font-medium"
                              : "text-slate-300 hover:bg-slate-800 hover:text-white"
                          }`}
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            {t.type === "webcontainer" ? (
                              <Package className="w-3.5 h-3.5 text-violet-400 shrink-0" />
                            ) : (
                              <Globe className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
                            )}
                            <span className="truncate">{t.title}</span>
                          </div>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                            {t.type === "webcontainer" ? "React" : "HTML"}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>

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

            {/* WebContainer 文件树查看按钮 */}
            {isWebContainer && (
              <button
                onClick={() => setIsFileTreeExpanded((prev) => !prev)}
                className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-all border ${
                  isFileTreeExpanded
                    ? "bg-indigo-600/30 text-indigo-300 border-indigo-500/40"
                    : "bg-slate-800/80 text-slate-400 hover:text-slate-200 border-slate-700/60"
                }`}
                title="查看 WebContainer 内部文件树"
              >
                <Folder className="w-3.5 h-3.5 text-amber-400" />
                <span>文件树</span>
              </button>
            )}

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

            {/* 重启 WebContainer 服务 */}
            {isWebContainer && (
              <button
                onClick={handleRestartWebContainer}
                disabled={isRestarting || wcStatus === "booting" || wcStatus === "installing"}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-all border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-750 disabled:opacity-50"
                title="重启 WebContainer 服务"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${isRestarting ? "animate-spin text-indigo-400" : "text-amber-400"}`} />
                <span className="hidden sm:inline">重启</span>
              </button>
            )}

            {/* 源码打包下载 ZIP */}
            {sessionId && (
              <button
                onClick={handleDownloadZip}
                disabled={isZipping}
                className="flex items-center gap-1 px-2 py-1 rounded text-xs font-mono transition-all border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-750 disabled:opacity-50"
                title="打包下载当前会话所有源码 (ZIP)"
              >
                {isZipping ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                ) : (
                  <Download className="w-3.5 h-3.5 text-emerald-400" />
                )}
                <span className="hidden sm:inline">ZIP</span>
              </button>
            )}

            {/* 非 WebContainer 模式（纯静态 H5）支持新窗口打开 */}
            {!isWebContainer && activePreviewUrl && (
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

      {/* 主展示区（支持左侧虚拟文件树与右侧页面渲染分栏） */}
      <div className="flex-1 w-full bg-slate-950/90 flex flex-row overflow-hidden relative">
        {/* WebContainer 虚拟文件树面板 */}
        <AnimatePresence>
          {isFileTreeExpanded && isWebContainer && (
            <motion.div
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 260 }}
              exit={{ opacity: 0, width: 0 }}
              transition={{ duration: 0.15 }}
              className="h-full z-10 shrink-0 overflow-hidden relative"
            >
              <WebContainerFileTree
                tree={wcFileTree}
                onRefresh={refreshFileTree}
                onReadFile={readFile}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* 页面渲染区域 */}
        <div className="flex-1 h-full flex flex-col items-center justify-center p-2 overflow-hidden relative">
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
