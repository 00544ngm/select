"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";
import type { JobMode, JobStatus } from "@/lib/api/types";

const modeOptions: { value: JobMode | ""; label: string }[] = [
  { value: "", label: "全部模式" },
  { value: "hypothesis", label: "假设分析" },
  { value: "judgment", label: "对比判断" },
  { value: "batch", label: "批量处理" },
];

const statusOptions: { value: JobStatus | ""; label: string }[] = [
  { value: "", label: "全部状态" },
  { value: "queued", label: "排队中" },
  { value: "running", label: "处理中" },
  { value: "completed", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "interrupted", label: "已中断" },
];

interface HistoryFiltersProps {
  mode: JobMode | "";
  status: JobStatus | "";
  onModeChange: (mode: JobMode | "") => void;
  onStatusChange: (status: JobStatus | "") => void;
}

export default function HistoryFilters({
  mode,
  status,
  onModeChange,
  onStatusChange,
}: HistoryFiltersProps) {
  const [modeOpen, setModeOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const modeRef = useRef<HTMLDivElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (modeRef.current && !modeRef.current.contains(e.target as Node)) {
        setModeOpen(false);
      }
      if (statusRef.current && !statusRef.current.contains(e.target as Node)) {
        setStatusOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const currentModeLabel = modeOptions.find((o) => o.value === mode)?.label ?? "全部模式";
  const currentStatusLabel = statusOptions.find((o) => o.value === status)?.label ?? "全部状态";

  return (
    <div className="flex gap-3">
      <div ref={modeRef} className="relative">
        <button
          type="button"
          onClick={() => setModeOpen(!modeOpen)}
          className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-muted"
          aria-label="模式"
        >
          {currentModeLabel}
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
        {modeOpen && (
          <div className="absolute left-0 top-full z-10 mt-1 w-36 rounded-md border bg-background shadow-lg">
            {modeOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={mode === opt.value}
                onClick={() => { onModeChange(opt.value); setModeOpen(false); }}
                className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-muted ${
                  mode === opt.value ? "font-medium" : ""
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div ref={statusRef} className="relative">
        <button
          type="button"
          onClick={() => setStatusOpen(!statusOpen)}
          className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-muted"
          aria-label="状态"
        >
          {currentStatusLabel}
          <ChevronDown className="h-4 w-4 text-muted-foreground" />
        </button>
        {statusOpen && (
          <div className="absolute left-0 top-full z-10 mt-1 w-36 rounded-md border bg-background shadow-lg">
            {statusOptions.map((opt) => (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={status === opt.value}
                onClick={() => { onStatusChange(opt.value); setStatusOpen(false); }}
                className={`w-full px-3 py-2 text-left text-sm transition-colors hover:bg-muted ${
                  status === opt.value ? "font-medium" : ""
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
