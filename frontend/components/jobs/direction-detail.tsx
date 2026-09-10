"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { directionFinalScore, directionQuery, normalizeExtendedScenarios, normalizeRelationReasons, splitDirectionName } from "@/lib/result-workbench";
import type { StructuredDirection } from "@/lib/api/types";
import PlatformSearchPanel, { type SearchState } from "@/components/jobs/platform-search-panel";
import DirectionKeywordAccordions from "@/components/jobs/direction-keyword-accordions";
import StickinessScorecard from "@/components/jobs/stickiness-scorecard";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { buildDecisionGuidance } from "@/lib/decision-guidance";
import { deepArgumentKeyLabel, evidenceLevelLabel, formatStrategy, relationLabel } from "@/lib/result-labels";

const labels: Record<string, string> = {
  user_rationale: "用户理由", seller_rationale: "卖家理由", urgency: "购买紧迫性",
  differentiation: "差异化", risk_mitigation: "风险控制", scenario_fit: "场景适配",
  rationale_score: "理由评分", bundling_display: "组合展示",
  listing_highlights: "Listing 卖点", pricing_tactic: "定价动作", launch_actions: "上线动作",
};

function DisplayValue({ value }: { value: unknown }) {
  if (Array.isArray(value)) return <ul>{value.map((item, i) => <li key={i}>· <DisplayValue value={item} /></li>)}</ul>;
  if (value && typeof value === "object") {
    return <dl className="space-y-1">{Object.entries(value as Record<string, unknown>).map(([key, item]) => <div key={key} className="grid gap-1 sm:grid-cols-[150px_minmax(0,1fr)]"><dt className="text-muted-foreground">{deepArgumentKeyLabel(key)}</dt><dd><DisplayValue value={item} /></dd></div>)}</dl>;
  }
  if (typeof value === "boolean") return <span>{value ? "是（true）" : "否（false）"}</span>;
  return <span>{value == null || value === "" ? "-" : String(value)}</span>;
}

function DetailGroup({ title, data }: { title: string; data?: Record<string, unknown> }) {
  if (!data || Object.keys(data).length === 0) return null;
  if (title === "一致性评分" && data.consistency && typeof data.consistency === "object") {
    return <section className="border bg-background p-4 shadow-sm"><h3 className="mb-3 text-sm font-semibold">{title}</h3><div className="space-y-3">{Object.entries(data.consistency as Record<string, unknown>).map(([dimension, value]) => {
      const item = value && typeof value === "object" ? value as Record<string, unknown> : { score: value };
      return <div key={dimension} className="border-l-2 border-primary/30 pl-3"><div className="flex flex-wrap items-center justify-between gap-2"><span className="text-sm font-medium">{deepArgumentKeyLabel(dimension)}</span><span className="rounded-md bg-primary/10 px-2 py-0.5 text-sm font-semibold tabular-nums">{deepArgumentKeyLabel("score")}：{String(item.score ?? "-")}/5</span></div><p className="mt-1 text-sm leading-relaxed text-muted-foreground">{deepArgumentKeyLabel("reason")}：{String(item.reason ?? "-")}</p></div>;
    })}</div></section>;
  }
  if (title === "扩展场景" && Array.isArray(data.extended_scenarios)) {
    return <section className="border bg-background p-4 shadow-sm"><h3 className="mb-3 text-sm font-semibold">{title}</h3><div className="grid gap-3">{(data.extended_scenarios as Array<Record<string, unknown>>).map((scenario, index) => <article key={`${String(scenario.name ?? index)}-${index}`} className="border-l-2 border-primary/30 pl-3"><h4 className="text-sm font-semibold">{deepArgumentKeyLabel("name")}：{String(scenario.name ?? "-")}</h4><p className="mt-1 text-sm leading-relaxed"><span className="font-medium text-muted-foreground">场景理由： </span>{String(scenario.reason ?? "-")}</p><p className="mt-1 text-sm leading-relaxed text-muted-foreground"><span className="font-medium">场景假设： </span>{String(scenario.assumption ?? "-")}</p></article>)}</div></section>;
  }
  return <section className="border bg-background p-4 shadow-sm"><h3 className="mb-3 text-sm font-semibold">{title}</h3><dl className="space-y-3">
    {Object.entries(data).map(([key, value]) => <div key={key} className="border-l-2 border-primary/30 pl-3">
      <dt className="text-sm text-muted-foreground">{title === "购买链路" ? "步骤明细" : labels[key] ?? deepArgumentKeyLabel(key)}</dt>
      <dd className="analysis-copy mt-1 min-w-0 text-sm leading-relaxed"><DisplayValue value={value} /></dd>
    </div>)}
  </dl></section>;
}

