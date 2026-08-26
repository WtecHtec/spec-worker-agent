"use client";

import React, { useState } from "react";
import {
  Folder,
  FolderOpen,
  FileCode,
  FileText,
  FileJson,
  File,
  ImageIcon,
  ChevronRight,
  ChevronDown,
  RefreshCw,
  Eye,
  X,
  Copy,
  Check,
  Search,
  Download,
  ExternalLink,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { VirtualTreeNode } from "@/lib/webcontainer/webcontainerManager";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { toast } from "@/store/useToastStore";

interface WebContainerFileTreeProps {
  tree: VirtualTreeNode[];
  onRefresh: () => void;
  onReadFile: (path: string) => Promise<string>;
  isLoading?: boolean;
}

function isImageFile(fileName: string): boolean {
  const ext = fileName.split(".").pop()?.toLowerCase() || "";
  return ["png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp"].includes(ext);
}

// 匹配文件图标
function getFileIcon(fileName: string) {
  const ext = fileName.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "png":
    case "jpg":
    case "jpeg":
    case "gif":
    case "svg":
    case "webp":
    case "ico":
    case "bmp":
      return <ImageIcon className="w-3.5 h-3.5 text-pink-400 shrink-0" />;
    case "jsx":
    case "tsx":
    case "js":
    case "ts":
      return <FileCode className="w-3.5 h-3.5 text-cyan-400 shrink-0" />;
    case "html":
      return <FileCode className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
    case "css":
    case "scss":
    case "less":
      return <FileCode className="w-3.5 h-3.5 text-violet-400 shrink-0" />;
    case "json":
      return <FileJson className="w-3.5 h-3.5 text-amber-300 shrink-0" />;
    case "md":
    case "txt":
      return <FileText className="w-3.5 h-3.5 text-slate-300 shrink-0" />;
    default:
      return <File className="w-3.5 h-3.5 text-slate-400 shrink-0" />;
  }
}

function getLanguage(fileName: string): string {
  const ext = fileName.split(".").pop()?.toLowerCase();
  switch (ext) {
    case "jsx":
      return "jsx";
    case "tsx":
      return "tsx";
    case "js":
      return "javascript";
    case "ts":
      return "typescript";
    case "html":
      return "html";
    case "css":
      return "css";
    case "json":
      return "json";
    case "md":
      return "markdown";
    case "svg":
      return "xml";
    default:
      return "plaintext";
  }
}

interface TreeNodeItemProps {
  node: VirtualTreeNode;
  depth: number;
  onSelectFile: (path: string, fileName: string) => void;
}

