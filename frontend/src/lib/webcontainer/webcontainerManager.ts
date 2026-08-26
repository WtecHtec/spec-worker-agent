import { WebContainer, FileSystemTree, WebContainerProcess } from "@webcontainer/api";

export interface VirtualFile {
  file_path: string;
  content: string;
}

export type WebContainerStatus =
  | "idle"
  | "booting"
  | "mounting"
  | "installing"
  | "starting"
  | "ready"
  | "error";

export interface DevServerCallbacks {
  onStatusChange?: (status: WebContainerStatus) => void;
  onLog?: (log: string) => void;
  onServerReady?: (port: number, url: string) => void;
  onError?: (error: string) => void;
}

declare global {
  // eslint-disable-next-line no-var
  var __webcontainer_instance__: WebContainer | undefined;
  // eslint-disable-next-line no-var
  var __webcontainer_boot_promise__: Promise<WebContainer> | undefined;
  // eslint-disable-next-line no-var
  var __webcontainer_manager_instance__: WebContainerManager | undefined;
}

class WebContainerManager {
  private static instance: WebContainerManager | null = null;
  private webcontainer: WebContainer | null = null;
  private bootPromise: Promise<WebContainer> | null = null;
  private activeDevProcess: WebContainerProcess | null = null;
  private activeInstallProcess: WebContainerProcess | null = null;
  private currentSessionId: string | null = null;
  private serverUrl: string | null = null;
  private serverPort: number | null = null;

  private constructor() {}

  public static getInstance(): WebContainerManager {
    if (typeof globalThis !== "undefined" && globalThis.__webcontainer_manager_instance__) {
      return globalThis.__webcontainer_manager_instance__;
    }
    if (!WebContainerManager.instance) {
      WebContainerManager.instance = new WebContainerManager();
    }
    if (typeof globalThis !== "undefined") {
      globalThis.__webcontainer_manager_instance__ = WebContainerManager.instance;
    }
    return WebContainerManager.instance;
  }

  /**
   * 检查当前浏览器环境是否支持 WebContainer (依赖 SharedArrayBuffer 与 crossOriginIsolated)
   */
  public isSupported(): boolean {
    if (typeof window === "undefined") return false;
    return typeof SharedArrayBuffer !== "undefined" && Boolean(window.crossOriginIsolated);
  }

  /**
   * 单例启动 WebContainer 虚拟内核（支持 Next.js HMR 全局单例保护）
   */
  public async getWebContainer(): Promise<WebContainer> {
    if (typeof globalThis !== "undefined" && globalThis.__webcontainer_instance__) {
      this.webcontainer = globalThis.__webcontainer_instance__;
      return this.webcontainer;
    }
    if (this.webcontainer) {
      return this.webcontainer;
    }

    if (typeof globalThis !== "undefined" && globalThis.__webcontainer_boot_promise__) {
      this.bootPromise = globalThis.__webcontainer_boot_promise__;
      return this.bootPromise;
    }
    if (this.bootPromise) {
      return this.bootPromise;
    }

    if (!this.isSupported()) {
      throw new Error(
        "当前浏览器或网络环境未启用跨域隔离 (SharedArrayBuffer)。请确保使用现代浏览器并允许跨域安全头 (COOP/COEP)。"
      );
    }

    this.bootPromise = (async () => {
      try {
        const wc = await WebContainer.boot();
        this.webcontainer = wc;
        if (typeof globalThis !== "undefined") {
          globalThis.__webcontainer_instance__ = wc;
        }
        return wc;
      } catch (err: any) {
        // 如果报错提示已经 boot 过了（例如 Fast Refresh / 热更遗留）
        if (
          err?.message?.includes("Only a single WebContainer instance can be booted") ||
          err?.message?.includes("single WebContainer")
        ) {
          if (typeof globalThis !== "undefined" && globalThis.__webcontainer_instance__) {
            this.webcontainer = globalThis.__webcontainer_instance__;
            return this.webcontainer;
          }
        }
        this.bootPromise = null;
        if (typeof globalThis !== "undefined") {
          globalThis.__webcontainer_boot_promise__ = undefined;
        }
        throw new Error(`WebContainer 启动失败: ${err?.message || String(err)}`);
      }
    })();

    if (typeof globalThis !== "undefined") {
      globalThis.__webcontainer_boot_promise__ = this.bootPromise;
    }

    return this.bootPromise;
  }

