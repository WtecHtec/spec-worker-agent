"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  VChart,
  registerRangeColumnChart,
  registerCartesianLinearAxis,
  registerCartesianBandAxis,
  registerTooltip,
  registerDomTooltipHandler,
  registerLabel,
  registerAnimate,
} from "@visactor/vchart";
import { SpanDetail } from "./TraceDrawer";

// 显式按需注册 VChart 核心模块，解决 Turbopack tree-shaking 导致的 "init chart fail"
try {
  VChart.useRegisters([
    registerRangeColumnChart,
    registerCartesianLinearAxis,
    registerCartesianBandAxis,
    registerTooltip,
    registerDomTooltipHandler,
    registerLabel,
    registerAnimate,
  ]);
} catch (e) {
  console.warn("VChart useRegisters warning:", e);
}

interface VChartGanttProps {
  spans: SpanDetail[];
  totalDurationMs: number;
  selectedSpanId?: string | null;
  onSelectSpan?: (spanId: string) => void;
}

function parseTimestamp(dateStr?: string): number {
  if (!dateStr) return 0;
  try {
    const normalized = dateStr.includes("T") ? dateStr : dateStr.replace(" ", "T");
    const ts = new Date(normalized).getTime();
    return isNaN(ts) ? 0 : ts;
  } catch {
    return 0;
  }
}

// 步骤类型色彩映射（参考 visactor gantt 风格的层次分明配色）
function getSpanColor(type: string, isEnd: boolean = false): string {
  const t = (type || "").toLowerCase();
  if (t.includes("llm") || t.includes("model") || t.includes("chat")) {
    return isEnd ? "#60a5fa" : "#3b82f6"; // 科技蓝
  }
  if (t.includes("tool") || t.includes("action") || t.includes("call")) {
    return isEnd ? "#fb923c" : "#f97316"; // 活力橙
  }
  if (t.includes("memory") || t.includes("compress")) {
    return isEnd ? "#34d399" : "#10b981"; // 记忆绿
  }
  if (t.includes("agent") || t.includes("node")) {
    return isEnd ? "#c084fc" : "#8b5cf6"; // 流程紫
  }
  return isEnd ? "#94a3b8" : "#64748b"; // 默认灰
}

