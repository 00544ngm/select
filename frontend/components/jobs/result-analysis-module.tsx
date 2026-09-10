"use client";

import { useEffect, useMemo, useState } from "react";
import DirectionDetail from "@/components/jobs/direction-detail";
import DirectionList from "@/components/jobs/direction-list";
import ProductMedia from "@/components/jobs/product-media";
import ResultSections from "@/components/jobs/result-sections";
import CrossReviewPanel from "@/components/jobs/cross-review-panel";
import { directionFinalScore, directionQuery, highestDirection } from "@/lib/result-workbench";
import type { CrossReviewEntry, ModelResult, StructuredDirection } from "@/lib/api/types";
import type { ResultStatus } from "@/lib/api/types";
import type { ProductTypeReview, RejectedBProduct } from "@/lib/api/types";
import ProductTypeReviewCard from "@/components/jobs/product-type-review-card";
import type { SearchState } from "@/components/jobs/platform-search-panel";

export interface ResultSection { title: string; content?: string; children?: ResultSection[]; }
interface Props {
  sections?: ResultSection[]; structuredDirections?: StructuredDirection[]; productId?: string; productTitle?: string; productTitleZh?: string;
  productUrl?: string; productImages?: string[]; productPrice?: string; productRating?: string;
  productReviewCount?: string; keywordPack?: string[]; crossReview?: Record<string, CrossReviewEntry>;
  models?: Record<string, ModelResult>;
  modelVersion?: string; resultStatus?: ResultStatus; resultMessage?: string;
  auditOutcome?: string; rejectionSummary?: Record<string, number>;
  productTypeReview?: ProductTypeReview; rejectedBProducts?: RejectedBProduct[];
}
type View = "directions" | "evidence" | "keywords" | "cross-review";

