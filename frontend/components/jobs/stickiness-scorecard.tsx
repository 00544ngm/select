"use client";

import { type RefObject, useState } from "react";
import { CheckCircle2, Clock3, Link2, Search, ShieldAlert, XCircle } from "lucide-react";
import type { ScoreBreakdown, StructuredDirection } from "@/lib/api/types";
import { buildDecisionGuidance } from "@/lib/decision-guidance";
import { directionFinalScore, normalizeExtendedScenarios, normalizeRelationReasons } from "@/lib/result-workbench";
import { evidenceLevelLabel, formatKeywordDisplay, purchaseChainKeyLabel, recommendationDisplayLabel, rejectionCodeLabel, relationLabel } from "@/lib/result-labels";
import ProductTypeReviewCard from "@/components/jobs/product-type-review-card";

const scoreLabels: Array<[keyof ScoreBreakdown, keyof ScoreBreakdown, string]> = [
  ["function_necessity", "relation_strength", "功能必要性"],
  ["usage_continuity", "lifecycle_connection", "使用连续性"],
  ["purchase_direction", "purchase_direction", "购买方向"],
  ["scene_fit", "user_scene", "场景一致性"],
  ["enhancement_maintenance", "function_gain", "增强维护保护"],
  ["natural_copurchase", "mental_copurchase", "自然联购"],
];

const consistencyLabels: Array<[string, string]> = [
  ["user", "用户一致"],
  ["scenario", "场景一致"],
  ["lifecycle", "时间一致"],
  ["mental", "心智一致"],
];

const simulationLabels: Record<string, string> = {
  A: "A · 自然一起购买",
  B: "B · 可能购买",
  C: "C · 需要营销教育",
  D: "D · 不合理",
};

function EvidenceValue({ value }: { value: unknown }) {
  if (typeof value === "string" && value.includes(" ")) return <span>{formatKeywordDisplay(value)}</span>;
  if (Array.isArray(value)) return <span>{value.map((item) => typeof item === "object" ? "已记录" : String(item)).join("、") || "-"}</span>;
  if (value && typeof value === "object") {
    const summary = Object.entries(value as Record<string, unknown>)
      .filter(([, item]) => ["string", "number", "boolean"].includes(typeof item))
      .map(([key, item]) => `${key}: ${String(item)}`)
      .join(" · ");
    return <span>{summary || "已记录"}</span>;
  }
  return <span>{value == null || value === "" ? "-" : String(value)}</span>;
}

function ScoreRow({ label, value }: { label: string; value?: number }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_52px] items-center gap-3 border-b py-2 last:border-b-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <strong className="text-right font-mono text-sm tabular-nums">{value ?? "-"}</strong>
    </div>
  );
}

function GuidanceItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l-2 border-primary/30 pl-3">
      <h3 className="text-xs font-semibold text-muted-foreground">{label}</h3>
      <p className="mt-1 text-sm leading-relaxed">{value}</p>
    </div>
  );
}

type StickinessScorecardProps = {
  direction: StructuredDirection;
  evidenceTargetRef?: RefObject<HTMLDivElement | null>;
  guidanceTargetRef?: RefObject<HTMLDivElement | null>;
  highlightedTarget?: "evidence" | "guidance" | null;
};

