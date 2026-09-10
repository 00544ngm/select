import type { JobAttempt } from "@/lib/api/types";

const statusLabels: Record<JobAttempt["status"], string> = {
  running: "处理中",
  succeeded: "成功",
  failed: "失败",
};

export default function JobAttemptTimeline({ attempts }: { attempts: JobAttempt[] }) {
  if (!attempts.length) return null;
  return (
    <section className="space-y-3 border p-4" aria-labelledby="job-attempts-heading">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="job-attempts-heading" className="text-sm font-semibold">模型尝试</h2>
        <span className="text-xs text-muted-foreground">{attempts.length} 次</span>
      </div>
      <ol className="space-y-2">
        {attempts.map((attempt) => (
          <li key={attempt.id} className="grid gap-1 border-l-2 border-muted pl-3 text-sm sm:grid-cols-[32px_minmax(0,1fr)_auto] sm:items-center">
            <span className="text-xs tabular-nums text-muted-foreground">#{attempt.ordinal}</span>
            <div className="min-w-0">
              <p className="truncate font-medium">{attempt.model}</p>
              <p className="text-xs text-muted-foreground">{attempt.provider} · {attempt.stage ?? "执行"}{attempt.error_code ? ` · ${attempt.error_code}` : ""}</p>
              {attempt.error_message && <p className="break-words text-xs text-destructive">{attempt.error_message}</p>}
            </div>
            <span className={`text-xs ${attempt.status === "succeeded" ? "text-green-700" : attempt.status === "failed" ? "text-destructive" : "text-amber-700"}`}>
              {statusLabels[attempt.status]}{attempt.duration_ms != null ? ` · ${(attempt.duration_ms / 1000).toFixed(1)}s` : ""}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
