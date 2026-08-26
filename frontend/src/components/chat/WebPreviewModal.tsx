"use client";

import React, { useState } from "react";
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
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface WebPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  previewUrl: string;
  title?: string;
  fileName?: string;
}

type ViewportMode = "desktop" | "tablet" | "mobile";

export const WebPreviewModal: React.FC<WebPreviewModalProps> = ({
  isOpen,
  onClose,
  previewUrl,
  title = "Web 页面预览",
  fileName = "index.html",
}) => {
  const [viewport, setViewport] = useState<ViewportMode>("desktop");
  const [refreshKey, setRefreshKey] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);

  if (!isOpen) return null;

  const handleRefresh = () => {
    setIsLoading(true);
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
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
                    {fileName}
                  </span>
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
                <a
                  href={previewUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-1.5 text-slate-400 hover:text-indigo-300 hover:bg-slate-800 rounded-lg transition-colors"
                  title="新标签页打开"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>
                <button
                  onClick={onClose}
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
                    isLoading ? "animate-spin text-indigo-400" : ""
                  }`}
                  title="重新加载页面"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* 模拟 URL 栏 */}
              <div className="flex-1 flex items-center gap-2 px-3 py-1 bg-slate-900/90 border border-slate-800 rounded-lg text-xs text-slate-300 font-mono select-all">
                <Lock className="w-3 h-3 text-emerald-400 shrink-0" />
                <span className="text-slate-400">http://localhost:3000/preview/</span>
                <span className="text-indigo-300 font-semibold">{fileName}</span>
              </div>
            </div>
          </div>

          {/* 核心展示区：自适应设备视口 */}
          <div className="flex-1 w-full bg-slate-950/90 flex items-center justify-center p-2 sm:p-4 overflow-hidden relative">
            <div
              className={`w-full h-full ${getViewportWidth()} transition-all duration-300 shadow-2xl relative flex flex-col bg-white rounded-xl overflow-hidden border border-slate-800`}
            >
              {/* 加载等待遮罩 */}
              {isLoading && (
                <div className="absolute inset-0 z-10 flex flex-col items-center justify-center bg-slate-900/90 backdrop-blur-sm gap-3">
                  <div className="w-8 h-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
                  <p className="text-xs text-slate-400 font-mono animate-pulse">
                    正在加载实时页面...
                  </p>
                </div>
              )}

              {/* 沙箱隔离 iframe */}
              <iframe
                key={refreshKey}
                src={previewUrl}
                title={title}
                sandbox="allow-scripts allow-forms allow-same-origin allow-modals"
                className="w-full h-full border-0 bg-white"
                onLoad={() => setIsLoading(false)}
              />
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
};
