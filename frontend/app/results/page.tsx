"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listJobs, getJob } from "@/lib/api/jobs";
import { queryKeys } from "@/lib/query-keys";
import ResultSummary from "@/components/jobs/result-summary";
import ResultAnalysisModule from "@/components/jobs/result-analysis-module";
import JudgmentAnalysis from "@/components/jobs/judgment-analysis";
import ArtifactActions from "@/components/jobs/artifact-actions";
import { resultModelLabel } from "@/lib/model-label";
import type { JobDetail, JobSummary, ModelResult } from "@/lib/api/types";

export default function ResultsPage() {
  const [selectedJobId, setSelectedJobId] = useState("");
  const [activeModel, setActiveModel] = useState("gpt");

  // Fetch completed jobs for the dropdown
  const { data: jobsData } = useQuery({
    queryKey: queryKeys.jobs.list({ status: "completed" }),
    queryFn: () => listJobs({ status: "completed", page_size: 100 }),
  });

  // Fetch selected job detail
  const { data: job } = useQuery<JobDetail>({
    queryKey: queryKeys.jobs.detail(selectedJobId),
    queryFn: () => getJob(selectedJobId),
    enabled: !!selectedJobId,
  });

  const completedJobs = (jobsData?.items ?? []).filter(
    (j) => j.status === "completed"
  );

  const payload = job?.result_payload;
  const models = payload?.models;
  const hasDual = models && models.gpt && models.deepseek;
  const crossReview = payload?.cross_review as
    | Record<string, { raw?: string; error?: string }>
    | undefined;

  let activeResult: ModelResult | undefined;
  if (hasDual) {
    activeResult = models[activeModel] as ModelResult;
  } else if (payload) {
    activeResult = payload as unknown as ModelResult;
  }
  const isJudgment = job?.mode === "judgment" || activeResult?.mode === "judgment";

  return (
    <div className="flex flex-col min-h-screen">
      {/* Top bar with job selector */}
      <div className="sticky top-0 z-20 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex items-center gap-4 px-6 py-4">
          <h1 className="whitespace-nowrap text-base font-semibold">结果展示</h1>
          <select
            value={selectedJobId}
            onChange={(e) => {
              setSelectedJobId(e.target.value);
              setActiveModel("gpt");
            }}
            className="h-9 max-w-lg flex-1 rounded-md border border-input bg-transparent px-3 text-sm outline-none"
          >
            <option value="">选择已完成任务...</option>
            {completedJobs.map((j: JobSummary) => (
              <option key={j.id} value={j.id}>
                {j.name || j.id.slice(0, 8)} — {j.mode} — {new Date(j.updated_at).toLocaleString("zh-CN")}
              </option>
            ))}
          </select>
          {selectedJobId && (
            <span className="text-xs text-muted-foreground">
              ID: {selectedJobId.slice(0, 8)}...
            </span>
          )}
        </div>
      </div>

      {/* Full-width result area */}
      {selectedJobId && job && job.status === "completed" && payload ? (
        <div className="flex-1 px-6 py-6">
          <div className="space-y-6">
            {/* Model switcher */}
            {hasDual && (
              <div className="flex gap-1 rounded-md border p-1">
                {Object.keys(models).map((modelKey) => (
                  <button
                    key={modelKey}
                    type="button"
                    onClick={() => setActiveModel(modelKey)}
                    className={`flex-1 rounded-sm px-3 py-2 text-sm font-medium transition-colors ${
                      activeModel === modelKey
                        ? "bg-foreground text-background"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {resultModelLabel(modelKey, job.request_payload)}
                  </button>
                ))}
              </div>
            )}

            <ResultSummary
              grade={activeResult?.grade as string | undefined}
              gradeReason={activeResult?.grade_reason as string | undefined}
              score={activeResult?.score as number | undefined}
              scoreReason={activeResult?.score_reason as string | undefined}
              productTitle={payload?.product_title as string | undefined}
            />

            {isJudgment ? (
              <JudgmentAnalysis
                sections={activeResult?.sections}
                grade={activeResult?.grade}
                complementEvidence={activeResult?.complement_evidence}
              />
            ) : (
              <ResultAnalysisModule
                sections={activeResult?.sections}
                structuredDirections={activeResult?.structured_directions}
                productTitle={activeResult?.product_title ?? payload?.product_title}
                productUrl={activeResult?.product_url ?? payload?.product_url}
                productImages={activeResult?.product_images ?? payload?.product_images}
                productPrice={activeResult?.product_price ?? payload?.product_price}
                productRating={activeResult?.product_rating ?? payload?.product_rating}
                productReviewCount={activeResult?.product_review_count ?? payload?.product_review_count}
                keywordPack={activeResult?.keyword_pack ?? payload?.keyword_pack}
                crossReview={crossReview}
                models={models}
              />
            )}

            <ArtifactActions jobId={selectedJobId} activeModel={hasDual ? activeModel : undefined} />
          </div>
        </div>
      ) : selectedJobId && job && job.status !== "completed" ? (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">该任务未完成</p>
        </div>
      ) : (
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-muted-foreground">
            {completedJobs.length === 0
              ? "暂无已完成的任务"
              : "请从上方下拉框选择一个已完成任务"}
          </p>
        </div>
      )}
    </div>
  );
}
