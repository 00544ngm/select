"use client";

import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  CircleAlert,
  ExternalLink,
  ShieldCheck,
  ShieldX,
} from "lucide-react";
import type {
  ComplementEvidenceRecord,
  ComplementEvidenceStatus,
} from "@/lib/api/types";
import type { PerBProduct } from "@/lib/result-format";

interface Props {
  product: PerBProduct;
  evidence?: ComplementEvidenceRecord;
}

const RISK_ROWS: Array<{
  label: string;
  key: keyof NonNullable<PerBProduct["vetoRisks"]>;
}> = [
  { label: "节奏不匹配", key: "rhythm" },
  { label: "竞品冲突", key: "competition" },
  { label: "品牌压制", key: "brandOvershadow" },
  { label: "物流问题", key: "logistics" },
  { label: "法律风险", key: "legal" },
  { label: "差评超标", key: "badReviews" },
];

const EVIDENCE_STATUS: Record<
  ComplementEvidenceStatus,
  { label: string; detail: string; className: string }
> = {
  verified: {
    label: "已验证",
    detail: "消费者评论中存在达到验证门槛的可追溯互补需求。",
    className: "bg-emerald-50 text-emerald-800",
  },
  signal: {
    label: "有需求线索",
    detail: "已发现相关评论，但数量或证据强度尚未达到验证门槛。",
    className: "bg-sky-50 text-sky-800",
  },
  not_found: {
    label: "暂未发现",
    detail: "当前有效样本中未发现相关评论，不代表市场需求不存在。",
    className: "bg-slate-100 text-slate-700",
  },
  insufficient: {
    label: "样本不足",
    detail: "有效评论数量不足，当前不能作出可靠判断。",
    className: "bg-amber-50 text-amber-800",
  },
  analysis_failed: {
    label: "分析失败",
    detail: "评论已抓取，但证据分类没有成功，可重新运行验证。",
    className: "bg-red-50 text-red-800",
  },
};

export default function VetoReviewPanel({ product, evidence }: Props) {
  const [showEvidence, setShowEvidence] = useState(false);
  const status = evidence ? EVIDENCE_STATUS[evidence.status] : undefined;
  const headerClass = product.vetoed
    ? "border-red-200 bg-red-50/70"
    : "border-emerald-200 bg-emerald-50/70";
  const verdictClass = product.vetoed
    ? "bg-red-100 text-red-800"
    : "bg-emerald-100 text-emerald-800";

  return (
    <section className="overflow-hidden rounded-lg border bg-background">
      <div className={"border-b px-4 py-3 " + headerClass}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold">否决审查</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {product.vetoed
                ? "已触发一票否决条件"
                : "未触发任何一票否决条件"}
            </p>
          </div>
          <span
            className={
              "inline-flex h-7 shrink-0 items-center gap-1 rounded-md px-2 text-xs font-semibold " +
              verdictClass
            }
          >
            {product.vetoed ? (
              <ShieldX className="h-3.5 w-3.5" />
            ) : (
              <ShieldCheck className="h-3.5 w-3.5" />
            )}
            {product.vetoed ? "未通过" : "通过"}
          </span>
        </div>
        {product.vetoed && product.vetoReason && (
          <p className="mt-2 text-sm text-red-800">
            否决原因：{product.vetoReason}
          </p>
        )}
      </div>

      <div className="p-4">
        <p className="text-xs font-semibold text-muted-foreground">风险检查</p>
        <div className="mt-2 divide-y">
          {RISK_ROWS.map((row) => (
            <RiskRow
              key={row.key}
              label={row.label}
              triggered={product.vetoRisks?.[row.key]}
            />
          ))}
        </div>

        <div className="mt-5 border-t pt-4">
          <p className="text-xs font-semibold text-muted-foreground">正向证据</p>
          <div className="mt-2 rounded-md border bg-muted/20 p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-sm font-medium">互补需求证据</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                  {status
                    ? status.detail
                    : "没有保存评论证据明细，建议重新运行验证"}
                </p>
              </div>
              <span
                className={
                  "shrink-0 rounded-md px-2 py-1 text-xs font-semibold " +
                  (status?.className ?? "bg-amber-50 text-amber-800")
                }
              >
                {status?.label ?? legacyStatus(product.legacyG3Validated)}
              </span>
            </div>

            {evidence && (
              <>
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                  <span>数据来源 {evidence.platform}</span>
                  <span>抽样评论 {evidence.valid_review_count} 条</span>
                  <span>相关评论 {evidence.relevant_review_count} 条</span>
                  <span>命中比例 {(evidence.hit_rate * 100).toFixed(1)}%</span>
                </div>
                {evidence.failure_reason && (
                  <p className="mt-2 text-xs text-amber-800">
                    {evidence.failure_reason}
                  </p>
                )}
                {evidence.evidence.length > 0 && (
                  <div className="mt-3 border-t pt-3">
                    <button
                      type="button"
                      onClick={() => setShowEvidence((value) => !value)}
                      aria-expanded={showEvidence}
                      className="inline-flex items-center gap-1 text-xs font-medium text-foreground hover:text-primary"
                    >
                      {showEvidence ? "收起证据原文" : "查看证据原文"}
                      <ChevronDown
                        className={
                          "h-3.5 w-3.5 transition-transform " +
                          (showEvidence ? "rotate-180" : "")
                        }
                      />
                    </button>
                    {showEvidence && (
                      <div className="mt-3 space-y-3">
                        {evidence.evidence.map((item) => (
                          <article
                            key={item.review_index}
                            className="rounded-md border bg-background p-3"
                          >
                            <p className="text-xs leading-relaxed text-foreground">
                              {item.original_text}
                            </p>
                            {item.translation_zh && (
                              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                                {item.translation_zh}
                              </p>
                            )}
                            {item.reason && (
                              <p className="mt-2 text-xs text-sky-800">
                                {item.reason}
                              </p>
                            )}
                            {item.keywords.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {item.keywords.map((keyword) => (
                                  <span
                                    key={keyword}
                                    className="rounded bg-sky-50 px-1.5 py-0.5 text-[11px] text-sky-800"
                                  >
                                    {keyword}
                                  </span>
                                ))}
                              </div>
                            )}
                            {item.source_url && (
                              <a
                                href={item.source_url}
                                target="_blank"
                                rel="noreferrer"
                                className="mt-2 inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
                              >
                                查看商品来源
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </article>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function RiskRow({
  label,
  triggered,
}: {
  label: string;
  triggered?: boolean;
}) {
  const tone =
    triggered === true
      ? "text-red-700"
      : triggered === false
        ? "text-emerald-700"
        : "text-muted-foreground";
  return (
    <div className="flex min-h-9 items-center justify-between gap-4 py-1.5">
      <span className="text-sm">{label}</span>
      <span className={"inline-flex items-center gap-1 text-xs font-medium " + tone}>
        {triggered === true ? (
          <CircleAlert className="h-3.5 w-3.5" />
        ) : triggered === false ? (
          <CheckCircle2 className="h-3.5 w-3.5" />
        ) : null}
        {triggered === true
          ? "已触发"
          : triggered === false
            ? "未触发"
            : "未提供"}
      </span>
    </div>
  );
}

function legacyStatus(value: boolean | undefined): string {
  return value
    ? "旧任务初判：已验证"
    : "旧任务初判：暂未确认";
}
