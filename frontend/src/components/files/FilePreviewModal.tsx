"use client";

import React, { useState, useEffect } from "react";
import { useFileStore } from "@/store/useFileStore";
import { useAuthStore } from "@/store/useAuthStore";
import { api, SANDBOX_BASE } from "@/lib/api";
import {
  X,
  Download,
  ExternalLink,
  Copy,
  Check,
  FileCode,
  Globe,
  ImageIcon,
  FileText,
  Code2,
  Eye,
  Loader2,
} from "lucide-react";
import { useToastStore } from "@/store/useToastStore";
import { CodeBlock } from "@/components/ui/CodeBlock";

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
  const token = useAuthStore((state) => state.token);
  const addToast = useToastStore((state) => state.addToast);

  const [copied, setCopied] = useState(false);
  const [iframeLoading, setIframeLoading] = useState(true);
  const [codeContent, setCodeContent] = useState<string>("");
  const [isCodeLoading, setIsCodeLoading] = useState(false);
  const [htmlViewMode, setHtmlViewMode] = useState<"render" | "source">("render");

  const isCodeOrText =
    previewingFile &&
    (previewingFile.category === "code" ||
      previewingFile.file_path.endsWith(".jsx") ||
      previewingFile.file_path.endsWith(".tsx") ||
      previewingFile.file_path.endsWith(".js") ||
      previewingFile.file_path.endsWith(".ts") ||
      previewingFile.file_path.endsWith(".json") ||
      previewingFile.file_path.endsWith(".py") ||
      previewingFile.file_path.endsWith(".css") ||
      previewingFile.file_path.endsWith(".md") ||
      previewingFile.file_path.endsWith(".txt") ||
      previewingFile.file_path.endsWith(".yaml") ||
      previewingFile.file_path.endsWith(".yml") ||
      previewingFile.file_path.endsWith(".sh"));

  // 构造沙箱直连地址
  const sandboxDirectUrl = previewingFile
    ? `${SANDBOX_BASE}/fs/raw?path=${encodeURIComponent(
        previewingFile.file_path.replace(/^\.?\//, "")
      )}&session_id=${encodeURIComponent(previewingFile.session_id)}`
    : "";

  const previewUrl = sandboxDirectUrl;
  const downloadUrl = `${sandboxDirectUrl}&download=1`;

  // 当预览代码或 HTML 源码时，异步获取文本内容
  useEffect(() => {
    if (!previewingFile) {
      setCodeContent("");
      return;
    }

    if (isCodeOrText || htmlViewMode === "source") {
      let isCancelled = false;
      setIsCodeLoading(true);

      async function fetchText() {
        try {
          // 优先沙箱直连
          let text = "";
          const resp = await fetch(sandboxDirectUrl);
          if (resp.ok) {
            text = await resp.text();
          } else {
            // 回退到后端代理
            const proxyUrl = api.getFilePreviewUrl(
              previewingFile!.session_id,
              previewingFile!.id,
              token
            );
            const proxyResp = await fetch(proxyUrl);
            if (proxyResp.ok) {
              text = await proxyResp.text();
            }
          }

          if (!isCancelled) {
            setCodeContent(text);
          }
        } catch (err) {
          console.error("Failed to load file text", err);
          if (!isCancelled) {
            setCodeContent("// 加载文件内容失败，请检查沙箱网络或权限");
          }
        } finally {
          if (!isCancelled) {
            setIsCodeLoading(false);
          }
        }
      }

      fetchText();

      return () => {
        isCancelled = true;
      };
    }
  }, [previewingFile, sandboxDirectUrl, isCodeOrText, htmlViewMode, token]);

  if (!previewingFile) return null;

  const handleCopyLink = () => {
    navigator.clipboard.writeText(previewUrl);
    setCopied(true);
    addToast({ title: "链接已复制", message: "访问链接已成功复制到剪贴板", type: "success" });
    setTimeout(() => setCopied(false), 2000);
  };

  const getLanguage = () => {
    const p = previewingFile.file_path.toLowerCase();
    if (p.endsWith(".jsx") || p.endsWith(".js")) return "javascript";
    if (p.endsWith(".tsx") || p.endsWith(".ts")) return "typescript";
    if (p.endsWith(".json")) return "json";
    if (p.endsWith(".py")) return "python";
    if (p.endsWith(".css")) return "css";
    if (p.endsWith(".html")) return "html";
    if (p.endsWith(".md")) return "markdown";
    if (p.endsWith(".sh")) return "bash";
    return "text";
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
            {/* HTML 渲染模式与源码模式切换 */}
            {previewingFile.category === "html" && (
              <div className="flex items-center bg-slate-800 p-1 rounded-lg border border-slate-700 mr-2">
                <button
                  onClick={() => setHtmlViewMode("render")}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-all ${
                    htmlViewMode === "render"
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>渲染</span>
                </button>
                <button
                  onClick={() => setHtmlViewMode("source")}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-all ${
                    htmlViewMode === "source"
                      ? "bg-indigo-600 text-white"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Code2 className="w-3.5 h-3.5" />
                  <span>源码</span>
                </button>
              </div>
            )}

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
        <div className="relative flex-1 w-full h-full bg-slate-950 overflow-auto flex items-center justify-center p-4">
          {previewingFile.category === "image" ? (
            <div className="p-6 flex items-center justify-center max-w-full max-h-full">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={previewUrl}
                alt={previewingFile.file_name}
                className="max-w-full max-h-[72vh] object-contain rounded-lg border border-slate-800 shadow-lg"
              />
            </div>
          ) : previewingFile.category === "html" && htmlViewMode === "render" ? (
            <div className="relative w-full h-full">
              {iframeLoading && (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950 text-slate-400 text-xs font-mono gap-2 z-10">
                  <div className="w-3 h-3 rounded-full bg-indigo-500 animate-ping" />
                  <span>正在沙箱加载 HTML 页面...</span>
                </div>
              )}
              <iframe
                key={previewingFile.id}
                srcDoc={codeContent || undefined}
                src={codeContent ? undefined : previewUrl}
                title={previewingFile.file_name}
                allow="cross-origin-isolated; autoplay"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                onLoad={() => setIframeLoading(false)}
                className="w-full h-full border-0 bg-white rounded-xl"
              />
            </div>
          ) : (
            <div className="w-full h-full overflow-auto">
              {isCodeLoading ? (
                <div className="w-full h-full flex items-center justify-center gap-2 text-slate-400 text-xs font-mono">
                  <Loader2 className="w-4 h-4 animate-spin text-indigo-400" />
                  <span>正在从沙箱加载代码...</span>
                </div>
              ) : (
                <div className="h-full overflow-y-auto">
                  <CodeBlock language={getLanguage()} value={codeContent} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
