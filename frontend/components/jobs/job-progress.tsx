"use client";

import { Check, Loader2, Circle, X } from "lucide-react";

interface JobProgressProps {
  status: "queued" | "running" | "completed" | "failed" | "interrupted";
  progress: number;
}

const STAGES = [
  { key: "fetch", label: "抓取商品", from: 0, to: 34 },
  { key: "analyze", label: "模型分析", from: 34, to: 88 },
  { key: "report", label: "生成报告", from: 88, to: 100 },
];

export default function JobProgress({ status, progress }: JobProgressProps) {
  // 已完成的任务不占版面，收成一行
  if (status === "completed") {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Check className="h-3.5 w-3.5 text-emerald-600" />
        任务已完成
      </div>
    );
  }

  const stageState = (from: number, to: number): "done" | "active" | "pending" => {
    if (status === "queued") return "pending";
    if (progress >= to) return "done";
    if (progress >= from) return "active";
    return "pending";
  };

  const activeStage = STAGES.find(
    (s) => stageState(s.from, s.to) === "active"
  );

  const statusLine =
    status === "queued"
      ? "排队中，等待执行..."
      : status === "failed"
        ? "任务失败"
        : status === "interrupted"
          ? "任务已中断，请重新提交"
        : activeStage
          ? `正在${activeStage.label}...`
          : "处理中...";

  return (
    <div className="rounded-xl border p-4">
      <div className="flex items-center">
        {STAGES.map((stage, i) => {
          const state = stageState(stage.from, stage.to);
          const failedHere = (status === "failed" || status === "interrupted") && state === "active";
          return (
            <div key={stage.key} className="flex flex-1 items-center">
              <div className="flex flex-1 flex-col items-center gap-1">
                {failedHere ? (
                  <X className="h-4 w-4 text-destructive" />
                ) : state === "done" ? (
                  <Check className="h-4 w-4 text-emerald-600" />
                ) : state === "active" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-foreground" />
                ) : (
                  <Circle className="h-4 w-4 text-muted-foreground/40" />
                )}
                <span
                  className={`text-xs ${
                    state === "active"
                      ? "font-medium text-foreground"
                      : state === "done"
                        ? "text-muted-foreground"
                        : "text-muted-foreground/60"
                  }`}
                >
                  {stage.label}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <div
                  className={`mb-4 h-0.5 flex-1 rounded-full ${
                    stageState(STAGES[i + 1].from, STAGES[i + 1].to) !==
                      "pending" || state === "done"
                      ? "bg-emerald-500"
                      : "bg-muted"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${
            status === "failed" ? "bg-destructive" : status === "interrupted" ? "bg-amber-500" : "bg-foreground"
          }`}
          style={{ width: `${progress}%` }}
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <div className="mt-1.5 flex items-center justify-between text-xs text-muted-foreground">
        <span>{statusLine}</span>
        <span className="tabular-nums">{progress}%</span>
      </div>
    </div>
  );
}
