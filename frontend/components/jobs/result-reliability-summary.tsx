import { CheckCircle2, Clock3, ShieldCheck, XCircle } from "lucide-react";
import type { ModelResult } from "@/lib/api/types";
import { providerModelLabel } from "@/lib/model-label";

interface Props {
  jobId: string;
  updatedAt: string;
  result: ModelResult;
}

const STATUS_LABELS = {
  completed_with_qualified_candidates: "发现合格候选",
  completed_needs_evidence: "需要补充证据",
  completed_no_qualified_candidates: "没有合格候选",
} as const;

function resultProviderModelLabel(result: ModelResult) {
  if (!result.provider || !result.provider_model) return "历史未记录";
  if (result.provider === "custom") return `自定义 Anthropic · ${result.provider_model}`;
  return providerModelLabel(result.provider, result.provider_model);
}

function countLabel(value: number | undefined) {
  return typeof value === "number" ? String(value) : "未记录";
}

function analysisTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "时间不可用";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(parsed);
}

export default function ResultReliabilitySummary({
  jobId,
  updatedAt,
  result,
}: Props) {
  const status = result.result_status;
  const statusLabel = status ? STATUS_LABELS[status] : "历史结果";
  const StatusIcon =
    status === "completed_with_qualified_candidates"
      ? CheckCircle2
      : status === "completed_no_qualified_candidates"
        ? XCircle
        : Clock3;

  return (
    <section className="border-y bg-muted/20" aria-labelledby="result-reliability-title">
      <div className="grid gap-4 px-4 py-4 lg:grid-cols-[minmax(220px,1.1fr)_minmax(260px,1.4fr)_auto] lg:items-center">
        <div className="min-w-0">
          <p
            id="result-reliability-title"
            className="flex items-center gap-2 text-sm font-semibold"
          >
            <ShieldCheck className="h-4 w-4 text-emerald-700" aria-hidden="true" />
            结果可靠性
          </p>
          <p className="mt-2 flex items-center gap-2 text-sm">
            <StatusIcon className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span className="font-medium">{statusLabel}</span>
          </p>
          {result.result_message && (
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              {result.result_message}
            </p>
          )}
        </div>

        <dl className="grid min-w-0 gap-x-6 gap-y-2 text-xs sm:grid-cols-2">
          <div className="min-w-0">
            <dt className="text-muted-foreground">模型契约</dt>
            <dd className="mt-0.5 break-all font-medium">
              {result.model_version ?? "历史未记录"}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-muted-foreground">供应商与实际模型</dt>
            <dd className="mt-0.5 break-all font-medium">
              {resultProviderModelLabel(result)}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="text-muted-foreground">任务 ID</dt>
            <dd className="mt-0.5 break-all font-mono">{jobId}</dd>
          </div>
          <div className="min-w-0">
            <dt className="text-muted-foreground">分析时间</dt>
            <dd className="mt-0.5 tabular-nums">{analysisTime(updatedAt)}</dd>
          </div>
        </dl>

        <div className="grid grid-cols-3 divide-x border text-center text-xs lg:min-w-[260px]">
          <div
            className="px-3 py-2"
            aria-label={`合格 ${countLabel(result.qualified_direction_count)}`}
          >
            <strong className="block text-base tabular-nums text-emerald-700">
              {countLabel(result.qualified_direction_count)}
            </strong>
            <span className="text-muted-foreground">合格</span>
          </div>
          <div
            className="px-3 py-2"
            aria-label={`待补证据 ${countLabel(result.hold_direction_count)}`}
          >
            <strong className="block text-base tabular-nums text-amber-700">
              {countLabel(result.hold_direction_count)}
            </strong>
            <span className="text-muted-foreground">待补证据</span>
          </div>
          <div
            className="px-3 py-2"
            aria-label={`已淘汰 ${countLabel(result.rejected_direction_count)}`}
          >
            <strong className="block text-base tabular-nums text-rose-700">
              {countLabel(result.rejected_direction_count)}
            </strong>
            <span className="text-muted-foreground">已淘汰</span>
          </div>
        </div>
      </div>
    </section>
  );
}
