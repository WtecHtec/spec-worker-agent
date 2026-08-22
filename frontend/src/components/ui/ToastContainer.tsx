"use client";

import React from "react";
import { useToastStore } from "@/store/useToastStore";
import { AlertTriangle, CheckCircle, Info, XCircle, X } from "lucide-react";

export const ToastContainer: React.FC = () => {
  const toasts = useToastStore((state) => state.toasts);
  const removeToast = useToastStore((state) => state.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
      {toasts.map((t) => {
        const iconMap = {
          info: <Info className="w-4 h-4 text-indigo-400 shrink-0" />,
          success: <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />,
          warning: <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />,
          error: <XCircle className="w-4 h-4 text-rose-400 shrink-0" />,
        };

        const borderMap = {
          info: "border-indigo-500/30 bg-slate-900/95 text-slate-100",
          success: "border-emerald-500/30 bg-slate-900/95 text-slate-100",
          warning: "border-amber-500/30 bg-slate-900/95 text-slate-100",
          error: "border-rose-500/30 bg-slate-900/95 text-slate-100",
        };

        return (
          <div
            key={t.id}
            className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-2xl border shadow-2xl backdrop-blur-xl animate-in slide-in-from-top-3 duration-200 ${borderMap[t.type]}`}
          >
            <div className="mt-0.5">{iconMap[t.type]}</div>
            <div className="flex-1 min-w-0">
              {t.title && (
                <div className="text-xs font-semibold text-slate-100 mb-0.5">
                  {t.title}
                </div>
              )}
              <div className="text-xs text-slate-300 leading-relaxed">
                {t.message}
              </div>
            </div>
            <button
              onClick={() => removeToast(t.id)}
              className="text-slate-500 hover:text-slate-300 p-0.5 rounded-md transition-colors"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
