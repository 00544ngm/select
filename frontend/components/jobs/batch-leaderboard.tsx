"use client";

import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import ResultSummary from "@/components/jobs/result-summary";
import ResultSections from "@/components/jobs/result-sections";
import { cleanLabel, scoreTone } from "@/lib/result-format";
import type { JobResultPayload, ModelResult } from "@/lib/api/types";
import ProductTypeReviewCard from "@/components/jobs/product-type-review-card";

interface BatchLeaderboardProps {
  results: JobResultPayload[];
}

const MODEL_LABELS: Record<string, string> = {
  gpt: "GPT",
  deepseek: "DeepSeek",
};

/** 批量任务结果：按评分排行，点击行展开该商品的完整结果 */
export default function BatchLeaderboard({ results }: BatchLeaderboardProps) {
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [modelByIdx, setModelByIdx] = useState<Record<number, string>>({});

  const ranked = useMemo(() => {
    const items = results.map((payload, originalIdx) => {
      const primary = primaryResult(payload);
      return {
        originalIdx,
        payload,
        title: primary?.product_title || `商品 ${originalIdx + 1}`,
        productId: primary?.product_id ?? payload.product_id,
        productTitleZh: primary?.product_title_zh ?? payload.product_title_zh,
        score: typeof primary?.score === "number" ? primary.score : null,
        grade: cleanLabel(primary?.grade),
      };
    });
    items.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    return items;
  }, [results]);

  return (
    <div className="space-y-1.5">
      <p className="text-sm font-medium text-muted-foreground">
        本批 {results.length} 个商品 · 按评分排名
      </p>
      {ranked.map((item, rank) => {
        const tone = scoreTone(item.score ?? undefined);
        const isOpen = openIdx === item.originalIdx;
        const models = item.payload.models;
        const modelKeys = Object.keys(models ?? {});
        const hasModels = modelKeys.length > 0;
        const activeModel = modelByIdx[item.originalIdx] && modelKeys.includes(modelByIdx[item.originalIdx])
          ? modelByIdx[item.originalIdx]
          : modelKeys[0];
        const activeResult: ModelResult | undefined = hasModels
          ? (models![activeModel] as ModelResult)
          : (item.payload as unknown as ModelResult);

        return (
          <div key={item.originalIdx} className="rounded-xl border">
            <button
              type="button"
              onClick={() => setOpenIdx(isOpen ? null : item.originalIdx)}
              className="flex w-full items-center gap-3 p-3 text-left"
            >
              <span className="w-6 shrink-0 text-center text-sm text-muted-foreground">
                {rank + 1}
              </span>
              <span className="min-w-0 flex-1 truncate text-sm font-medium">
                {item.title}
              </span>
              {item.grade && (
                <span className="shrink-0 rounded-md bg-sky-50 px-2 py-0.5 text-xs text-sky-800">
                  {item.grade}
                </span>
              )}
              {item.score != null && (
                <span
                  className={`flex h-7 w-11 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${tone.bg} ${tone.text}`}
                >
                  {item.score}
                </span>
              )}
              {isOpen ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              )}
            </button>

            {isOpen && (
              <div className="space-y-4 border-t p-3">
                {activeResult?.product_type_review && <ProductTypeReviewCard review={activeResult.product_type_review} />}
                {modelKeys.length > 1 && (
                  <div className="flex gap-1 rounded-md border p-1">
                    {Object.keys(models!).map((modelKey) => (
                      <button
                        key={modelKey}
                        type="button"
                        onClick={() =>
                          setModelByIdx((prev) => ({
                            ...prev,
                            [item.originalIdx]: modelKey,
                          }))
                        }
                        className={`flex-1 rounded-sm px-3 py-1.5 text-xs font-medium transition-colors ${
                          activeModel === modelKey
                            ? "bg-foreground text-background"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                      >
                        {MODEL_LABELS[modelKey] ?? modelKey}
                      </button>
                    ))}
                  </div>
                )}
                <ResultSummary
                  grade={activeResult?.grade}
                  gradeReason={activeResult?.grade_reason}
                  score={activeResult?.score}
                  scoreReason={activeResult?.score_reason}
                  productId={activeResult?.product_id ?? item.productId}
                  productTitle={activeResult?.product_title ?? item.title}
                  productTitleZh={activeResult?.product_title_zh ?? item.productTitleZh}
                  productImages={activeResult?.product_images ?? item.payload.product_images}
                />
                <ResultSections sections={activeResult?.sections} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function primaryResult(payload: JobResultPayload): ModelResult | undefined {
  const first = Object.values(payload.models ?? {})[0];
  if (first) return first;
  return payload as unknown as ModelResult;
}
