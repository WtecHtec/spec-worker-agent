"use client";

import React, { useState, useEffect } from "react";
import {
  X,
  History,
  GitCommit,
  Clock,
  FileCode,
  Copy,
  Check,
  Loader2,
  ChevronRight,
  ArrowLeft,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/useAuthStore";
import { useToastStore } from "@/store/useToastStore";

interface FileDiffModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId: string;
  fileId: string;
  fileName: string;
}

export const FileDiffModal: React.FC<FileDiffModalProps> = ({
  isOpen,
  onClose,
  sessionId,
  fileId,
  fileName,
}) => {
  const token = useAuthStore((state) => state.token);
  const addToast = useToastStore((state) => state.addToast);

  const [versions, setVersions] = useState<any[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (isOpen && fileId && sessionId) {
      let isCancelled = false;
      setIsLoading(true);

      async function fetchVersions() {
        try {
          const list = await api.getFileVersions(sessionId, fileId, token || "");
          if (!isCancelled) {
            setVersions(list || []);
            if (list && list.length > 0) {
              setSelectedVersion(list[0]);
            }
          }
        } catch (err) {
          console.error("Failed to fetch file versions", err);
        } finally {
          if (!isCancelled) {
            setIsLoading(false);
          }
        }
      }

      fetchVersions();

      return () => {
        isCancelled = true;
      };
    }
  }, [isOpen, sessionId, fileId, token]);

  if (!isOpen) return null;

  const handleCopyDiff = () => {
    if (selectedVersion?.diff_content) {
      navigator.clipboard.writeText(selectedVersion.diff_content);
      setCopied(true);
      addToast({ title: "Diff 已复制", message: "版本差异内容已复制到剪贴板", type: "success" });
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const renderDiffLines = (diffText?: string) => {
    if (!diffText) {
      return (
        <div className="p-8 text-center text-slate-500 font-mono text-xs">
          当前版本无增量 Diff 记录或为初始版本
        </div>
      );
    }

    const lines = diffText.split("\n");
    return (
      <div className="font-mono text-xs leading-relaxed overflow-x-auto p-4 select-text">
        {lines.map((line, idx) => {
          let lineStyle = "text-slate-300";
          let bgStyle = "";
          if (line.startsWith("+") && !line.startsWith("+++")) {
            lineStyle = "text-emerald-400 font-semibold";
            bgStyle = "bg-emerald-950/40 border-l-2 border-emerald-500 pl-1.5";
          } else if (line.startsWith("-") && !line.startsWith("---")) {
            lineStyle = "text-rose-400 font-semibold";
            bgStyle = "bg-rose-950/40 border-l-2 border-rose-500 pl-1.5";
          } else if (line.startsWith("@@")) {
            lineStyle = "text-indigo-400 font-bold bg-indigo-950/40 py-0.5 px-1 rounded";
          }

          return (
            <div key={idx} className={`whitespace-pre py-0.5 ${lineStyle} ${bgStyle}`}>
              {line || " "}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/85 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-5xl h-[85vh] flex flex-col bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* 顶部标题栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/80">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400">
              <History className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-slate-100 flex items-center gap-2">
                版本历史与 Diff 追溯
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700">
                  {fileName}
                </span>
              </h3>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                追踪每次文件修改的 Unified Diff 补丁与改动版本
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {selectedVersion?.diff_content && (
              <button
                onClick={handleCopyDiff}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium border border-slate-700 transition-colors"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>复制 Diff</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors ml-2"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* 主体左右双栏 */}
        <div className="flex-1 flex overflow-hidden">
          {/* 左侧版本列表 */}
          <div className="w-64 border-r border-slate-800 bg-slate-950/50 flex flex-col shrink-0">
            <div className="px-4 py-2.5 border-b border-slate-800 text-xs font-semibold text-slate-400 uppercase tracking-wider font-mono">
              版本列表 ({versions.length})
            </div>

            <div className="flex-1 overflow-y-auto p-2 space-y-1">
              {isLoading ? (
                <div className="flex items-center justify-center p-6 text-slate-500 gap-2 text-xs font-mono">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                  <span>加载版本中...</span>
                </div>
              ) : versions.length === 0 ? (
                <div className="p-6 text-center text-slate-500 font-mono text-xs">
                  暂无历史版本记录
                </div>
              ) : (
                versions.map((ver) => {
                  const isSelected = selectedVersion?.id === ver.id;
                  return (
                    <button
                      key={ver.id}
                      onClick={() => setSelectedVersion(ver)}
                      className={`w-full text-left p-3 rounded-xl transition-all border ${
                        isSelected
                          ? "bg-indigo-600/20 border-indigo-500/50 text-indigo-200 shadow-sm"
                          : "bg-slate-900/60 border-slate-800/80 text-slate-400 hover:bg-slate-850 hover:text-slate-200"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold flex items-center gap-1.5">
                          <GitCommit className="w-3.5 h-3.5 text-indigo-400" />
                          v{ver.version_num}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {ver.file_size} B
                        </span>
                      </div>
                      <p className="text-xs text-slate-300 font-sans mt-1 truncate">
                        {ver.summary || `第 ${ver.version_num} 版改动`}
                      </p>
                      <div className="flex items-center gap-1 text-[10px] text-slate-500 font-mono mt-1">
                        <Clock className="w-3 h-3" />
                        <span>{new Date(ver.created_at).toLocaleTimeString()}</span>
                      </div>
                    </button>
                  );
                })
              )}
            </div>
          </div>

          {/* 右侧 Diff 查看区 */}
          <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
            {selectedVersion && (
              <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between text-xs font-mono text-slate-400">
                <div className="flex items-center gap-2">
                  <span className="text-emerald-400 font-semibold">+ 增加</span>
                  <span className="text-rose-400 font-semibold">- 删除</span>
                  <span>• 当前查看: v{selectedVersion.version_num}</span>
                </div>
                <span>Version ID: {selectedVersion.id.slice(0, 8)}</span>
              </div>
            )}

            <div className="flex-1 overflow-y-auto bg-black/40">
              {renderDiffLines(selectedVersion?.diff_content)}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