  /**
   * 将平面文件列表转换为 WebContainer 树形结构
   */
  private buildFileSystemTree(files: VirtualFile[]): FileSystemTree {
    const tree: FileSystemTree = {};

    for (const file of files) {
      const normalized = file.file_path.replace(/^\/+/, "");
      const segments = normalized.split("/");
      let currentLevel = tree;

      for (let i = 0; i < segments.length; i++) {
        const segment = segments[i];
        const isFile = i === segments.length - 1;

        if (isFile) {
          currentLevel[segment] = {
            file: {
              contents: file.content,
            },
          };
        } else {
          if (!currentLevel[segment]) {
            currentLevel[segment] = {
              directory: {},
            };
          }
          const dirEntry = currentLevel[segment];
          if ("directory" in dirEntry) {
            currentLevel = dirEntry.directory;
          }
        }
      }
    }

    return tree;
  }

  /**
   * 全量挂载会话文件
   */
  public async mountSession(sessionId: string, files: VirtualFile[]): Promise<void> {
    const wc = await this.getWebContainer();

    // 如果切换了会话，先杀掉旧的 Dev 服务
    if (this.currentSessionId && this.currentSessionId !== sessionId) {
      await this.stopDevServer();
    }
    this.currentSessionId = sessionId;

    const tree = this.buildFileSystemTree(files);
    await wc.mount(tree);
  }

  /**
   * 增量写入/修改单个文件（用于 LLM 生成后续改动时触发 Vite HMR 热更）
   */
  public async writeVirtualFile(filePath: string, content: string): Promise<void> {
    const wc = await this.getWebContainer();
    const normalized = filePath.replace(/^\/+/, "");
    const segments = normalized.split("/");

    if (segments.length > 1) {
      // 确保父级目录存在
      const dirPath = segments.slice(0, -1).join("/");
      try {
        await wc.fs.mkdir(dirPath, { recursive: true });
      } catch {
        // 忽略已存在错误
      }
    }

    await wc.fs.writeFile(normalized, content);
  }

  /**
   * 启动 WebContainer 前端开发服务（完整流水线：npm i -> npm run dev）
   */
  public async startDevServer(
    sessionId: string,
    files: VirtualFile[],
    callbacks?: DevServerCallbacks
  ): Promise<void> {
    const { onStatusChange, onLog, onServerReady, onError } = callbacks || {};

    try {
      onStatusChange?.("booting");
      onLog?.("🚀 正在初始化 WebContainer 虚拟内核...\n");
      const wc = await this.getWebContainer();

      onStatusChange?.("mounting");
      onLog?.(`📁 正在挂载项目文件 (共 ${files.length} 个文件)...\n`);
      await this.mountSession(sessionId, files);

      // 注册 server-ready 监听
      wc.on("server-ready", (port, url) => {
        this.serverPort = port;
        this.serverUrl = url;
        onLog?.(`\n🎉 Web 开发服务已就绪！监听虚拟端口: ${port}\n预览地址: ${url}\n`);
        onStatusChange?.("ready");
        onServerReady?.(port, url);
      });

      // 1. 执行依赖安装 npm install
      onStatusChange?.("installing");
      onLog?.("📦 正在安装 NPM 项目依赖 (npm install)...\n");

      const installProcess = await wc.spawn("npm", ["install"]);
      this.activeInstallProcess = installProcess;

      installProcess.output.pipeTo(
        new WritableStream({
          write(data) {
            onLog?.(data);
          },
        })
      );

      const installExitCode = await installProcess.exit;
      this.activeInstallProcess = null;

      if (installExitCode !== 0) {
        throw new Error(`npm install 失败，退出码: ${installExitCode}`);
      }

      onLog?.("✅ 依赖安装完毕，正在启动本地开发服务器 (npm run dev)...\n");
      onStatusChange?.("starting");

      // 2. 启动开发服务器 npm run dev
      // 避免之前的进程冲突
      await this.stopDevServer();

      const devProcess = await wc.spawn("npm", ["run", "dev", "--", "--host"]);
      this.activeDevProcess = devProcess;

      devProcess.output.pipeTo(
        new WritableStream({
          write(data) {
            onLog?.(data);
          },
        })
      );

      // 监控异常退出
      devProcess.exit.then((code) => {
        if (code !== 0 && this.activeDevProcess === devProcess) {
          onLog?.(`\n⚠️ 开发服务器异常终止，退出码: ${code}\n`);
          onStatusChange?.("error");
          onError?.(`开发服务器异常退出 (code: ${code})`);
        }
      });
    } catch (err: any) {
      const errMsg = err?.message || String(err);
      onLog?.(`\n❌ 执行失败: ${errMsg}\n`);
      onStatusChange?.("error");
      onError?.(errMsg);
    }
  }

