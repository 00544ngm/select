import { CheckCircle2, ShieldAlert, XCircle } from "lucide-react";
import { useId } from "react";
import type { ProductTypeReview, ProductTypeReviewEvidence, ProductTypeReviewStatus } from "@/lib/api/types";

const statusLabels = {
  confirmed_non_food: "确认非食品",
  confirmed_food: "确认食品（不符合准入范围）",
  likely_non_food: "倾向非食品（建议复核）",
  needs_review: "需要人工复核",
} as const;
const sourceLabels = { rule: "规则判断", model: "模型复核", fallback: "安全降级" } as const;
const actionLabels = { continue: "允许继续分析", continue_with_review: "继续分析，建议人工复核", block: "食品不准入，已阻断" } as const;
const knownStatuses = new Set<string>(Object.keys(statusLabels));
const hasChinese = (value: string) => /[\u3400-\u9fff]/.test(value);

export function productTypeReasonZh(review: ProductTypeReview): string {
  const reasonZh = review.reason_zh?.trim();
  if (reasonZh) return reasonZh;
  const reason = review.reason?.trim();
  if (reason && hasChinese(reason)) return reason;
  const status = knownStatuses.has(review.status)
    ? statusLabels[review.status as ProductTypeReviewStatus]
    : "商品类型需要人工复核";
  const source = review.source && review.source in sourceLabels
    ? sourceLabels[review.source as keyof typeof sourceLabels]
    : "历史未记录";
  const action = review.action && review.action in actionLabels
    ? actionLabels[review.action as keyof typeof actionLabels]
    : "继续分析，建议人工复核";
  return `${status}；判断来源为${source}；系统${action}。`;
}

function evidenceFieldLabel(field: string) {
  const labels: Record<string, string> = {
    name_zh: "中文名称", name_en: "英文名称", canonical_name: "规范名称",
    title: "商品标题", description: "商品描述", bullet_points: "商品要点", attributes: "商品属性",
  };
  if (labels[field]) return labels[field];
  const bullet = field.match(/^bullet_points\[(\d+)\]$/);
  if (bullet) return `商品要点 ${bullet[1]}`;
  if (/^attributes(?:\.|\[)/.test(field)) return "商品属性";
  return "商品信息";
}

function validEvidence(value: unknown): ProductTypeReviewEvidence[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ProductTypeReviewEvidence => Boolean(
    item && typeof item === "object" &&
    typeof (item as ProductTypeReviewEvidence).source_field === "string" &&
    typeof (item as ProductTypeReviewEvidence).verbatim_quote === "string"
  ));
}

export default function ProductTypeReviewCard({ review }: { review: ProductTypeReview }) {
  const titleId = useId();
  const status = knownStatuses.has(review.status) ? review.status as ProductTypeReviewStatus : null;
  const evidence = validEvidence(review.evidence);
  const sourceLabel = review.source && review.source in sourceLabels ? sourceLabels[review.source as keyof typeof sourceLabels] : "历史未记录";
  const actionLabel = review.action && review.action in actionLabels
    ? actionLabels[review.action as keyof typeof actionLabels]
    : status === "likely_non_food" || status === "needs_review" || status === null
      ? actionLabels.continue_with_review
      : "历史未记录";
  const blocked = status === "confirmed_food";
  const confirmed = status === "confirmed_non_food";
  const tone = confirmed
    ? "border-emerald-200 bg-emerald-50 text-emerald-950"
    : blocked ? "border-rose-200 bg-rose-50 text-rose-950" : "border-amber-200 bg-amber-50 text-amber-950";
  const Icon = confirmed ? CheckCircle2 : blocked ? XCircle : ShieldAlert;
  const reasonZh = productTypeReasonZh(review);
  const originalReason = review.reason_original?.trim()
    || (review.reason && !hasChinese(review.reason) ? review.reason.trim() : "");
  return <section aria-labelledby={titleId} className={`border ${tone}`}>
    <div className="flex items-start gap-3 border-b border-current/15 px-4 py-3">
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <div className="min-w-0"><h3 id={titleId} className="text-sm font-semibold">商品类型复核</h3></div>
    </div>
    <dl className="grid gap-3 px-4 py-3 text-sm sm:grid-cols-3">
      <div><dt className="text-xs opacity-70">商品类型结论</dt><dd className="mt-1 font-medium">{status ? statusLabels[status] : "未知商品类型（需要人工复核）"}</dd></div>
      <div><dt className="text-xs opacity-70">判断来源</dt><dd className="mt-1">{sourceLabel}</dd></div>
      <div><dt className="text-xs opacity-70">系统处理</dt><dd className="mt-1 font-medium">{actionLabel}</dd></div>
      <div className="min-w-0 sm:col-span-3">
        <dt className="text-xs opacity-70">判断依据</dt>
        <dd className="mt-1 break-words leading-relaxed">{reasonZh}</dd>
        {originalReason && (
          <details className="mt-2 text-xs">
            <summary className="cursor-pointer font-medium">查看英文原文</summary>
            <p className="mt-2 break-words opacity-80">{originalReason}</p>
          </details>
        )}
      </div>
    </dl>
    {evidence.length > 0 && <ul className="space-y-2 border-t border-current/15 px-4 py-3">
      {evidence.map((item, index) => <li key={`${item.source_field}-${index}`} className="min-w-0 text-sm">
        <span className="font-medium">来源字段：{evidenceFieldLabel(item.source_field)}</span><span className="mx-2 opacity-50">·</span><span className="break-words">原文摘录：{item.verbatim_quote}</span>
      </li>)}
    </ul>}
  </section>;
}