function DeepAnalysisGroups({ direction }: { direction: StructuredDirection }) {
  const deep = direction.deep_arguments ?? {};
  const groupedKeys = new Set(["assumptions", "consistency", "purchase_chain", "relation_reasons", "extended_scenarios"]);
  const residualDeep = Object.fromEntries(Object.entries(deep).filter(([key]) => !groupedKeys.has(key)));
  const groups = [
    { title: "分析假设", data: direction.assumptions?.length ? { assumptions: direction.assumptions } : Array.isArray(deep.assumptions) ? { assumptions: deep.assumptions } : undefined },
    { title: "一致性评分", data: direction.consistency ? { consistency: direction.consistency } : deep.consistency && typeof deep.consistency === "object" ? { consistency: deep.consistency } : undefined },
    { title: "购买链路", data: direction.purchase_chain ? { steps: direction.purchase_chain } : deep.purchase_chain && typeof deep.purchase_chain === "object" ? { steps: deep.purchase_chain } : undefined },
    { title: "关系依据", data: direction.relation_reasons?.length ? { relation_reasons: direction.relation_reasons } : undefined },
    { title: "扩展场景", data: direction.extended_scenarios?.length ? { extended_scenarios: direction.extended_scenarios } : undefined },
    { title: "交付检查", data: direction.delivery_checklist },
    { title: "深度依据", data: residualDeep },
  ].filter((group) => group.data && Object.keys(group.data).length > 0);
  if (!groups.length) return null;
  return <section className="border-t pt-4"><div className="mb-3 flex items-center justify-between gap-3"><h3 className="text-sm font-semibold">深度分析分组</h3><span className="text-xs text-muted-foreground">按结论 → 依据阅读</span></div><div className="grid gap-3 md:grid-cols-2">{groups.map((group) => <DetailGroup key={group.title} title={group.title} data={group.data} />)}</div></section>;
}

function StructuredAnalysis({ direction }: { direction: StructuredDirection }) {
  const reasons = normalizeRelationReasons(direction.relation_reasons);
  const scenarios = normalizeExtendedScenarios(direction.extended_scenarios);
  if (!reasons.length && !scenarios.length && !direction.assumptions?.length) return null;
  return <section className="border-t pt-4">
    <h3 className="mb-3 text-sm font-semibold">结构化组合分析</h3>
    {reasons.length > 0 && <div className="mb-4"><h4 className="text-xs font-semibold text-muted-foreground">关系依据</h4><ul className="mt-2 space-y-1 text-sm">{reasons.map((reason) => <li key={reason}>· {reason}</li>)}</ul></div>}
    {scenarios.length > 0 && <div className="mb-4"><h4 className="text-xs font-semibold text-muted-foreground">拓展场景</h4><div className="mt-2 grid gap-2 sm:grid-cols-2">{scenarios.map((scenario) => <div key={scenario.name} className="border p-3 text-sm"><strong>{scenario.name}</strong><p className="mt-1 text-muted-foreground">{scenario.reason || "-"}</p><p className="mt-1 text-xs text-muted-foreground">成立前提：{scenario.assumption || "待验证"}</p></div>)}</div></div>}
    {!!direction.assumptions?.length && <div><h4 className="text-xs font-semibold text-muted-foreground">统一前提</h4><ul className="mt-2 space-y-1 text-sm">{direction.assumptions.map((assumption) => <li key={assumption}>· {assumption}</li>)}</ul></div>}
  </section>;
}