const TreeNodeItem: React.FC<TreeNodeItemProps> = ({
  node,
  depth,
  onSelectFile,
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(depth < 2); // 默认前两层展开

  if (node.isDirectory) {
    return (
      <div className="w-full">
        <button
          onClick={() => setIsOpen((prev) => !prev)}
          style={{ paddingLeft: `${depth * 12 + 6}px` }}
          className="w-full flex items-center gap-1.5 py-1.5 pr-2 hover:bg-slate-800/80 rounded-md text-xs text-slate-300 font-mono transition-colors group text-left"
          title={node.name}
        >
          {isOpen ? (
            <ChevronDown className="w-3 h-3 text-slate-500 group-hover:text-slate-300 shrink-0" />
          ) : (
            <ChevronRight className="w-3 h-3 text-slate-500 group-hover:text-slate-300 shrink-0" />
          )}
          {isOpen ? (
            <FolderOpen className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          ) : (
            <Folder className="w-3.5 h-3.5 text-amber-400/80 shrink-0" />
          )}
          <span className="truncate font-medium group-hover:text-white flex-1 min-w-0">
            {node.name}
          </span>
        </button>

        {isOpen && node.children && (
          <div className="space-y-0.5 w-full">
            {node.children.map((child) => (
              <TreeNodeItem
                key={child.path}
                node={child}
                depth={depth + 1}
                onSelectFile={onSelectFile}
              />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <button
      onClick={() => onSelectFile(node.path, node.name)}
      style={{ paddingLeft: `${depth * 12 + 18}px` }}
      className="w-full flex items-center justify-between py-1.5 pr-2 hover:bg-indigo-950/50 hover:text-indigo-200 rounded-md text-xs text-slate-300 font-mono transition-colors group text-left"
      title={node.name}
    >
      <div className="flex items-center gap-1.5 min-w-0 flex-1">
        {getFileIcon(node.name)}
        <span className="truncate group-hover:text-white flex-1">{node.name}</span>
      </div>
      <Eye className="w-3 h-3 opacity-0 group-hover:opacity-100 text-indigo-400 transition-opacity shrink-0 ml-1" />
    </button>
  );
};

export const WebContainerFileTree: React.FC<WebContainerFileTreeProps> = ({
  tree,
  onRefresh,
  onReadFile,
  isLoading = false,
}) => {
  const [selectedFile, setSelectedFile] = useState<{
    path: string;
    fileName: string;
    content: string;
    isImage: boolean;
  } | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [filterText, setFilterText] = useState<string>("");
  const [svgViewMode, setSvgViewMode] = useState<"image" | "code">("image");

  const handleSelectFile = async (path: string, fileName: string) => {
    try {
      const isImg = isImageFile(fileName);
      const content = await onReadFile(path);
      setSvgViewMode("image");
      setSelectedFile({ path, fileName, content, isImage: isImg });
    } catch (err: any) {
      toast.error(err.message || "读取虚拟文件失败", "读取异常");
    }
  };

  const handleCopy = () => {
    if (!selectedFile?.content) return;
    navigator.clipboard.writeText(selectedFile.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
    toast.success("内容已复制到剪贴板！", "复制成功");
  };

  const handleDownloadImage = () => {
    if (!selectedFile) return;
    const a = document.createElement("a");
    a.href = selectedFile.content.startsWith("data:")
      ? selectedFile.content
      : `data:image/svg+xml;utf8,${encodeURIComponent(selectedFile.content)}`;
    a.download = selectedFile.fileName;
    a.click();
    toast.success("图片下载已触发！", "下载图片");
  };

  // 递归过滤
  const filterTree = (nodes: VirtualTreeNode[], query: string): VirtualTreeNode[] => {
    if (!query) return nodes;
    const lower = query.toLowerCase();

    return nodes
      .map((node) => {
        if (node.isDirectory) {
          const filteredChildren = filterTree(node.children || [], query);
          if (filteredChildren.length > 0 || node.name.toLowerCase().includes(lower)) {
            return { ...node, children: filteredChildren };
          }
          return null;
        }
        return node.name.toLowerCase().includes(lower) ? node : null;
      })
      .filter(Boolean) as VirtualTreeNode[];
  };

  const filteredNodes = filterTree(tree, filterText);

  return (
    <div className="flex flex-col h-full bg-slate-950/95 border-r border-slate-800 w-full font-sans select-none text-xs min-w-[240px]">
      {/* 头部标题与刷新 */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-800 bg-slate-900/80 shrink-0">
        <div className="flex items-center gap-1.5 font-semibold text-slate-200 truncate">
          <Folder className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
          <span className="truncate">WebContainer 文件树</span>
        </div>
        <button
          onClick={onRefresh}
          disabled={isLoading}
          className="p-1 hover:text-white text-slate-400 rounded hover:bg-slate-800 transition-colors disabled:opacity-50 shrink-0 ml-1"
          title="刷新虚拟文件树"
        >
          <RefreshCw className={`w-3 h-3 ${isLoading ? "animate-spin text-indigo-400" : ""}`} />
        </button>
      </div>

      {/* 搜索框 */}
      <div className="p-2 border-b border-slate-800/80 shrink-0">
        <div className="relative flex items-center">
          <Search className="w-3 h-3 absolute left-2 text-slate-500" />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="搜索虚拟文件/图片..."
            className="w-full pl-6 pr-2 py-1 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500/50"
          />
        </div>
      </div>

      {/* 树形列表区 */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden p-1.5 space-y-0.5">
        {filteredNodes.length === 0 ? (
          <div className="py-8 text-center text-slate-500 font-mono text-[11px] px-2">
            {isLoading ? "正在读取虚拟文件系统..." : "暂无文件或未完成挂载"}
          </div>
        ) : (
          filteredNodes.map((node) => (
            <TreeNodeItem
              key={node.path}
              node={node}
              depth={0}
              onSelectFile={handleSelectFile}
            />
          ))
        )}
      </div>

      {/* 全局大弹窗查看文件 / 图片内容 */}
      <AnimatePresence>
        {selectedFile && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/80 backdrop-blur-md animate-in fade-in duration-200">
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.96 }}
              transition={{ duration: 0.15 }}
              className="relative w-full max-w-4xl max-h-[85vh] flex flex-col bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl overflow-hidden"
            >
              {/* 弹窗顶栏 */}
              <div className="flex items-center justify-between px-4 py-3 bg-slate-950 border-b border-slate-800 text-xs">
                <div className="flex items-center gap-2 min-w-0 font-mono">
                  {getFileIcon(selectedFile.fileName)}
                  <span className="font-semibold text-slate-200 truncate">
                    {selectedFile.path}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 uppercase font-sans">
                    {selectedFile.isImage ? "IMAGE" : getLanguage(selectedFile.fileName)}
                  </span>
                </div>

                <div className="flex items-center gap-1.5">
                  {/* 如果是 SVG，支持在渲染图与源码之间切换 */}
                  {selectedFile.fileName.endsWith(".svg") && (
                    <div className="flex items-center bg-slate-800 p-0.5 rounded-lg border border-slate-700 mr-1">
                      <button
                        onClick={() => setSvgViewMode("image")}
                        className={`px-2 py-0.5 rounded text-[11px] font-sans transition-all ${
                          svgViewMode === "image"
                            ? "bg-indigo-600 text-white"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        预览图
                      </button>
                      <button
                        onClick={() => setSvgViewMode("code")}
                        className={`px-2 py-0.5 rounded text-[11px] font-sans transition-all ${
                          svgViewMode === "code"
                            ? "bg-indigo-600 text-white"
                            : "text-slate-400 hover:text-slate-200"
                        }`}
                      >
                        SVG 代码
                      </button>
                    </div>
                  )}

                  {selectedFile.isImage ? (
                    <button
                      onClick={handleDownloadImage}
                      className="flex items-center gap-1 px-2.5 py-1 text-slate-300 hover:text-white rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors"
                      title="保存图片"
                    >
                      <Download className="w-3.5 h-3.5 text-pink-400" />
                      <span className="text-[11px] font-sans">保存</span>
                    </button>
                  ) : (
                    <button
                      onClick={handleCopy}
                      className="flex items-center gap-1 px-2 py-1 text-slate-300 hover:text-white rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors"
                      title="复制全文"
                    >
                      {copied ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                      <span className="text-[11px] font-sans">{copied ? "已复制" : "复制"}</span>
                    </button>
                  )}

                  <button
                    onClick={() => setSelectedFile(null)}
                    className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-rose-500/20 transition-colors ml-1"
                    title="关闭"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* 弹窗内容展示区：区分图片 vs 代码 */}
              {selectedFile.isImage && (!selectedFile.fileName.endsWith(".svg") || svgViewMode === "image") ? (
                <div className="flex-1 min-h-[300px] flex items-center justify-center p-6 bg-slate-950/80 overflow-auto bg-[radial-gradient(#334155_1px,transparent_1px)] [background-size:16px_16px]">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={
                      selectedFile.content.startsWith("data:")
                        ? selectedFile.content
                        : `data:image/svg+xml;utf8,${encodeURIComponent(selectedFile.content)}`
                    }
                    alt={selectedFile.fileName}
                    className="max-w-full max-h-[65vh] object-contain rounded-lg border border-slate-800 shadow-2xl bg-black/40 p-2"
                  />
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto p-4 font-mono text-xs select-text bg-slate-950/60">
                  <CodeBlock
                    language={getLanguage(selectedFile.fileName)}
                    value={selectedFile.content}
                  />
                </div>
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
