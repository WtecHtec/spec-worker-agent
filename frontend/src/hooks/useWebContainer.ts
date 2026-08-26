"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import {
  webcontainerManager,
  WebContainerStatus,
  VirtualFile,
} from "@/lib/webcontainer/webcontainerManager";

export function useWebContainer() {
  const [status, setStatus] = useState<WebContainerStatus>("idle");
  const [logs, setLogs] = useState<string[]>([]);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [port, setPort] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSupported, setIsSupported] = useState<boolean>(true);

  const activeSessionRef = useRef<string | null>(null);

  useEffect(() => {
    setIsSupported(webcontainerManager.isSupported());
  }, []);

  const appendLog = useCallback((data: string) => {
    setLogs((prev) => [...prev, data]);
  }, []);

  const clearLogs = useCallback(() => {
    setLogs([]);
  }, []);

  const runProject = useCallback(
    async (sessionId: string, files: VirtualFile[]) => {
      setError(null);
      setLogs([]);
      setPreviewUrl(null);
      setPort(null);
      activeSessionRef.current = sessionId;

      await webcontainerManager.startDevServer(sessionId, files, {
        onStatusChange: (newStatus) => {
          setStatus(newStatus);
        },
        onLog: (chunk) => {
          appendLog(chunk);
        },
        onServerReady: (p, url) => {
          setPort(p);
          setPreviewUrl(url);
        },
        onError: (err) => {
          setError(err);
        },
      });
    },
    [appendLog]
  );

  const stopProject = useCallback(async () => {
    await webcontainerManager.stopDevServer();
    setStatus("idle");
    setPreviewUrl(null);
    setPort(null);
  }, []);

  return {
    status,
    logs,
    previewUrl,
    port,
    error,
    isSupported,
    runProject,
    stopProject,
    clearLogs,
  };
}