export default function StickinessScorecard({
  direction,
  evidenceTargetRef,
  guidanceTargetRef,
  highlightedTarget,
}: StickinessScorecardProps) {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);
  const breakdown = direction.score_breakdown;
  const evidence = direction.evidence ?? {};
  const market = evidence.market && typeof evidence.market === "object"
    ? evidence.market as Record<string, unknown>
    : undefined;
  const consistency = direction.consistency ?? {};
  const isV21 = direction.model_version === "combination_model_v2.1";
  const isV2 = isV21 || direction.model_version === "combination_model_v2.0";
  const rejected = direction.rejected === true;
  const guidance = buildDecisionGuidance(direction);
  const relationReasons = normalizeRelationReasons(direction.relation_reasons);
  const extendedScenarios = normalizeExtendedScenarios(direction.extended_scenarios);
  const rejectionText = direction.rejection_codes?.length
    ? direction.rejection_codes.join("、")
    : "未提供淘汰原因";

  return (
    <section aria-label="全品类购买链路" className="border-t bg-muted/10">
      {direction.product_type_review && <div className="p-4 pb-0"><ProductTypeReviewCard review={direction.product_type_review} /></div>}
      {isV2 && (
        <div className="flex items-center gap-2 border-b px-4 py-3 text-xs font-semibold tracking-wide text-primary">
          <Link2 className="h-4 w-4" aria-hidden="true" />
          <span>{isV21 ? "V2.1 高精准购买链路" : "V2.0 全品类购买链路"}</span>
          <span className="ml-auto text-muted-foreground">{relationLabel(direction.primary_relation)}</span>
        </div>
      )}

      {!isV21 && rejected ? (
        <div className="flex items-start gap-3 border-b border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-900">
          <XCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <strong className="block">已淘汰</strong>
            <span>{rejectionText}</span>
          </div>
        </div>
      ) : !isV21 && direction.score_cap != null && direction.raw_score != null && direction.score_cap < direction.raw_score ? (
        <div className="flex items-start gap-3 border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <div>
            <strong className="block">分数已封顶</strong>
            <span>证据等级 {evidenceLevelLabel(direction.evidence_level)} 限制最高分为 {direction.score_cap}</span>
          </div>
        </div>
      ) : null}

      {isV21 ? (
        <>
          <div className="grid gap-4 border-b p-4 lg:grid-cols-2">
            <div>
              <span className="block text-xs text-muted-foreground">价值判断</span>
              <strong className="mt-1 block text-2xl tabular-nums">粘性潜力：{directionFinalScore(direction)}/100</strong>
            </div>
            <div>
              <span className="block text-xs text-muted-foreground">当前处理建议</span>
              <strong className="mt-1 block text-xl text-primary">{guidance.title}</strong>
            </div>
          </div>
          <div
            ref={guidanceTargetRef}
            role="region"
            aria-label="处理说明"
            tabIndex={-1}
            data-highlighted={highlightedTarget === "guidance" ? "true" : "false"}
            className={`grid gap-4 border-b p-4 outline-none transition-colors lg:grid-cols-3 ${highlightedTarget === "guidance" ? "bg-amber-100 ring-2 ring-amber-400" : ""}`}
          >
            <GuidanceItem label="为什么" value={guidance.reason} />
            <GuidanceItem label="下一步" value={guidance.nextStep} />
            <GuidanceItem label="这意味着" value={guidance.meaning} />
          </div>
        </>
      ) : (
        <div className="grid gap-4 border-b p-4 sm:grid-cols-3">
          <div><span className="block text-xs text-muted-foreground">原始分</span><strong className="mt-1 block text-2xl tabular-nums">{direction.raw_score ?? direction.score ?? "-"}</strong></div>
          <div><span className="block text-xs text-muted-foreground">分数上限</span><strong className="mt-1 block text-2xl tabular-nums">{direction.score_cap ?? "-"}</strong></div>
          <div><span className="block text-xs text-muted-foreground">最终分</span><strong className="mt-1 block text-2xl text-primary tabular-nums">{rejected ? "-" : direction.final_score ?? direction.score ?? "-"}</strong></div>
        </div>
      )}

      <div className="grid gap-6 border-b p-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Link2 className="h-4 w-4" aria-hidden="true" />组合价值评分</h3>
          <div className="border-y">
            {scoreLabels.map(([key, legacyKey, label]) => (
              <ScoreRow key={key} label={label} value={breakdown?.[key] ?? breakdown?.[legacyKey]} />
            ))}
          </div>
        </section>
        <section>
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><Clock3 className="h-4 w-4" aria-hidden="true" />消费者购买链路</h3>
          <dl className="border-y divide-y">
            {Object.entries(direction.purchase_chain ?? {}).map(([key, value], index) => (
              <div key={`${key}-${index}`} className="grid gap-1 py-2 sm:grid-cols-[130px_minmax(0,1fr)] sm:gap-3">
                <dt className="text-xs text-muted-foreground">{purchaseChainKeyLabel(key)}</dt><dd className="text-sm">{typeof value === "string" ? value : "已记录"}</dd>
              </div>
            ))}
          </dl>
        </section>
      </div>

      <div className="grid gap-6 border-b p-4 lg:grid-cols-2">
        <section>
          <h3 className="mb-3 text-sm font-semibold">产品关系依据</h3>
          {relationReasons.length ? (
            <ul className="space-y-2 text-sm">{relationReasons.map((reason, index) => <li key={`${reason}-${index}`} className="border-l-2 border-primary/40 pl-3">{reason}</li>)}</ul>
          ) : <p className="text-sm text-muted-foreground">暂无结构化关系理由</p>}
        </section>
        <section>
          <h3 className="mb-3 text-sm font-semibold">食品过滤</h3>
          <p className="text-sm font-medium">{direction.food_filter_status === "food" ? "已过滤：食品类" : direction.food_filter_status === "allowed" ? "已通过：非食品产品" : "待验证：未确认产品类型"}</p>
          <p className="mt-1 text-sm text-muted-foreground">{direction.food_filter_reason || "-"}</p>
        </section>
      </div>

      {!!extendedScenarios.length && (
        <section className="border-b p-4">
          <h3 className="mb-3 text-sm font-semibold">拓展场景</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {extendedScenarios.map((scenario, index) => (
              <div key={`${scenario.name}-${index}`} className="border bg-background p-3">
                <strong className="text-sm">{scenario.name}</strong>
                <p className="mt-1 text-sm text-muted-foreground">{scenario.reason || "-"}</p>
                <p className="mt-2 text-xs text-muted-foreground">成立前提：{scenario.assumption || "待验证"}</p>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="border-b p-4">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold"><CheckCircle2 className="h-4 w-4" aria-hidden="true" />四一致检测</h3>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {consistencyLabels.map(([key, label]) => {
            const item = consistency[key];
            return <div key={key} className="border bg-background p-3"><div className="flex items-center justify-between gap-2"><span className="text-sm">{label}</span><strong className="font-mono tabular-nums">{item?.score ?? "-"}/5</strong></div><p className="mt-2 text-xs text-muted-foreground">{item?.reason || "-"}</p></div>;
          })}
        </div>
      </section>

      <div className="grid gap-6 border-b p-4 lg:grid-cols-2">
        <section>
          <h3 className="mb-2 text-sm font-semibold">消费者模拟</h3>
          <p className="text-base font-medium">{simulationLabels[direction.consumer_simulation || ""] || direction.consumer_simulation || "-"}</p>
          <p className="mt-1 text-sm text-muted-foreground">{direction.consumer_simulation_reason || "-"}</p>
        </section>
        <section>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Search className="h-4 w-4" aria-hidden="true" />证据来源</h3>
          <dl className="grid gap-2 text-sm sm:grid-cols-[120px_minmax(0,1fr)] sm:items-start">
            <dt className="text-muted-foreground">证据等级</dt><dd>{evidenceLevelLabel(direction.evidence_level)}</dd>
            <dt className="text-muted-foreground">英文搜索词（English）</dt><dd className="min-w-0 break-words"><EvidenceValue value={market?.query} /></dd>
            <dt className="text-muted-foreground">验证时间</dt><dd className="break-all"><EvidenceValue value={market?.verified_at} /></dd>
            <dt className="text-muted-foreground">匹配数量</dt><dd><EvidenceValue value={market?.matched_count} /></dd>
            <dt className="text-muted-foreground">平台状态</dt><dd><EvidenceValue value={direction.market_evidence_status || market?.status || "待验证"} /></dd>
          </dl>
          {Array.isArray(market?.source_urls) && market.source_urls.length > 0 && (
            <details className="mt-3 text-xs text-muted-foreground"><summary className="cursor-pointer">查看原始来源</summary><ul className="mt-2 space-y-1">{market.source_urls.map((url) => <li key={url} className="truncate">{url}</li>)}</ul></details>
          )}
        </section>
      </div>

      <div className="grid gap-6 p-4 lg:grid-cols-2">
        <section><h3 className="mb-2 text-sm font-semibold">风险分析</h3><p className="text-sm text-muted-foreground">{direction.risk_analysis || "-"}</p></section>
        <section
          ref={evidenceTargetRef}
          role="region"
          aria-label="待验证证据"
          tabIndex={-1}
          data-highlighted={highlightedTarget === "evidence" ? "true" : "false"}
          className={`outline-none transition-colors ${highlightedTarget === "evidence" ? "bg-amber-100 p-3 ring-2 ring-amber-400" : ""}`}
        ><h3 className="mb-2 text-sm font-semibold">待验证证据</h3>{direction.missing_evidence?.length ? <ul className="space-y-1 text-sm text-muted-foreground">{direction.missing_evidence.map((item) => <li key={item}>· {item}</li>)}</ul> : <p className="text-sm text-muted-foreground">-</p>}</section>
      </div>
      {isV21 ? (
        <details
          className="border-t px-4 py-3 text-xs text-muted-foreground"
          onToggle={(event) => setShowTechnicalDetails(event.currentTarget.open)}
        >
          <summary className="cursor-pointer font-medium text-foreground">技术详情</summary>
          {showTechnicalDetails && (
            <dl className="mt-3 grid gap-2 sm:grid-cols-[140px_minmax(0,1fr)]">
              <dt>执行状态</dt><dd>{direction.execution_status ?? "-"}</dd>
              <dt>最终动作</dt><dd>{direction.decision_action ?? "-"}</dd>
              <dt>拒绝代码</dt><dd>{direction.rejection_codes?.map(rejectionCodeLabel).join("、") || "-"}</dd>
            </dl>
          )}
        </details>
      ) : (
        !rejected && <div className="border-t px-4 py-3 text-sm"><span className="text-muted-foreground">推荐等级：</span><strong>{recommendationDisplayLabel(direction.recommendation_level)}</strong></div>
      )}
    </section>
  );
}