export default function ResultAnalysisModule(props: Props) {
  const directions = useMemo(() => props.structuredDirections ?? [], [props.structuredDirections]);
  const highest = highestDirection(directions);
  const [activeName, setActiveName] = useState(highest?.name ?? "");
  const [view, setView] = useState<View>("directions");
  const [searchStates, setSearchStates] = useState<Record<string, SearchState>>({});
  useEffect(() => { if (!directions.some((item) => item.name === activeName)) setActiveName(highestDirection(directions)?.name ?? ""); }, [activeName, directions]);
  const active = directions.find((item) => item.name === activeName) ?? highest;
  const activeSearchKey = active ? `${active.name}\u0000${directionQuery(active)}` : "";
  const evidenceSections = useMemo(
    () => (props.sections ?? []).filter((section) =>
      ["商品分析", "证据表", "策略判断"].some((label) => section.title.includes(label))
    ),
    [props.sections]
  );
  const isV21 = props.modelVersion === "combination_model_v2.1";
  const statusNotice = props.resultStatus === "completed_needs_evidence" ? (
    <div className="border-l-4 border-amber-500 bg-amber-50 px-4 py-3 text-sm text-amber-950">
      {props.resultMessage || "发现潜在方向，但当前不可执行"}
    </div>
  ) : null;
  const rejectedProducts = props.rejectedBProducts?.length ? <section className="space-y-3 border border-rose-200 bg-rose-50/50 p-4" aria-labelledby="rejected-food-title">
    <h2 id="rejected-food-title" className="text-sm font-semibold text-rose-950">食品辅品不准入</h2>
    {props.rejectedBProducts.map((item, index) => <div key={`${item.url ?? item.title ?? "food"}-${index}`} className="space-y-2">
      <p className="break-words text-sm font-medium text-rose-950">{item.title || "未记录商品标题"}：确认为食品，不符合准入范围</p>
      {item.review && <ProductTypeReviewCard review={item.review} />}
    </div>)}
  </section> : null;
  if (!directions.length) {
    const isV21Zero = isV21 && props.resultStatus === "completed_no_qualified_candidates";
    const rejectionEntries = Object.entries(props.rejectionSummary ?? {});
    const emptyMessage = isV21Zero
      ? props.resultMessage || "分析已完成，未发现达到高粘性门槛的辅品。"
      : props.modelVersion === "combination_model_v2.0"
        ? "历史 V2.0 快照，未保存结构化方向"
        : "历史结果暂无结构化方向";
    return <div className="space-y-3">
      {props.productTypeReview && <ProductTypeReviewCard review={props.productTypeReview} />}
      {rejectedProducts}
      <div className={isV21Zero ? "border-l-4 border-rose-500 bg-rose-50 px-4 py-3" : "border bg-warning/10 px-3 py-2"}>
        <p className="text-sm leading-relaxed">{emptyMessage}</p>
        {isV21Zero && props.auditOutcome === "confirmed_no_candidates" && <p className="mt-2 text-xs font-medium text-rose-800">遗漏复核已完成</p>}
        {isV21Zero && rejectionEntries.length > 0 && <div className="mt-2 flex flex-wrap gap-2">{rejectionEntries.map(([code, count]) => <span key={code} className="border border-rose-200 bg-white px-2 py-1 text-xs text-rose-900">{code} · {count}</span>)}</div>}
      </div>
      <ResultSections sections={props.sections} />
      {props.crossReview && Object.keys(props.crossReview).length > 0 && <CrossReviewPanel crossReview={props.crossReview} models={props.models} />}
    </div>;
  }
  const views: Array<[View, string]> = [["directions", "方向研究"], ["evidence", "商品与证据"], ["keywords", "关键词包"], ["cross-review", "交叉验证"]];
  return <div className="space-y-3">{props.productTypeReview && <ProductTypeReviewCard review={props.productTypeReview} />}{rejectedProducts}{statusNotice}<section className="overflow-hidden border bg-background">
    <div className="grid gap-4 border-b p-4 sm:grid-cols-[96px_minmax(0,1fr)_auto] sm:items-center">
      <ProductMedia src={props.productImages} alt={props.productTitle || props.productTitleZh || "主品图片"} emptyLabel="历史无图" className="w-24" />
      <div className="min-w-0"><p className="text-xs font-medium text-primary">原始主品</p>{props.productId && <p className="mt-1 text-xs text-muted-foreground"><span>商品 ID：</span><span>{props.productId}</span></p>}{props.productTitleZh && <p className="mt-1 font-semibold leading-relaxed">{props.productTitleZh}</p>}{props.productUrl ? <a href={props.productUrl} target="_blank" rel="noreferrer" className="mt-1 block text-sm text-muted-foreground hover:underline"><span>原始标题：</span><span>{props.productTitle || "未保存主品标题"}</span></a> : <p className="mt-1 text-sm text-muted-foreground"><span>原始标题：</span><span>{props.productTitle || "未保存主品标题"}</span></p>}<div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">{props.productPrice && <span>价格 {props.productPrice}</span>}{props.productRating && <span>评分 {props.productRating}</span>}{props.productReviewCount && <span>评论 {props.productReviewCount}</span>}</div></div>
      <div className="sm:text-right"><span className="text-xs text-muted-foreground">最高方向分</span><strong className="block text-2xl text-primary">{highest ? directionFinalScore(highest) : "-"}</strong></div>
    </div>
    <div className="flex overflow-x-auto border-b bg-muted/20 p-1" role="tablist" aria-label="结果视图">{views.map(([key, label]) => <button key={key} role="tab" aria-selected={view === key} onClick={() => setView(key)} className={view === key ? "shrink-0 border-b-2 border-primary px-4 py-2 text-sm font-medium" : "shrink-0 border-b-2 border-transparent px-4 py-2 text-sm text-muted-foreground"}>{label}</button>)}</div>
    {view === "directions" && active && <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] lg:grid-cols-[300px_minmax(0,1fr)]"><DirectionList directions={directions} activeName={active.name} onSelect={(item) => setActiveName(item.name)} /><DirectionDetail direction={active} searchState={searchStates[activeSearchKey] ?? { status: "idle" }} onSearchState={(state) => setSearchStates((current) => ({ ...current, [activeSearchKey]: state }))} /></div>}
    {view === "evidence" && <div className="p-4"><ResultSections sections={evidenceSections} /></div>}
    {view === "keywords" && <div className="p-4">{props.keywordPack?.length ? <ul className="grid gap-2 sm:grid-cols-2">{props.keywordPack.map((word) => <li key={word} className="keyword-text border px-3 py-2">{word}</li>)}</ul> : <p>当前结果没有保存关键词包</p>}</div>}
    {view === "cross-review" && (props.crossReview && Object.keys(props.crossReview).length ? <CrossReviewPanel crossReview={props.crossReview} models={props.models} /> : <p className="p-6 text-sm text-muted-foreground">当前任务没有交叉验证结果</p>)}
  </section></div>;
}
