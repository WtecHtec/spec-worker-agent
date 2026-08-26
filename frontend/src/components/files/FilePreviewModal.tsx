"use client";

import React, { useState } from "react";
import { useFileStore } from "@/store/useFileStore";
import { useAuthStore } from "@/store/useAuthStore";
import { api } from "@/lib/api";
import {
  X,
  Download,
  ExternalLink,
  Copy,
  Check,
  FileCode,
  FileText,
  Image as ImageIcon,
  Globe,
  FileBox,
} from "lucide-react";
import { useToastStore } from "@/store/useToastStore";

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

export const FilePreviewModal: React.FC = () => {
  const previewingFile = useFileStore((state) => state.previewingFile);
  const closePreview = useFileStore((state) => state.closePreview);
  const customDomain = useFileStore((state) => state.customDomain);
  const token = useAuthStore((state) => state.token);
  const addToast = useToastStore((state) => state.addToast);

  const [copied, setCopied] = useState(false);
  const [iframeLoading, setIframeLoading] = useState(true);

  if (!previewingFile) return null;

  const previewUrl = api.getFilePreviewUrl(
    previewingFile.session_id,
    previewingFile.id,
    token,
    customDomain || undefined
  );

  const downloadUrl = api.getFileDownloadUrl(
    previewingFile.session_id,
    previewingFile.id,
    token,
    customDomain || undefined
  );

  const handleCopyLink = () => {
    navigator.clipboard.writeText(previewUrl);
    setCopied(true);
    addToast({ title: "链接已复制", message: "预览链接已成功复制到剪贴板", type: "success" });
    setTimeout(() => setCopied(false), 2000);
  };

  const getCategoryIcon = () => {
    switch (previewingFile.category) {
      case "html":
        return <Globe className="w-5 h-5 text-indigo-400" />;
      case "image":
        return <ImageIcon className="w-5 h-5 text-emerald-400" />;
      case "code":
        return <FileCode className="w-5 h-5 text-amber-400" />;
      default:
        return <FileText className="w-5 h-5 text-sky-400" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
      <div className="relative w-full max-w-5xl h-[88vh] flex flex-col bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800/80 bg-slate-950/60 shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <div className="p-2 rounded-xl bg-slate-800/80 border border-slate-700/50">
              {getCategoryIcon()}
            </div>
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-slate-100 truncate flex items-center gap-2">
                {previewingFile.file_name}
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-400 uppercase">
                  {previewingFile.category}
                </span>
              </h3>
              <p className="text-xs text-slate-400 font-mono flex items-center gap-2">
                <span>{previewingFile.file_path}</span>
                <span>•</span>
                <span>{formatBytes(previewingFile.file_size)}</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleCopyLink}
              title="复制访问链接"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium transition-colors border border-slate-700/60"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              <span>{copied ? "已复制" : "复制链接"}</span>
            </button>

            <a
              href={downloadUrl}
              download={previewingFile.file_name}
              title="下载文件"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 hover:text-indigo-200 text-xs font-medium transition-colors border border-indigo-500/30"
            >
              <Download className="w-3.5 h-3.5" />
              <span>下载</span>
            </a>

            <a
              href={previewUrl}
              target="_blank"
              rel="noreferrer"
              title="新窗口打开"
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            >
              <ExternalLink className="w-4 h-4" />
            </a>

            <button
              onClick={closePreview}
              title="关闭预览"
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors ml-2"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Preview Body */}
        <div className="relative flex-1 w-full h-full bg-slate-950 overflow-auto flex items-center justify-center">
          {previewingFile.category === "image" ? (
            <div className="p-6 flex items-center justify-center max-w-full max-h-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl}
                alt={previewingFile.file_name}
                className="max-w-full max-h-[72vh] object-contain rounded-lg border border-slate-800 shadow-lg"
              />
            </div>
          ) : previewingFile.category === "html" ? (
            <div className="relative w-full h-full">
              {iframeLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950 text-slate-400 text-xs font-mono gap-2 z-10">
                  <div className="w-3 h-3 rounded-full bg-indigo-500 animate-ping" />
                  <span>正在沙箱加载 HTML 页面...</span>
                </div>
              )}
              <iframe
                src={previewUrl}
                title={previewingFile.file_name}
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                onLoad={() => setIframeLoading(false)}
                className="w-full h-full border-0 bg-white"
              />
            </div>
          ) : (
            <div className="w-full h-full p-4">
              <iframe
                src={previewUrl}
                title={previewingFile.file_name}
                className="w-full h-full rounded-lg border border-slate-800 bg-slate-900 text-slate-200"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
