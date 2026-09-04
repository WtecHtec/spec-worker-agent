"use client";

import React, { useRef, useEffect, useCallback, useState, useMemo } from "react";
import { MessageItem } from "./MessageItem";
import { ActiveStreamingTurn } from "./ActiveStreamingTurn";
import { ChatInput } from "./ChatInput";
import { useSessionStore } from "@/store/useSessionStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useLangGraphStream } from "@/hooks/useLangGraphStream";
import { Bot, Loader2 } from "lucide-react";
import { HitlFormCard } from "./HitlFormCard";
import { splitCompletedAndActive } from "@/lib/messageNormalizer";

const PAGE_SIZE = 15;

export const ChatWindow: React.FC = () => {
  const token = useAuthStore((state) => state.token);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const createSession = useSessionStore((state) => state.createSession);
  const setCurrentRunId = useSessionStore((state) => state.setCurrentRunId);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const topSentinelRef = useRef<HTMLDivElement>(null);

  const [submittedRequestIds, setSubmittedRequestIds] = useState<Record<string, boolean>>({});
  const [visibleCount, setVisibleCount] = useState<number>(PAGE_SIZE);
  const [isLoadingMore, setIsLoadingMore] = useState<boolean>(false);
  const isUserScrolledUpRef = useRef<boolean>(false);

  // 全面拥抱 LangGraph 原生 useStream：以 Thread 消息流为全局单一可信源
  const {
    isLoading,
    submit,
    resume,
    actionRequests,
    cancel,
    messages,
    getHistory,
  } = useLangGraphStream({
    threadId: currentSessionId,
    token,
    onRunCreated: useCallback((runId: string) => {
      setCurrentRunId(runId);
    }, [setCurrentRunId]),
    onFinish: useCallback(() => {
      setCurrentRunId(null);
    }, [setCurrentRunId]),
  });

  // 维护从数据库 Checkpoints 分页拉取到的历史消息与检查点游标
  const [databaseMessages, setDatabaseMessages] = useState<any[]>([]);
  const [earliestCheckpointId, setEarliestCheckpointId] = useState<string | undefined>(undefined);
  const [hasMoreDatabaseHistory, setHasMoreDatabaseHistory] = useState<boolean>(true);

  // 合并数据库拉取的历史消息与当前 SDK stream.messages（按 id / 内容去重）
  const mergedMessages = useMemo(() => {
    if (databaseMessages.length === 0) return messages;
    const seenIds = new Set<string>();
    const result: any[] = [];

    // 先推入数据库更早的历史
    for (const m of databaseMessages) {
      const key = m.id || `${m.type}-${JSON.stringify(m.content).slice(0, 40)}`;
      if (!seenIds.has(key)) {
        seenIds.add(key);
        result.push(m);
      }
    }

    // 再推入当前 SDK stream 中的消息
    for (const m of messages) {
      const key = m.id || `${m.type}-${JSON.stringify(m.content).slice(0, 40)}`;
      if (!seenIds.has(key)) {
        seenIds.add(key);
        result.push(m);
      }
    }

    return result;
  }, [databaseMessages, messages]);

  // 1. 动静分离：拆解为“已完成静态历史”与“当前活跃流式轮次”
  const { completedTurns, activeTurn } = useMemo(
    () => splitCompletedAndActive(mergedMessages, isLoading),
    [mergedMessages, isLoading]
  );

  // 智能吸底滚动：仅在用户未向上滑看历史或主动发送时执行
  const scrollToBottom = useCallback((force: boolean = false) => {
    if (force || !isUserScrolledUpRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: "auto" });
    }
  }, []);

  // 监听容器滚动：判断用户是否脱离了底部
  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceToBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    isUserScrolledUpRef.current = distanceToBottom > 80;
  }, []);

  // 2. 核心：调用官方 client.threads.getHistory 从数据库拉取更早的 Checkpoints 历史
  const loadPreviousHistory = useCallback(async () => {
    if (isLoadingMore || !hasMoreDatabaseHistory || !currentSessionId) return;
    const container = scrollContainerRef.current;
    if (!container) return;

    setIsLoadingMore(true);
    const prevScrollHeight = container.scrollHeight;

    try {
      // 官方 LangGraph SDK 方法：await client.threads.getHistory(currentThreadId, options)
      const states = await getHistory({
        limit: 10,
        before: earliestCheckpointId ? { configurable: { checkpoint_id: earliestCheckpointId } } : undefined,
      });

      if (!states || states.length === 0) {
        setHasMoreDatabaseHistory(false);
      } else {
        // 提取这些 Checkpoints 中包含的消息
        const olderMessages: any[] = [];
        for (const s of states) {
          const ms = (s as any).values?.messages;
          if (Array.isArray(ms)) {
            olderMessages.push(...ms);
          }
        }

        // 记录最早的 Checkpoint ID 供下次继续向上翻查
        const oldestState = states[states.length - 1];
        const oldestCheckpointId = (oldestState as any).checkpoint_id || (oldestState as any).checkpoint?.id;
        if (oldestCheckpointId) {
          setEarliestCheckpointId(oldestCheckpointId);
        }

        if (states.length < 10) {
          setHasMoreDatabaseHistory(false);
        }

        if (olderMessages.length > 0) {
          setDatabaseMessages((prev) => [...olderMessages, ...prev]);
        }

        // 3. 在 DOM 渲染更新的下一帧精准补偿 scrollTop，实现 Scroll Anchoring 视口绝对静止
        requestAnimationFrame(() => {
          if (scrollContainerRef.current) {
            const newScrollHeight = scrollContainerRef.current.scrollHeight;
            const diff = newScrollHeight - prevScrollHeight;
            scrollContainerRef.current.scrollTop += diff;
          }
        });
      }
    } catch (err) {
      console.error("[ChatWindow] Load previous history from database failed:", err);
    } finally {
      setIsLoadingMore(false);
    }
  }, [isLoadingMore, hasMoreDatabaseHistory, currentSessionId, earliestCheckpointId, getHistory]);

  // 使用 IntersectionObserver 监听顶部哨兵触顶
  useEffect(() => {
    const sentinel = topSentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMoreDatabaseHistory && !isLoadingMore) {
          loadPreviousHistory();
        }
      },
      { root: scrollContainerRef.current, threshold: 0.1 }
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [loadPreviousHistory, hasMoreDatabaseHistory, isLoadingMore]);

  // 会话切换时重置所有数据库游标、消息与审批状态
  useEffect(() => {
    setDatabaseMessages([]);
    setEarliestCheckpointId(undefined);
    setHasMoreDatabaseHistory(true);
    setSubmittedRequestIds({});
    isUserScrolledUpRef.current = false;
    requestAnimationFrame(() => scrollToBottom(true));
  }, [currentSessionId, scrollToBottom]);

  // 发送消息处理
  const handleSend = useCallback(async (text: string) => {
    if (!token || !text.trim() || isLoading) return;

    let sessionId = currentSessionId;
    if (!sessionId) {
      const autoTitle = text.length > 24 ? `${text.slice(0, 24)}...` : text;
      const created = await createSession(token, autoTitle);
      sessionId = created.id;
    }

    // 用户主动发消息：强制吸底并重置滚动脱离标记
    isUserScrolledUpRef.current = false;
    submit(text);
    requestAnimationFrame(() => scrollToBottom(true));
  }, [token, isLoading, currentSessionId, createSession, submit, scrollToBottom]);

  // 监听并处理 HITL 快捷提交事件
  useEffect(() => {
    const onHitlSubmit = (e: any) => {
      const text = e.detail;
      if (text) {
        handleSend(text);
      }
    };
    window.addEventListener("submit_hitl_response", onHitlSubmit);
    return () => window.removeEventListener("submit_hitl_response", onHitlSubmit);
  }, [handleSend]);

  const handleCancel = useCallback(async () => {
    await cancel();
    setCurrentRunId(null);
  }, [cancel, setCurrentRunId]);

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 overflow-hidden">
      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto px-4 sm:px-8 py-6 space-y-2 scrollbar-thin scrollbar-thumb-slate-800"
      >
        {/* 顶部哨兵与更早历史加载提示条 */}
        {hasMoreDatabaseHistory && (
          <div ref={topSentinelRef} className="py-2 text-center">
            <button
              type="button"
              onClick={loadPreviousHistory}
              disabled={isLoadingMore}
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-900 border border-slate-800 text-[11px] text-slate-400 hover:text-indigo-300 hover:border-indigo-500/30 transition-all font-mono"
            >
              {isLoadingMore ? (
                <>
                  <Loader2 className="w-3 h-3 animate-spin text-indigo-400" />
                  <span>正在从数据库拉取更早记录...</span>
                </>
              ) : (
                <span>向上滑动或点击从数据库加载更早历史</span>
              )}
            </button>
          </div>
        )}

        {!currentSessionId || (completedTurns.length === 0 && !activeTurn) ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8 max-w-lg mx-auto">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white mb-4 shadow-xl shadow-indigo-950/50">
              <Bot className="w-7 h-7" />
            </div>
            <h2 className="text-lg font-bold text-slate-100 mb-1.5">欢迎使用 X Agent</h2>
            <p className="text-xs text-slate-400 mb-6 leading-relaxed">
              全链路企业级 Agent 交互平台，完全由 LangGraph 官方流式架构驱动。
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full text-left">
              <button
                onClick={() => handleSend("什么是事件驱动架构？请简要介绍一下。")}
                className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 hover:bg-slate-800/50 transition-all text-xs text-slate-300"
              >
                <span className="font-semibold text-indigo-400 block mb-0.5">🧠 LLM 问答</span>
                问一个技术概念问题
              </button>
              <button
                onClick={() => handleSend("请用中文写一段 50 字以内的自我介绍。")}
                className="p-3 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/40 hover:bg-slate-800/50 transition-all text-xs text-slate-300"
              >
                <span className="font-semibold text-indigo-400 block mb-0.5">✍️ 生成文本</span>
                让 LLM 生成一段介绍
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* 1. 静态历史轮次（含数据库拉取的更早历史）：推流期间完全冻结，重绘次数为 0 */}
            {completedTurns.map((turn) => (
              <MessageItem key={turn.id} message={turn} />
            ))}

            {/* 2. 动态活动流式轮次：仅在打字进行中存在，高频 Token 在叶子组件内局部消化 */}
            {activeTurn && (
              <ActiveStreamingTurn
                turn={activeTurn}
                onScrollBottom={() => scrollToBottom(false)}
              />
            )}
          </>
        )}

        {/* 官方 LangGraph HITL interrupt 待审批交互卡片 */}
        {actionRequests && actionRequests.length > 0 && actionRequests
          .filter((req: any, idx: number) => !submittedRequestIds[req.id || String(idx)])
          .map((req: any, idx: number) => {
            const reqKey = req.id || String(idx);
            return (
              <div key={reqKey} className="flex justify-start my-3 animate-in fade-in slide-in-from-bottom-2 duration-300">
                <HitlFormCard
                  title={req.title || "人机协同操作审批"}
                  description={req.description || ""}
                  riskLevel={req.risk_level || "high"}
                  formFields={req.form_fields || []}
                  onSubmit={(formData) => {
                    setSubmittedRequestIds((prev) => ({ ...prev, [reqKey]: true }));
                    resume(formData);
                  }}
                />
              </div>
            );
          })}

        <div ref={messagesEndRef} />
      </div>

      <ChatInput
        onSendMessage={handleSend}
        onCancel={handleCancel}
        isSending={isLoading}
        isStreaming={isLoading}
      />
    </div>
  );
};
