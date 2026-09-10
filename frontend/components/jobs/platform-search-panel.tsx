"use client";

import { Search } from "lucide-react";
import ProductMedia from "@/components/jobs/product-media";
import { searchWalmart } from "@/lib/api/search";
import { directionQuery } from "@/lib/result-workbench";
import type { SearchProduct, StructuredDirection } from "@/lib/api/types";

export type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; results: SearchProduct[] }
  | { status: "empty" }
  | { status: "error"; message: string };

export default function PlatformSearchPanel({ direction, state, onChange }: {
  direction: StructuredDirection;
  state: SearchState;
  onChange: (state: SearchState) => void;
}) {
  const query = directionQuery(direction);

  const runSearch = async () => {
    if (!query) return;
    onChange({ status: "loading" });
    try {
      const response = await searchWalmart(query);
      onChange(response.results.length ? { status: "success", results: response.results } : { status: "empty" });
    } catch (error) {
      onChange({ status: "error", message: error instanceof Error ? error.message : "未知搜索错误" });
    }
  };

  return <section className="border-t pt-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div><h3 className="text-sm font-semibold">平台核验</h3><p className="mt-1 text-xs text-muted-foreground">按需查询，不影响原分析任务和分数。</p></div>
      <span className="border bg-muted/30 px-2 py-1 text-xs">{state.status === "idle" ? "待核验" : state.status === "loading" ? "搜索中" : state.status === "success" ? "平台已返回" : state.status === "empty" ? "无结果" : "搜索失败"}</span>
    </div>
    <div className="mt-3 flex flex-wrap gap-2">
      <button type="button" aria-label="核验 Walmart" disabled={!query || state.status === "loading"} onClick={runSearch} className="inline-flex items-center gap-2 border bg-primary px-3 py-2 text-sm text-primary-foreground disabled:opacity-50"><Search className="h-4 w-4" />{state.status === "loading" ? "搜索中..." : "核验 Walmart"}</button>
    </div>
    {!query && <p className="mt-3 text-sm text-warning-foreground">暂无可核验关键词</p>}
    {state.status === "error" && <div className="mt-3 border border-destructive/30 bg-destructive/5 p-3"><p className="text-sm text-muted-foreground">{state.message}</p></div>}
    {state.status === "empty" && <p className="mt-3 border bg-muted/20 p-3 text-sm text-muted-foreground">本次未找到平台候选商品</p>}
    {state.status === "success" && <div className="mt-4 space-y-2">{state.results.map((product) => <a key={product.url} href={product.url} target="_blank" rel="noreferrer" className="grid gap-3 border p-3 transition-colors hover:bg-muted/20 sm:grid-cols-[80px_minmax(0,1fr)]">
      <ProductMedia src={product.image} alt={product.title} emptyLabel="平台未返回图片" className="w-20" />
      <span className="min-w-0"><span className="flex flex-wrap gap-2"><span className="border bg-sky-50 px-1.5 py-0.5 text-xs text-sky-800">平台实际返回</span><span className="border bg-warning/10 px-1.5 py-0.5 text-xs text-warning-foreground">相似候选（未确认精准）</span></span><strong className="mt-2 block text-sm">{product.title}</strong><span className="mt-1 block text-xs text-muted-foreground">{[product.price, product.rating && "评分 " + product.rating, product.review_count && "评论 " + product.review_count].filter(Boolean).join(" · ")}</span></span>
    </a>)}</div>}
  </section>;
}
