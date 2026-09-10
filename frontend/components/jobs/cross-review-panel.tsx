"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, ArrowLeftRight } from "lucide-react";
import { CrossReviewDocument } from "@/components/jobs/cross-review-document";
import {
  describeCrossReviewEntry,
  extractCrossReviewSummary,
  formatFullIdentity,
} from "@/lib/cross-review-identity";
import { cleanLabel } from "@/lib/result-format";
import type { CrossReviewEntry, CrossReviewState, ModelResult } from "@/lib/api/types";

interface CrossReviewPanelProps {
  crossReview: Record<string, CrossReviewEntry> | CrossReviewState;
  models?: Record<string, ModelResult>;
}

/**
 * 交叉验证展示：顶部摘要徽章（评级是否一致、评分差——由双模型结果直接算出），
 * 评审原文默认折叠、按段落排版。
 */
export default function CrossReviewPanel({ crossReview, models }: CrossReviewPanelProps) {
  const state = crossReview as CrossReviewState;
  const reviewers = state.reviewers ?? [];
  const results = state.results ?? (crossReview as Record<string, CrossReviewEntry>);
  const resultEntries = Object.entries(results).filter(([key, value]) =>
    key !== "status" && key !== "reviewers" && key !== "error" && value && typeof value === "object"
  ) as Array<[string, CrossReviewEntry]>;
  const [openEntry, setOpenEntry] = useState<string | null>(
    resultEntries[0]?.[0] ?? null
  );

  const gpt = models?.gpt;
  const deepseek = models?.deepseek;
  const gradeGpt = cleanLabel(gpt?.grade);
  const gradeDs = cleanLabel(deepseek?.grade);
  const gradesComparable = !!(gradeGpt && gradeDs);
  const gradesMatch = gradesComparable && gradeGpt === gradeDs;
  const scoreDiff =
    typeof gpt?.score === "number" && typeof deepseek?.score === "number"
      ? Math.abs(gpt.score - deepseek.score)
      : null;

  return (
    <div className="space-y-3 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3">
        <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
          <ArrowLeftRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          交叉验证结果
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {reviewers.length === 2 && (
            <span className="text-xs text-muted-foreground">
              {reviewers[0].display_name ?? reviewers[0].provider} · {reviewers[0].api_protocol ?? "openai"} · {reviewers[0].model}
              <span className="mx-1">/</span>
              {reviewers[1].display_name ?? reviewers[1].provider} · {reviewers[1].api_protocol ?? "openai"} · {reviewers[1].model}
            </span>
          )}
          {gradesComparable && (
            <span
              className={`rounded-md px-2 py-0.5 text-xs ${
                gradesMatch
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-amber-50 text-amber-700"
              }`}
            >
              {gradesMatch ? "评级一致" : `评级分歧：${gradeGpt} / ${gradeDs}`}
            </span>
          )}
          {scoreDiff != null && (
            <span className="rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
              评分差 {Math.round(scoreDiff * 10) / 10}
            </span>
          )}
        </span>
      </div>

      <div className="space-y-2">
          {resultEntries.map(([key, review]) => {
            const description = describeCrossReviewEntry(key, reviewers);
            const summary = extractCrossReviewSummary(review.raw);
            const entryOpen = openEntry === key;
            return (
              <div key={key} className="rounded-md border">
                <button
                  type="button"
                  onClick={() => setOpenEntry(entryOpen ? null : key)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-left text-sm font-medium"
                >
                  {description.title}
                  {entryOpen ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  )}
                </button>
                {entryOpen && (
                  <div className="border-t px-4 py-4 sm:px-5">
                    {review.error ? (
                      <p className="text-sm text-destructive">{review.error}</p>
                    ) : (
                      <>
                        <div className="mb-4 grid gap-3 rounded-md bg-muted/30 p-3 text-sm sm:grid-cols-2">
                          <div>
                            <span className="text-muted-foreground">评审模型</span>
                            <strong className="mt-1 block">
                              {formatFullIdentity(description.reviewer)}
                            </strong>
                          </div>
                          <div>
                            <span className="text-muted-foreground">被评审模型</span>
                            <strong className="mt-1 block">
                              {formatFullIdentity(description.reviewed)}
                            </strong>
                          </div>
                          <div>
                            <span className="text-muted-foreground">结论类型</span>
                            <strong className="mt-1 block">{summary.conclusionType}</strong>
                          </div>
                          <div>
                            <span className="text-muted-foreground">一句话结论</span>
                            <strong className="mt-1 block">{summary.conclusion}</strong>
                          </div>
                        </div>
                        <CrossReviewDocument raw={review.raw} />
                        {review.raw && (
                          <RawReviewDisclosure
                            raw={review.raw}
                            testId={`cross-review-raw-${key}`}
                          />
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
      </div>
      {state.status && state.status !== "completed" && (
        <p className={state.status === "failed" ? "text-sm text-destructive" : "text-sm text-muted-foreground"}>
          {state.status === "queued" ? "交叉验证已排队，等待执行" : state.status === "running" ? "交叉验证正在执行" : state.error ?? "交叉验证失败"}
        </p>
      )}
    </div>
  );
}

function RawReviewDisclosure({ raw, testId }: { raw: string; testId: string }) {
  const [open, setOpen] = useState(false);

  return (
    <details
      className="mt-5 border-t pt-3 text-xs text-muted-foreground"
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer font-medium text-foreground">
        查看模型原文
      </summary>
      {open && (
        <pre
          data-testid={testId}
          className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap rounded-md bg-muted/40 p-3 font-mono text-xs leading-6"
        >
          {raw}
        </pre>
      )}
    </details>
  );
}
