"use client";

import React, { useState } from "react";
import { Play, ExternalLink, Globe, Sparkles, CheckCircle2, Layers, Package } from "lucide-react";
import { WebPreviewModal } from "./WebPreviewModal";

interface WebPreviewCardProps {
  fileName?: string;
  previewUrl: string;
  title?: string;
  description?: string;
  sessionId?: string;
  isWebContainer?: boolean;
}

export const WebPreviewCard: React.FC<WebPreviewCardProps> = ({
  fileName = "index.html",
  previewUrl,
  title = "Web 实时应用",
  description = "已生成可交互的前端网页应用，支持在沙箱环境中即时运行与体验。",
  sessionId,
  isWebContainer = false,
}) => {
  const [isModalOpen, setIsModalOpen] = useState(false);

  const isNPMProject = isWebContainer || fileName.includes("package.json");

  return (
    <>
      <div className="my-3 overflow-hidden rounded-xl border border-indigo-500/30 bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-slate-950/80 p-4 backdrop-blur-md shadow-lg shadow-indigo-950/20 transition-all hover:border-indigo-500/50">
        {/* 卡片头部 */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 shrink-0 shadow-inner">
              {isNPMProject ? (
                <Package className="w-4 h-4 text-violet-400" />
              ) : (
                <Globe className="w-4 h-4 text-indigo-400" />
              )}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-100 text-sm truncate">{title}</span>
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <CheckCircle2 className="w-2.5 h-2.5" />
                  Ready
                </span>
                {isNPMProject && (
                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-violet-500/15 text-violet-300 border border-violet-500/20">
                    <Layers className="w-2.5 h-2.5" />
                    WebContainer
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5 truncate">{fileName}</p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <span className="inline-flex items-center gap-1 text-[11px] text-indigo-300/80 font-mono">
              <Sparkles className="w-3 h-3 text-indigo-400" />
              Live
            </span>
          </div>
        </div>

        {/* 描述说明 */}
        <p className="text-xs text-slate-300 leading-relaxed mt-2.5 font-sans line-clamp-2">
          {description}
        </p>

        {/* 底部操作条 */}
        <div className="mt-3.5 pt-3 border-t border-slate-800/80 flex items-center justify-between gap-2">
          <button
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-gradient-to-r from-indigo-600 to-indigo-700 hover:from-indigo-500 hover:to-indigo-600 text-white text-xs font-medium shadow-md shadow-indigo-900/30 transition-all active:scale-[0.98]"
          >
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>实时预览</span>
          </button>

          {!isNPMProject && previewUrl && (
            <a
              href={previewUrl}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-800/70 hover:bg-slate-800 text-slate-300 hover:text-indigo-300 text-xs font-medium border border-slate-700/60 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>新标签页打开</span>
            </a>
          )}
        </div>
      </div>

      {/* 弹窗 */}
      <WebPreviewModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        previewUrl={previewUrl}
        fileName={fileName}
        title={title}
        sessionId={sessionId}
        isWebContainer={isNPMProject}
      />
    </>
  );
};