export const VChartGantt: React.FC<VChartGanttProps> = ({
  spans,
  totalDurationMs,
  selectedSpanId,
  onSelectSpan,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<VChart | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);

  // 计算甘特图区间数据项
  const firstStartTime = spans && spans.length > 0 ? parseTimestamp(spans[0]?.start_time) : 0;
  let cumulativeOffset = 0;

  const ganttValues = (spans || []).map((span, index) => {
    const sTime = parseTimestamp(span.start_time);
    const hasRealOffset = firstStartTime > 0 && sTime >= firstStartTime;
    const startOffset = hasRealOffset ? sTime - firstStartTime : cumulativeOffset;

    const rawDuration = span.duration_ms || 0;
    // 视觉保底 30ms，防止纳秒级 span 在时间轴上缩为 0px
    const visualDuration = Math.max(rawDuration, 30);
    const endOffset = startOffset + visualDuration;

    cumulativeOffset = Math.max(cumulativeOffset + visualDuration, endOffset);

    const typeStr = span.type || "node";
    const colorStart = getSpanColor(typeStr, false);
    const colorEnd = getSpanColor(typeStr, true);

    return {
      id: span.id,
      index: index + 1,
      stepName: `${index + 1}. ${span.name}`,
      rawName: span.name,
      type: typeStr,
      status: span.status || "success",
      start: Math.round(startOffset),
      end: Math.round(endOffset),
      duration: rawDuration,
      colorStart,
      colorEnd,
      tokensTotal: span.tokens?.total || span.tokens?.total_tokens || 0,
    };
  });

  const maxAxisMs = Math.max(
    totalDurationMs || 0,
    ganttValues.length > 0 ? ganttValues[ganttValues.length - 1].end : 500,
    100
  );

  useEffect(() => {
    if (!containerRef.current || !spans || spans.length === 0) return;

    setRenderError(null);

    // 销毁旧实例
    if (chartInstanceRef.current) {
      try {
        chartInstanceRef.current.release();
      } catch (e) {
        console.warn("Release chart warning:", e);
      }
      chartInstanceRef.current = null;
    }

    try {
      // 官方 Spec 配置（参考 https://visactor.io/vchart/demo/gantt/gantt-customLayout）
      const spec: any = {
        type: "rangeColumn",
        direction: "horizontal",
        theme: "dark",
        background: "transparent",
        padding: { top: 16, right: 32, bottom: 32, left: 24 },
        data: [
          {
            id: "ganttData",
            values: ganttValues,
          },
        ],
        xField: ["start", "end"],
        yField: "stepName",
        seriesField: "type",
        bar: {
          style: {
            cornerRadius: 8,
            fill: (datum: any) => datum.colorStart || "#6366f1",
            stroke: (datum: any) =>
              datum.id === selectedSpanId ? "#ffffff" : "rgba(255,255,255,0.15)",
            lineWidth: (datum: any) => (datum.id === selectedSpanId ? 2.5 : 1),
            shadowBlur: (datum: any) => (datum.id === selectedSpanId ? 12 : 0),
            shadowColor: (datum: any) =>
              datum.id === selectedSpanId ? "rgba(99, 102, 241, 0.8)" : "transparent",
            fillOpacity: (datum: any) =>
              selectedSpanId && datum.id !== selectedSpanId ? 0.45 : 0.95,
          },
          state: {
            hover: {
              fillOpacity: 1,
              cursor: "pointer",
            },
          },
        },
        label: {
          visible: true,
          position: "inside-right",
          style: {
            fill: "#ffffff",
            fontSize: 10,
            fontWeight: 600,
            fontFamily: "monospace",
          },
          formatMethod: (_val: any, datum: any) => {
            const d = datum.duration;
            return d >= 1000 ? `${(d / 1000).toFixed(2)}s` : `${d}ms`;
          },
        },
        axes: [
          {
            orient: "bottom",
            type: "linear",
            min: 0,
            max: maxAxisMs,
            title: {
              visible: true,
              text: "时间线 (毫秒 ms)",
              style: { fill: "#64748b", fontSize: 11, fontWeight: 500 },
            },
            label: {
              style: { fill: "#94a3b8", fontSize: 11, fontFamily: "monospace" },
              formatMethod: (val: number) => `${Math.round(val)}ms`,
            },
            grid: {
              visible: true,
              style: { stroke: "#1e293b", lineDash: [4, 4] },
            },
          },
          {
            orient: "left",
            type: "band",
            domainLine: { style: { stroke: "#334155" } },
            label: {
              style: { fill: "#cbd5e1", fontSize: 12, fontWeight: 500 },
            },
          },
        ],
        tooltip: {
          visible: true,
          mark: {
            title: {
              value: (datum: any) => datum.rawName,
            },
            content: [
              {
                key: "步骤类型",
                value: (datum: any) => String(datum.type).toUpperCase(),
              },
              {
                key: "实际执行耗时",
                value: (datum: any) =>
                  datum.duration >= 1000
                    ? `${(datum.duration / 1000).toFixed(2)} 秒 (${datum.duration} ms)`
                    : `${datum.duration} ms`,
              },
              {
                key: "时间轴区间",
                value: (datum: any) => `${datum.start}ms ~ ${datum.end}ms`,
              },
              {
                key: "Token 消耗",
                value: (datum: any) =>
                  datum.tokensTotal > 0 ? `${datum.tokensTotal}` : "无",
              },
              {
                key: "执行状态",
                value: (datum: any) => datum.status,
              },
            ],
          },
        },
      };

      const vchart = new VChart(spec, {
        dom: containerRef.current,
        mode: "desktop-browser",
        onError: (err: any) => {
          console.error("VChart onError triggered:", err);
          setRenderError(String(err?.message || err));
        },
      });
      chartInstanceRef.current = vchart;

      vchart
        .renderAsync()
        .then(() => {
          requestAnimationFrame(() => {
            if (containerRef.current && chartInstanceRef.current) {
              const w = containerRef.current.clientWidth;
              if (w > 0) {
                chartInstanceRef.current.resize(w, height);
              }
            }
          });
        })
        .catch((err) => {
          console.error("vchart renderAsync failed:", err);
          setRenderError(err?.message || "渲染失败");
        });

      // 监听条形点击，联动父级 Step Inspector
      vchart.on("click", (params: any) => {
        const clickedId = params.datum?.id;
        if (clickedId && onSelectSpan) {
          onSelectSpan(clickedId);
        }
      });
    } catch (e: any) {
      console.error("Failed to initialize VChart:", e);
      setRenderError(e?.message || "初始化图表失败");
    }

    // 抽屉动画完成或容器尺寸变化自适应
    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && containerRef.current) {
      ro = new ResizeObserver(() => {
        if (containerRef.current && chartInstanceRef.current) {
          const w = containerRef.current.clientWidth;
          if (w > 0) {
            chartInstanceRef.current.resize(w, height);
          }
        }
      });
      ro.observe(containerRef.current);
    }

    return () => {
      if (ro) ro.disconnect();
      if (chartInstanceRef.current) {
        try {
          chartInstanceRef.current.release();
        } catch {}
        chartInstanceRef.current = null;
      }
    };
  }, [spans, totalDurationMs, selectedSpanId, onSelectSpan]);

  const height = Math.max(180, (spans || []).length * 48 + 72);

  // 若 VChart 引擎在某些特殊环境下报错，无缝降级为高保真 CSS/SVG 甘特图，确保用户体验不中断
  if (renderError) {
    return (
      <div className="w-full bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 font-sans">
        <div className="flex items-center justify-between pb-3 mb-3 border-b border-slate-800 text-xs text-slate-400">
          <span className="font-medium text-slate-300">执行时序甘特图 (降级视图)</span>
          <span className="font-mono text-[11px]">总计: {totalDurationMs}ms</span>
        </div>
        <div className="space-y-2.5">
          {ganttValues.map((item) => {
            const startPct = Math.min(100, Math.max(0, (item.start / maxAxisMs) * 100));
            const widthPct = Math.min(
              100 - startPct,
              Math.max(4, ((item.end - item.start) / maxAxisMs) * 100)
            );
            const isSelected = item.id === selectedSpanId;

            return (
              <div
                key={item.id}
                onClick={() => onSelectSpan && onSelectSpan(item.id)}
                className={`group cursor-pointer rounded-lg p-2 transition-all ${
                  isSelected
                    ? "bg-slate-800/90 ring-1 ring-indigo-500 shadow-md"
                    : "hover:bg-slate-800/50"
                }`}
              >
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[11px] text-slate-400">
                      {item.index}.
                    </span>
                    <span className="font-medium text-slate-200 group-hover:text-indigo-300 transition-colors">
                      {item.rawName}
                    </span>
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded font-mono uppercase"
                      style={{
                        backgroundColor: `${item.colorStart}20`,
                        color: item.colorStart,
                        border: `1px solid ${item.colorStart}40`,
                      }}
                    >
                      {item.type}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-slate-400">
                    {item.duration}ms
                  </span>
                </div>
                <div className="h-4 w-full bg-slate-900 rounded-full overflow-hidden relative border border-slate-800">
                  <div
                    className="h-full rounded-full transition-all duration-300 relative group-hover:brightness-110"
                    style={{
                      left: `${startPct}%`,
                      width: `${widthPct}%`,
                      backgroundColor: item.colorStart,
                      boxShadow: isSelected ? `0 0 10px ${item.colorStart}80` : "none",
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <div className="w-full relative min-h-[180px]">
      <div
        ref={containerRef}
        style={{ width: "100%", height: `${height}px` }}
        className="rounded-xl overflow-hidden"
      />
    </div>
  );
};

export default VChartGantt;