export default function DirectionDetail({ direction, searchState, onSearchState }: { direction: StructuredDirection; searchState: SearchState; onSearchState: (state: SearchState) => void }) {
  const [showDeepAnalysis, setShowDeepAnalysis] = useState(false);
  const [pendingFocusTarget, setPendingFocusTarget] = useState<"evidence" | "guidance" | null>(null);
  const [highlightedTarget, setHighlightedTarget] = useState<"evidence" | "guidance" | null>(null);
  const evidenceTargetRef = useRef<HTMLDivElement>(null);
  const guidanceTargetRef = useRef<HTMLDivElement>(null);
  const name = splitDirectionName(direction.name);
  const query = directionQuery(direction);
  const guidance = buildDecisionGuidance(direction);
  const coreReason = direction.direction_reason || direction.motivation || direction.motivation_evidence || "暂无核心理由";
  const chain = Object.entries(direction.purchase_chain ?? {}).filter(([, value]) => typeof value === "string" && value.trim());
  const metrics = [["组合类型", relationLabel(direction.type)], ["粘性等级", direction.stickiness], ["证据层级", evidenceLevelLabel(direction.evidence_level)]];
  const reviewEvidence = () => {
    setShowDeepAnalysis(true);
    setPendingFocusTarget(direction.missing_evidence?.length ? "evidence" : "guidance");
  };
  const reviewHistoricalGuidance = () => {
    setShowDeepAnalysis(true);
    setPendingFocusTarget("guidance");
  };

  useEffect(() => {
    if (!showDeepAnalysis || !pendingFocusTarget) return;
    const target = pendingFocusTarget === "evidence"
      ? evidenceTargetRef.current
      : guidanceTargetRef.current;
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    target?.focus({ preventScroll: true });
    setHighlightedTarget(pendingFocusTarget);
    setPendingFocusTarget(null);
  }, [pendingFocusTarget, showDeepAnalysis]);

  useEffect(() => {
    if (!highlightedTarget) return;
    const timeout = window.setTimeout(() => setHighlightedTarget(null), 1800);
    return () => window.clearTimeout(timeout);
  }, [highlightedTarget]);

  useEffect(() => {
    setPendingFocusTarget(null);
    setHighlightedTarget(null);
  }, [direction.name]);

  return <article className="min-w-0 p-4 sm:p-5">
    <Card className="mb-5 border-primary/20 bg-primary/[0.03] shadow-none">
      <CardHeader className="gap-2 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">结论摘要</CardTitle>
          <div className="flex items-center gap-2">
            {guidance.status === "hold" || guidance.status === "historical_incomplete" ? (
              <button
                type="button"
                aria-label={guidance.status === "hold" ? "查看待补证据" : "查看历史判定说明"}
                onClick={guidance.status === "hold" ? reviewEvidence : reviewHistoricalGuidance}
                className="rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
              >
                <Badge variant="default" className="cursor-pointer">{guidance.title}</Badge>
              </button>
            ) : (
              <Badge variant={guidance.status === "reject" ? "destructive" : "default"}>{guidance.title}</Badge>
            )}
            <span className="rounded-md border bg-background px-2.5 py-1 text-sm font-semibold tabular-nums">粘性潜力：{directionFinalScore(direction)}/100</span>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div>
          <p className="text-xs font-medium text-muted-foreground">核心理由</p>
          <p className="mt-1 text-sm leading-relaxed">{coreReason}</p>
        </div>
        <div>
          <p className="text-xs font-medium text-muted-foreground">购买链路</p>
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            {(chain.length ? chain.slice(0, 3) : [["before_use", "暂无购买链路"]]).map(([key, value], index) => (
              <div key={`${key}-${index}`} className="relative border bg-background p-3">
                <span className="text-[11px] font-semibold text-primary">0{index + 1}</span>
                <p className="mt-1 text-xs text-muted-foreground">{key === "before" || key === "before_use" ? "购买前" : key === "using_main" || key === "primary_use" ? "使用主品" : "使用辅品"}</p>
                <p className="mt-1 text-sm leading-relaxed">{value}</p>
              </div>
            ))}
          </div>
        </div>
        <button type="button" aria-expanded={showDeepAnalysis} onClick={() => setShowDeepAnalysis((open) => !open)} className="flex w-full items-center justify-between gap-3 rounded-md border border-primary bg-primary px-4 py-3 text-left text-sm font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2">
          <span>深度分析（点击展开）</span>
          {showDeepAnalysis ? <ChevronDown className="h-4 w-4" aria-hidden="true" /> : <ChevronRight className="h-4 w-4" aria-hidden="true" />}
        </button>
      </CardContent>
    </Card>
    <header className="flex flex-wrap items-start justify-between gap-3 border-b pb-4">
      <div className="min-w-0"><h2 className="text-xl font-semibold" aria-label={name.zh}>{name.zh}</h2>{name.en && <p className="keyword-text mt-1 text-muted-foreground">{name.en}</p>}</div>
      <div className="flex items-center gap-2"><span className="border bg-success/10 px-2 py-1 text-xs text-success">{evidenceLevelLabel(direction.evidence_level)}</span><strong className="min-w-12 border bg-primary px-2 py-1 text-center text-lg text-primary-foreground tabular-nums">{directionFinalScore(direction) || "-"}</strong></div>
    </header>
    <dl className="grid border-b sm:grid-cols-2 xl:grid-cols-3">{metrics.map(([label, value]) => <div key={label} className="border-b p-3 sm:border-r"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-sm font-medium">{value || "-"}</dd></div>)}</dl>
    <DirectionKeywordAccordions keywords={direction.keywords ?? query} />
    <PlatformSearchPanel direction={direction} state={searchState} onChange={onSearchState} />
    {showDeepAnalysis && <div className="mt-5 space-y-4 border-t pt-4"><StickinessScorecard direction={direction} evidenceTargetRef={evidenceTargetRef} guidanceTargetRef={guidanceTargetRef} highlightedTarget={highlightedTarget} />
      {direction.motivation_evidence && <section className="border-t pt-4"><h3 className="text-sm font-semibold">原始动机证据</h3><p className="analysis-copy mt-2 text-sm text-muted-foreground">{direction.motivation_evidence}</p></section>}
      <DeepAnalysisGroups direction={direction} />
      {(direction.deep_arguments || direction.delivery_checklist) && <details className="mt-4 border-t pt-4 text-xs text-muted-foreground"><summary className="cursor-pointer">查看原始数据</summary><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap">{JSON.stringify({ deep_arguments: direction.deep_arguments ?? {}, delivery_checklist: direction.delivery_checklist ?? {} }, null, 2)}</pre></details>}
    </div>}
  </article>;
}
