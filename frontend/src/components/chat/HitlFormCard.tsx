"use client";

import React, { useState } from "react";
import { ShieldAlert, CheckCircle2, AlertTriangle, Send, Lock } from "lucide-react";

export interface FormField {
  field_id: string;
  label: string;
  type: "confirm" | "single_select" | "multi_select" | "text_input";
  options?: string[];
  default_value?: string;
  required?: boolean;
}

export interface HitlCardProps {
  title: string;
  description: string;
  riskLevel?: "low" | "medium" | "high" | "critical";
  formFields: FormField[];
  onSubmit: (data: Record<string, any>) => void;
  isResolved?: boolean;
}

const riskBadges = {
  critical: { label: "CRITICAL 极高危", color: "bg-red-500/20 text-red-400 border-red-500/40" },
  high: { label: "HIGH 高危", color: "bg-orange-500/20 text-orange-400 border-orange-500/40" },
  medium: { label: "MEDIUM 中度关注", color: "bg-amber-500/20 text-amber-400 border-amber-500/40" },
  low: { label: "LOW 提示", color: "bg-blue-500/20 text-blue-400 border-blue-500/40" },
};

export const HitlFormCard: React.FC<HitlCardProps> = ({
  title,
  description,
  riskLevel = "medium",
  formFields,
  onSubmit,
  isResolved = false,
}) => {
  const [formData, setFormData] = useState<Record<string, any>>(() => {
    const init: Record<string, any> = {};
    formFields.forEach((f) => {
      if (f.type === "confirm") init[f.field_id] = "approve";
      else if (f.type === "single_select") init[f.field_id] = f.default_value || f.options?.[0] || "";
      else if (f.type === "multi_select") init[f.field_id] = f.default_value ? [f.default_value] : [];
      else init[f.field_id] = f.default_value || "";
    });
    return init;
  });

  const [submitted, setSubmitted] = useState<boolean>(isResolved);

  const handleSingleSelect = (fieldId: string, val: string) => {
    if (submitted) return;
    setFormData((prev) => ({ ...prev, [fieldId]: val }));
  };

  const handleMultiSelect = (fieldId: string, val: string) => {
    if (submitted) return;
    setFormData((prev) => {
      const cur: string[] = prev[fieldId] || [];
      const updated = cur.includes(val) ? cur.filter((item) => item !== val) : [...cur, val];
      return { ...prev, [fieldId]: updated };
    });
  };

  const handleTextChange = (fieldId: string, val: string) => {
    if (submitted) return;
    setFormData((prev) => ({ ...prev, [fieldId]: val }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (submitted) return;
    setSubmitted(true);
    onSubmit(formData);
  };

  const badge = riskBadges[riskLevel] || riskBadges.medium;

  return (
    <div className="my-3 p-4 rounded-xl border border-amber-500/30 bg-slate-900/90 shadow-xl shadow-amber-950/20 max-w-xl">
      {/* 头部标题与风险徽章 */}
      <div className="flex items-start justify-between gap-3 pb-3 border-b border-white/10">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              {title}
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono border ${badge.color}`}>
                {badge.label}
              </span>
            </h4>
            <p className="text-xs text-slate-400 mt-0.5">{description}</p>
          </div>
        </div>

        {submitted && (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
            <CheckCircle2 className="w-3.5 h-3.5" /> 已响应
          </span>
        )}
      </div>

      {/* 动态表单项 */}
      <form onSubmit={handleSubmit} className="mt-3.5 space-y-3.5">
        {formFields.map((field) => (
          <div key={field.field_id} className="space-y-1.5">
            <label className="block text-xs font-medium text-slate-300">
              {field.label}
              {field.required && <span className="text-rose-400 ml-1">*</span>}
            </label>

            {/* 1. 操作确认 (confirm) */}
            {field.type === "confirm" && (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={submitted}
                  onClick={() => handleSingleSelect(field.field_id, "approve")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                    formData[field.field_id] === "approve"
                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm"
                      : "bg-slate-800/60 text-slate-400 border-slate-700/60 hover:bg-slate-800"
                  }`}
                >
                  ✅ 批准执行
                </button>
                <button
                  type="button"
                  disabled={submitted}
                  onClick={() => handleSingleSelect(field.field_id, "reject")}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-all ${
                    formData[field.field_id] === "reject"
                      ? "bg-rose-500/20 text-rose-300 border-rose-500/40 shadow-sm"
                      : "bg-slate-800/60 text-slate-400 border-slate-700/60 hover:bg-slate-800"
                  }`}
                >
                  ❌ 拒绝此操作
                </button>
              </div>
            )}

            {/* 2. 单选 (single_select) */}
            {field.type === "single_select" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(field.options || []).map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    disabled={submitted}
                    onClick={() => handleSingleSelect(field.field_id, opt)}
                    className={`px-3 py-2 rounded-lg text-left text-xs border transition-all ${
                      formData[field.field_id] === opt
                        ? "bg-indigo-600/20 text-indigo-200 border-indigo-500/50"
                        : "bg-slate-800/40 text-slate-400 border-slate-700/40 hover:bg-slate-800/80"
                    }`}
                  >
                    <span className="inline-block w-2 h-2 rounded-full mr-2 bg-current opacity-70" />
                    {opt}
                  </button>
                ))}
              </div>
            )}

            {/* 3. 多选 (multi_select) */}
            {field.type === "multi_select" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(field.options || []).map((opt) => {
                  const isChecked = (formData[field.field_id] || []).includes(opt);
                  return (
                    <button
                      key={opt}
                      type="button"
                      disabled={submitted}
                      onClick={() => handleMultiSelect(field.field_id, opt)}
                      className={`px-3 py-2 rounded-lg text-left text-xs border transition-all flex items-center justify-between ${
                        isChecked
                          ? "bg-indigo-600/20 text-indigo-200 border-indigo-500/50"
                          : "bg-slate-800/40 text-slate-400 border-slate-700/40 hover:bg-slate-800/80"
                      }`}
                    >
                      <span>{opt}</span>
                      <span className={`w-3.5 h-3.5 rounded flex items-center justify-center border text-[9px] ${
                        isChecked ? "bg-indigo-500 border-indigo-400 text-white" : "border-slate-600"
                      }`}>
                        {isChecked && "✓"}
                      </span>
                    </button>
                  );
                })}
              </div>
            )}

            {/* 4. 文本输入 (text_input) */}
            {field.type === "text_input" && (
              <input
                type="text"
                disabled={submitted}
                value={formData[field.field_id] || ""}
                onChange={(e) => handleTextChange(field.field_id, e.target.value)}
                placeholder="请输入您的要求或补充说明..."
                className="w-full px-3 py-2 bg-slate-950/80 border border-slate-700/80 rounded-lg text-xs text-slate-200 focus:outline-none focus:border-indigo-500/60 disabled:opacity-50"
              />
            )}
          </div>
        ))}

        {!submitted ? (
          <div className="pt-2 flex justify-end">
            <button
              type="submit"
              className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-amber-600 to-amber-700 hover:from-amber-500 hover:to-amber-600 text-white shadow-md shadow-amber-950/40 transition-all active:scale-95"
            >
              <Send className="w-3.5 h-3.5" /> 提交决策并继续
            </button>
          </div>
        ) : (
          <div className="pt-2 flex items-center gap-1 text-[11px] text-slate-400 italic">
            <Lock className="w-3 h-3" /> 表单已锁定并已向 Agent 提交确认。
          </div>
        )}
      </form>
    </div>
  );
};