  /**
   * 停止当前运行的开发服务
   */
  public async stopDevServer(): Promise<void> {
    if (this.activeInstallProcess) {
      try {
        this.activeInstallProcess.kill();
      } catch {}
      this.activeInstallProcess = null;
    }

    if (this.activeDevProcess) {
      try {
        this.activeDevProcess.kill();
      } catch {}
      this.activeDevProcess = null;
    }

    this.serverUrl = null;
    this.serverPort = null;
  }

  public getServerUrl(): string | null {
    return this.serverUrl;
  }

  public getServerPort(): number | null {
    return this.serverPort;
  }

  /**
   * 递归读取 WebContainer 内部文件树（默认忽略 node_modules 与隐藏文件）
   */
  public async readVirtualTree(
    dirPath: string = "/",
    ignoreList: string[] = ["node_modules", ".git", ".next", ".turbo"]
  ): Promise<VirtualTreeNode[]> {
    const wc = await this.getWebContainer();
    const cleanDir = dirPath.startsWith("/") ? dirPath : `/${dirPath}`;

    try {
      const entries = await wc.fs.readdir(cleanDir, { withFileTypes: true });
      const nodes: VirtualTreeNode[] = [];

      for (const entry of entries) {
        if (ignoreList.includes(entry.name)) {
          continue;
        }

        const fullPath = cleanDir === "/" ? `/${entry.name}` : `${cleanDir}/${entry.name}`;
        const isDir = entry.isDirectory();

        if (isDir) {
          const children = await this.readVirtualTree(fullPath, ignoreList);
          nodes.push({
            name: entry.name,
            path: fullPath,
            isDirectory: true,
            children,
          });
        } else {
          nodes.push({
            name: entry.name,
            path: fullPath,
            isDirectory: false,
          });
        }
      }

      // 文件夹排在前面，同类按名称字典序
      nodes.sort((a, b) => {
        if (a.isDirectory === b.isDirectory) {
          return a.name.localeCompare(b.name);
        }
        return a.isDirectory ? -1 : 1;
      });

      return nodes;
    } catch (err) {
      console.warn(`Failed to read virtual dir ${cleanDir}:`, err);
      return [];
    }
  }

  /**
   * 读取 WebContainer 中指定文件的文本内容（若为二进制图片则自动转为 Base64 Data URL）
   */
  public async readVirtualFile(filePath: string): Promise<string> {
    const wc = await this.getWebContainer();
    const normalized = filePath.startsWith("/") ? filePath : `/${filePath}`;
    const ext = normalized.split(".").pop()?.toLowerCase() || "";
    const isBinaryImage = ["png", "jpg", "jpeg", "gif", "webp", "ico", "bmp"].includes(ext);

    if (isBinaryImage) {
      const buffer = await wc.fs.readFile(normalized);
      let binary = "";
      const bytes = new Uint8Array(buffer);
      const len = bytes.byteLength;
      for (let i = 0; i < len; i++) {
        binary += String.fromCharCode(bytes[i]);
      }
      const base64 = typeof window !== "undefined" ? window.btoa(binary) : "";
      const mime = ext === "jpg" ? "image/jpeg" : ext === "ico" ? "image/x-icon" : `image/${ext}`;
      return `data:${mime};base64,${base64}`;
    }

    return await wc.fs.readFile(normalized, "utf-8");
  }
}

export interface VirtualTreeNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: VirtualTreeNode[];
}

export const webcontainerManager = WebContainerManager.getInstance();
