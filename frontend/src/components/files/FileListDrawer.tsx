"use client";

import React, { useState, useEffect, useMemo } from "react";
import { useFileStore } from "@/store/useFileStore";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useToastStore } from "@/store/useToastStore";
import { FileCategory, SessionFile } from "@/types/file";
import {
  X,
  RefreshCw,
  Search,
  Settings2,
  FileCode,
  FileText,
  Image as ImageIcon,
  Globe,
  Download,
  Eye,
  Trash2,
  FolderArchive,
  Check,
  Server,
  Layers,
} from "lucide-react";
import { api } from "@/lib/api";

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function formatDate(isoStr?: string): string {
  if (!isoStr) return "";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

export const FileListDrawer: React.FC = () => {
  const isDrawerOpen = useFileStore((state) => state.isDrawerOpen);
  const closeDrawer = useFileStore((state) => state.closeDrawer);
  const files = useFileStore((state) => state.files);
  const total = useFileStore((state) => state.total);
  const isLoading = useFileStore((state) => state.isLoading);
  const activeCategory = useFileStore((state) => state.activeCategory);
  const setCategory = useFileStore((state) => state.setCategory);
  const fetchFiles = useFileStore((state) => state.fetchFiles);
  const openPreview = useFileStore((state) => state.openPreview);
  const deleteFile = useFileStore((state) => state.deleteFile);
  const customDomain = useFileStore((state) => state.customDomain);
  const setCustomDomain = useFileStore((state) => state.setCustomDomain);
  const initSettings = useFileStore((state) => state.initSettings);

  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const token = useAuthStore((state) => state.token);
  const addToast = useToastStore((state) => state.addToast);

  const [searchQuery, setSearchQuery] = useState("");
  const [showConfig, setShowConfig] = useState(false);
  const [tempDomain, setTempDomain] = useState(customDomain);

  useEffect(() => {
    initSettings();
  }, [initSettings]);

  useEffect(() => {
    setTempDomain(customDomain);
  }, [customDomain]);

  useEffect(() => {
    if (isDrawerOpen && currentSessionId && token) {
      fetchFiles(currentSessionId, token, activeCategory);
    }
  }, [isDrawerOpen, currentSessionId, token, activeCategory, fetchFiles]);

  const handleRefresh = () => {
    if (currentSessionId && token) {
      fetchFiles(currentSessionId, token, activeCategory);
    }
  };

  const handleSaveDomain = () => {
    setCustomDomain(tempDomain.trim());
    setShowConfig(false);
    addToast({
      title: "配置已保存",
      message: tempDomain.trim()
        ? `文件访问域名已更新为: ${tempDomain.trim()}`
        : "已切换为默认后端代理安全模式",
      type: "success",
    });
  };

  const handleDelete = async (file: SessionFile, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!currentSessionId || !token) return;
    if (confirm(`确定要从会话列表中移除文件 [${file.file_name}] 吗？`)) {
      try {
        await deleteFile(currentSessionId, file.id, token);
        addToast({ title: "已删除", message: `文件 ${file.file_name} 已移除`, type: "info" });
      } catch (err: any) {
        addToast({ title: "删除失败", message: err.message || "无法删除文件", type: "error" });
      }
    }
  };

  const filteredFiles = useMemo(() => {
    if (!searchQuery.trim()) return files;
    const q = searchQuery.toLowerCase();
    return files.filter(
      (f) =>
        f.file_name.toLowerCase().includes(q) ||
        f.file_path.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q)
    );
  }, [files, searchQuery]);

  const categories: { id: FileCategory; label: string; icon: any }[] = [
    { id: "all", label: "全部", icon: Layers },
    { id: "html", label: "网页", icon: Globe },
    { id: "image", label: "截图/图片", icon: ImageIcon },
    { id: "code", label: "代码", icon: FileCode },
    { id: "document", label: "文档", icon: FileText },
  ];

  if (!isDrawerOpen) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/60 backdrop-blur-sm animate-in fade-in duration-200">
      {/* 遮罩背景点击关闭 */}
      <div className="absolute inset-0" onClick={closeDrawer} />

      {/* 抽屉面板 */}
      <div className="relative w-full max-w-md h-full bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col z-10 animate-in slide-in-from-right duration-300">
        {/* Header */}
        <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/70 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
              <FolderArchive className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-slate-100">会话产出文件</h3>
                <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                  {total}
                </span>
              </div>
              <p className="text-[11px] text-slate-400">查看并下载会话中生成的所有资产</p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              onClick={() => setShowConfig(!showConfig)}
              title="配置访问域名"
              className={`p-2 rounded-lg transition-colors ${
                showConfig || customDomain
                  ? "text-indigo-400 bg-indigo-500/10"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              }`}
            >
              <Settings2 className="w-4 h-4" />
            </button>

            <button
              onClick={handleRefresh}
              title="刷新文件列表"
              className={`p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors ${
                isLoading ? "animate-spin text-indigo-400" : ""
              }`}
            >
              <RefreshCw className="w-4 h-4" />
            </button>

            <button
              onClick={closeDrawer}
              title="关闭抽屉"
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 访问域名设置面板 (可折叠) */}
        {showConfig && (
          <div className="p-4 bg-slate-950/90 border-b border-slate-800 animate-in slide-in-from-top-2 duration-200">
            <div className="flex items-center gap-2 mb-2 text-xs font-semibold text-slate-200">
              <Server className="w-4 h-4 text-indigo-400" />
              <span>文件访问域名配置</span>
            </div>
            <p className="text-[11px] text-slate-400 mb-3 leading-relaxed">
              默认为空时自动走业务后端统一代理（安全隔离 VPC 沙箱）。若沙箱配置了独立公网域名，可在此填入自定义
              Host（如 <code>http://sandbox.lan:8080</code>）。
            </p>
            <div className="flex items-center gap-2">
              <input
                type="text"
                placeholder="默认代理 (留空)"
                value={tempDomain}
                onChange={(e) => setTempDomain(e.target.value)}
                className="flex-1 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 font-mono"
              />
              <button
                onClick={handleSaveDomain}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors shrink-0"
              >
                <Check className="w-3.5 h-3.5" />
                <span>保存</span>
              </button>
            </div>
          </div>
        )}

        {/* 分类标签栏 */}
        <div className="px-4 py-2 border-b border-slate-800 flex items-center gap-1.5 overflow-x-auto bg-slate-950/40 shrink-0">
          {categories.map((cat) => {
            const Icon = cat.icon;
            const isActive = activeCategory === cat.id;
            return (
              <button
                key={cat.id}
                onClick={() => setCategory(cat.id)}
                className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-colors shrink-0 ${
                  isActive
                    ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                <span>{cat.label}</span>
              </button>
            );
          })}
        </div>

        {/* 搜索框 */}
        <div className="p-3 border-b border-slate-800/80 shrink-0">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="搜索文件名或路径..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>
        </div>

        {/* 文件列表 */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {isLoading && files.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-slate-500 text-xs font-mono gap-2">
              <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
              <span>正在加载文件列表...</span>
            </div>
          ) : filteredFiles.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-slate-500 text-xs text-center px-4">
              <FolderArchive className="w-8 h-8 text-slate-600 mb-2 stroke-[1.5]" />
              <p className="font-medium text-slate-400">暂无产出文件</p>
              <p className="text-[11px] text-slate-600 mt-1">
                当 Agent 在该会话生成网页、代码或截图时将自动显示在此处
              </p>
            </div>
          ) : (
            filteredFiles.map((file) => {
              const downloadUrl = api.getFileDownloadUrl(
                file.session_id,
                file.id,
                token,
                customDomain || undefined
              );

              return (
                <div
                  key={file.id}
                  onClick={() => openPreview(file)}
                  className="group relative p-3 rounded-xl bg-slate-950/60 hover:bg-slate-800/70 border border-slate-800/80 hover:border-slate-700 transition-all cursor-pointer flex items-center justify-between gap-3"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 group-hover:text-indigo-400 transition-colors shrink-0">
                      {file.category === "html" ? (
                        <Globe className="w-4 h-4 text-indigo-400" />
                      ) : file.category === "image" ? (
                        <ImageIcon className="w-4 h-4 text-emerald-400" />
                      ) : file.category === "code" ? (
                        <FileCode className="w-4 h-4 text-amber-400" />
                      ) : (
                        <FileText className="w-4 h-4 text-sky-400" />
                      )}
                    </div>

                    <div className="min-w-0">
                      <p className="text-xs font-semibold text-slate-200 truncate group-hover:text-white">
                        {file.file_name}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5 text-[10px] text-slate-500 font-mono">
                        <span>{formatBytes(file.file_size)}</span>
                        <span>•</span>
                        <span>{formatDate(file.updated_at || file.created_at)}</span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0 opacity-80 group-hover:opacity-100">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        openPreview(file);
                      }}
                      title="预览"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-300 hover:bg-slate-800 transition-colors"
                    >
                      <Eye className="w-3.5 h-3.5" />
                    </button>

                    <a
                      href={downloadUrl}
                      download={file.file_name}
                      onClick={(e) => e.stopPropagation()}
                      title="下载"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-300 hover:bg-slate-800 transition-colors"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </a>

                    <button
                      onClick={(e) => handleDelete(file, e)}
                      title="删除"
                      className="p-1.5 rounded-lg text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
