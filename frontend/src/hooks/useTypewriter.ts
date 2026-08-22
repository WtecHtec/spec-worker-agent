import { useState, useEffect, useRef } from "react";

interface UseTypewriterOptions {
  speed?: number;          // 基础字符延迟 (ms)
  isStreaming?: boolean;   // 是否处于流式状态
  batchSize?: number;      // 基础每次吐出字符数
  onComplete?: () => void; // 吐字完成回调
}

/**
 * 高性能 requestAnimationFrame 驱动的打字机 Hook
 * 带有自适应缓冲区调度，杜绝高频 setState 掉帧
 */
export function useTypewriter(
  targetText: string = "",
  options: UseTypewriterOptions = {}
) {
  const {
    speed = 18,
    isStreaming = true,
    batchSize = 1,
    onComplete,
  } = options;

  const [displayedText, setDisplayedText] = useState(() => (isStreaming ? "" : targetText));
  const displayedLengthRef = useRef(isStreaming ? 0 : targetText.length);
  const targetTextRef = useRef(targetText);
  const rafIdRef = useRef<number | null>(null);
  const lastTickTimeRef = useRef<number>(0);

  targetTextRef.current = targetText;

  useEffect(() => {
    // 如果不是实时流式推送（如查看历史消息），直接瞬时输出，跳过动画
    if (!isStreaming) {
      setDisplayedText(targetText);
      displayedLengthRef.current = targetText.length;
      return;
    }

    const animate = (timestamp: number) => {
      if (!lastTickTimeRef.current) lastTickTimeRef.current = timestamp;
      const elapsed = timestamp - lastTickTimeRef.current;

      const currentTarget = targetTextRef.current;
      const currentLength = displayedLengthRef.current;
      const remainingLength = currentTarget.length - currentLength;

      if (remainingLength > 0) {
        // 动态自适应速度：如果缓冲区积压严重（>50字符），自动加速每帧多吐字
        let charsToTake = batchSize;
        if (remainingLength > 100) {
          charsToTake = 6;
        } else if (remainingLength > 40) {
          charsToTake = 3;
        }

        if (elapsed >= speed) {
          const nextLength = Math.min(currentLength + charsToTake, currentTarget.length);
          displayedLengthRef.current = nextLength;
          setDisplayedText(currentTarget.slice(0, nextLength));
          lastTickTimeRef.current = timestamp;
        }

        rafIdRef.current = requestAnimationFrame(animate);
      } else {
        // 已经追平目标文本
        if (onComplete) onComplete();
        rafIdRef.current = null;
      }
    };

    rafIdRef.current = requestAnimationFrame(animate);

    return () => {
      if (rafIdRef.current) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [targetText, isStreaming, speed, batchSize]);

  return {
    displayedText,
    isTyping: isStreaming && displayedText.length < targetText.length,
  };
}
