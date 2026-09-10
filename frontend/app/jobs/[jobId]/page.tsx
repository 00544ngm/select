"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getJob, retryJob } from "@/lib/api/jobs";
import { listProviders } from "@/lib/api/providers";
import { providerModelOptions } from "@/lib/model-identity";
import { isFreshVerifiedModel } from "@/lib/provider-model-status";
import { triggerCrossReview } from "@/lib/api/cross-review";
import { queryKeys } from "@/lib/query-keys";
import { getJobPollingInterval } from "@/lib/job-status";
import JobProgress from "@/components/jobs/job-progress";
import JobError from "@/components/jobs/job-error";
import ResultSummary from "@/components/jobs/result-summary";
import ResultSections from "@/components/jobs/result-sections";
import ResultAnalysisModule from "@/components/jobs/result-analysis-module";
import CrossReviewPanel from "@/components/jobs/cross-review-panel";
import { Button } from "@/components/ui/button";
import { ShieldCheck } from "lucide-react";
import JudgmentAnalysis from "@/components/jobs/judgment-analysis";
import BatchLeaderboard from "@/components/jobs/batch-leaderboard";
import ArtifactActions from "@/components/jobs/artifact-actions";
import ProductMedia from "@/components/jobs/product-media";
import ResultReliabilitySummary from "@/components/jobs/result-reliability-summary";
import ProductTypeReviewCard from "@/components/jobs/product-type-review-card";
import JobAttemptTimeline from "@/components/history/job-attempt-timeline";
import { cleanLabel, scoreTone } from "@/lib/result-format";
import { resultModelLabel } from "@/lib/model-label";
import type { JobDetail, JobResultPayload, ModelResult } from "@/lib/api/types";

function formatElapsedTime(createdAt: string, nowMs: number): string {
  const elapsedSeconds = Math.max(
    0,
    Math.floor((nowMs - new Date(createdAt).getTime()) / 1000),
  );
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  return `${minutes} 分 ${seconds} 秒`;
}

function isSlowOpenAIModel(model: unknown): boolean {
  if (typeof model !== "string") return false;
  const normalized = model.trim().toLowerCase();
  return normalized === "gpt-5.5" || normalized.startsWith("gpt-5.5-");
}

export default function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();

  const {
    data: job,
    isLoading,
    isError,
    error,
  } = useQuery<JobDetail>({
    queryKey: queryKeys.jobs.detail(jobId),
    queryFn: () => getJob(jobId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return 1500;
      return getJobPollingInterval(data.status);
    },
  });

  const retryMutation = useMutation({
    mutationFn: () => retryJob(jobId),
    onSuccess: (newJob) => {
      queryClient.setQueryData(queryKeys.jobs.detail(jobId), newJob);
    },
  });

  const providersQuery = useQuery({ queryKey: ["providers", "cross-review"], queryFn: () => listProviders(), staleTime: 30000 });

  const crossReviewMutation = useMutation({
    mutationFn: async ({ reviewerA, reviewerB }: { reviewerA: { provider: string; model: string }; reviewerB: { provider: string; model: string } }) => {
      const base = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
      const res = await fetch(`${base}/api/v1/jobs/${jobId}/cross-review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer_a: reviewerA, reviewer_b: reviewerB }) });
      if (!res.ok) throw new Error("触发交叉验证失败");
      return res.json();
    },
    onSuccess: () => {
      // Start frequent polling until cross-review appears
      const interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: queryKeys.jobs.detail(jobId) });
      }, 2000);
      // Stop polling after 5 minutes
      setTimeout(() => clearInterval(interval), 300000);
    },
  });

  const [activeModel, setActiveModel] = useState("gpt");
  const [reviewerA, setReviewerA] = useState<{ provider: string; model: string } | null>(null);
  const [reviewerB, setReviewerB] = useState<{ provider: string; model: string } | null>(null);
  const [resultView, setResultView] = useState<"details" | "analysis">("details");
  const [nowMs, setNowMs] = useState(() => Date.now());
  const isJobRunning = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    if (!isJobRunning) return undefined;
    const interval = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [isJobRunning]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (isError) {
    const is404 = error instanceof Error && error.message.includes("404");
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-sm text-muted-foreground">
          {is404 ? "任务不存在" : error.message}
        </p>
      </div>
    );
  }

  if (!job) return null;

  const payload = job.result_payload;
  const models = payload?.models;
  const hasDual = !!(models && models.gpt && models.deepseek);
  const crossReview = payload?.cross_review as
    | Record<string, unknown>
    | undefined;
  const hasCrossReview = !!(crossReview && (
    (typeof crossReview.status === "string" && ["queued", "running", "completed", "failed"].includes(crossReview.status)) ||
    crossReview.gpt_reviews_deepseek ||
    crossReview.deepseek_reviews_gpt
  ));
  const eligibleReviewProviders = (providersQuery.data ?? []).filter(
    (provider) =>
      provider.is_enabled &&
      provider.configured
  );
  const catalog = providerModelOptions(eligibleReviewProviders).filter(
    (option) => isFreshVerifiedModel(option) && option.is_selected === true
  );
  const catalogIdentities = new Set(
    catalog.map((option) => `${option.provider}:${option.model}`)
  );
  const isCatalogSelection = (selection: { provider: string; model: string } | null) =>
    !!selection && catalogIdentities.has(`${selection.provider}:${selection.model}`);
  const toSelection = (option: (typeof catalog)[number]) => ({
    provider: option.provider,
    model: option.model,
  });
  let selectedA = isCatalogSelection(reviewerA) ? reviewerA : null;
  let selectedB = isCatalogSelection(reviewerB) ? reviewerB : null;
  if (!selectedA) {
    const fallbackA = catalog.find(
      (option) => !selectedB || `${option.provider}:${option.model}` !== `${selectedB.provider}:${selectedB.model}`
    );
    selectedA = fallbackA ? toSelection(fallbackA) : null;
  }
  if (!selectedB) {
    const fallbackB = catalog.find(
      (option) => !selectedA || `${option.provider}:${option.model}` !== `${selectedA.provider}:${selectedA.model}`
    );
    selectedB = fallbackB ? toSelection(fallbackB) : null;
  }

  // Batch job payload: { batch_count, results: [...] }
  const batchResults =
    payload && Array.isArray((payload as Record<string, unknown>).results)
      ? ((payload as Record<string, unknown>).results as JobResultPayload[])
      : null;
  const isBatch = !!batchResults && batchResults.length > 0;

  // Determine which model result to display
  let activeResult: ModelResult | undefined;
  if (hasDual) {
    activeResult = models![activeModel];
  } else if (payload) {
    activeResult = payload as unknown as ModelResult;
  }

  const isJudgment =
    job.mode === "judgment" || activeResult?.mode === "judgment";
  const taskProductTypeReview = payload?.product_type_review ?? activeResult?.product_type_review;
  const taskRejectedBProducts = payload?.rejected_b_products ?? activeResult?.rejected_b_products;
  const judgmentBProducts = activeResult?.b_products ?? payload?.b_products;
  const judgmentBUrls = Array.isArray(job.request_payload.b_urls)
    ? job.request_payload.b_urls.filter(
        (value): value is string => typeof value === "string",
      )
    : undefined;

  // Metadata is persisted at both job and result level so older and in-flight
  // jobs can render the same product context without changing analysis data.
  const productId = activeResult?.product_id ?? payload?.product_id ?? job.product_id ?? undefined;
  const productTitle = activeResult?.product_title ?? payload?.product_title ?? job.product_title ?? undefined;
  const productTitleZh = activeResult?.product_title_zh ?? payload?.product_title_zh ?? job.product_title_zh ?? undefined;
  const productImages = activeResult?.product_images ?? payload?.product_images ?? (job.product_image ? [job.product_image] : undefined);

  const bandScore =
    typeof activeResult?.score === "number" ? activeResult.score : null;
  const bandTone = scoreTone(bandScore ?? undefined);
  const bandGrade = cleanLabel(activeResult?.grade);
  const bandTitle = payload?.product_title || job.name || "";
  const elapsedLabel = formatElapsedTime(job.created_at, nowMs);
  const slowModel = isSlowOpenAIModel(job.request_payload.model);
  const waitingForWalmartVerification =
    job.status === "running" &&
    job.error_code === "WALMART_CAPTCHA_REQUIRED";

  return (
    <div className="mx-auto max-w-[1500px] space-y-6 p-6">
      <h1 className="text-lg font-semibold">任务详情</h1>

      <JobProgress status={job.status} progress={job.progress} />

      {job.attempts?.length ? <JobAttemptTimeline attempts={job.attempts} /> : null}

      {(job.status === "queued" || job.status === "running") && (
        <div className="flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50/60 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="space-y-1 text-sm">
            {waitingForWalmartVerification ? (
              <>
                <p className="font-medium text-amber-950">等待 Walmart 人工验证</p>
                <p className="text-amber-900">
                  软件已打开 Walmart 验证窗口。请完成验证，不要关闭窗口；验证通过后任务会自动继续。
                </p>
                <p className="text-amber-800">当前尚未调用模型，不会消耗 Token。</p>
              </>
            ) : (
              <>
                <p className="font-medium text-foreground">
                  {job.progress >= 35
                    ? `模型正在生成完整报告，已等待 ${elapsedLabel}`
                    : `任务正在后台运行，已等待 ${elapsedLabel}`}
                </p>
                {slowModel && (
                  <p className="text-amber-800">慢模型最长等待 10 分钟，超时不会自动重试。</p>
                )}
                <p className="text-muted-foreground">返回后任务继续在后台运行，可在历史记录查看。</p>
              </>
            )}
          </div>
          <Button className="shrink-0" type="button" variant="outline" onClick={() => router.push("/")}>
            返回工作台
          </Button>
        </div>
      )}

      {(productId || productTitle || productTitleZh || productImages?.length) && (
        <section className="grid gap-4 rounded-xl border p-4 sm:grid-cols-[96px_minmax(0,1fr)]">
          <ProductMedia
            src={productImages}
            alt={productTitle || productTitleZh || "主品图片"}
            emptyLabel="暂无主品图片"
            className="w-24"
          />
          <div className="min-w-0">
            <p className="text-xs font-medium text-primary">主品信息</p>
            {productId && <p className="mt-1 text-sm"><span>商品 ID：</span><span>{productId}</span></p>}
            {productTitleZh && <p className="mt-1 text-base font-semibold leading-relaxed">{productTitleZh}</p>}
            {productTitle && <p className="mt-1 text-sm text-muted-foreground"><span>原始标题：</span><span>{productTitle}</span></p>}
          </div>
        </section>
      )}

      {job.status === "failed" && (
        <div className="space-y-3">
          <JobError
            errorCode={job.error_code ?? "UNKNOWN"}
            errorMessage={job.error_message ?? "未知错误"}
            onRetry={() => retryMutation.mutate()}
            isRetrying={retryMutation.isPending}
          />
          <div className="flex justify-end">
            <Button type="button" variant="outline" onClick={() => router.push("/")}>
              返回工作台
            </Button>
          </div>
        </div>
      )}

      {job.status === "completed" && isBatch && (
        <BatchLeaderboard results={batchResults!} />
      )}

      {job.status === "completed" && !isBatch && (
        <>
          {!isJudgment && activeResult && (
            <ResultReliabilitySummary
              jobId={jobId}
              updatedAt={job.updated_at}
              result={activeResult}
            />
          )}

          {/* 粘性信息带：评分 / 评级 / 标题 / 模型切换 / 导出 */}
          <div className="sticky top-0 z-30 -mx-6 border-b bg-background/95 px-6 py-2 backdrop-blur">
            <div className="flex items-center gap-3">
              {bandScore != null && (
                <span
                  className={`flex h-8 w-12 shrink-0 items-center justify-center rounded-lg text-sm font-bold ${bandTone.bg} ${bandTone.text}`}
                >
                  {bandScore}
                </span>
              )}
              {bandGrade && (
                <span className="shrink-0 rounded-md bg-sky-50 px-2 py-1 text-xs font-medium text-sky-800">
                  {bandGrade}
                </span>
              )}
              <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                {bandTitle}
              </span>
              {hasDual && (
                <div className="flex shrink-0 gap-0.5 rounded-md border p-0.5">
                  {Object.keys(models!).map((modelKey) => (
                    <button
                      key={modelKey}
                      type="button"
                      onClick={() => setActiveModel(modelKey)}
                      className={`rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${
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
              <ArtifactActions
                jobId={jobId}
                activeModel={hasDual ? activeModel : undefined}
                compact
              />
            </div>
          </div>

          {/* Cross-review trigger */}
          {hasDual && !hasCrossReview && (
            <div className="border border-primary/25 bg-primary/[0.04] p-4 shadow-sm">
            <div className="mb-3 flex items-center gap-3"><div className="grid h-9 w-9 place-items-center rounded-md bg-primary text-primary-foreground"><ShieldCheck className="h-5 w-5" aria-hidden="true" /></div><div><h2 className="text-sm font-semibold">交叉验证</h2><p className="text-sm text-muted-foreground">比较两个模型的结论与评分差异</p></div></div>
            <div className="mb-3 grid gap-3 md:grid-cols-2">
              <label className="space-y-1 text-sm"><span className="font-medium">评审模型 A</span><select aria-label="评审模型 A" value={selectedA ? `${selectedA.provider}:${selectedA.model}` : ""} onChange={(event) => { const [provider, ...model] = event.target.value.split(":"); setReviewerA({ provider, model: model.join(":") }); }} className="h-10 w-full rounded-md border border-input bg-background px-3">{!selectedA && <option value="" disabled>无可用评审模型</option>}{catalog.map((option) => <option key={`${option.provider}:${option.model}`} value={`${option.provider}:${option.model}`}>{option.provider_display_name} · {option.model}</option>)}</select></label>
              <label className="space-y-1 text-sm"><span className="font-medium">评审模型 B</span><select aria-label="评审模型 B" value={selectedB ? `${selectedB.provider}:${selectedB.model}` : ""} onChange={(event) => { const [provider, ...model] = event.target.value.split(":"); setReviewerB({ provider, model: model.join(":") }); }} className="h-10 w-full rounded-md border border-input bg-background px-3">{!selectedB && <option value="" disabled>需要第二个可用评审模型</option>}{catalog.map((option) => <option key={`${option.provider}:${option.model}`} value={`${option.provider}:${option.model}`}>{option.provider_display_name} · {option.model}</option>)}</select></label>
            </div>
            <button
              type="button"
               onClick={() => selectedA && selectedB && crossReviewMutation.mutate({ reviewerA: selectedA, reviewerB: selectedB })}
               disabled={crossReviewMutation.isPending || !selectedA || !selectedB || (selectedA.provider === selectedB.provider && selectedA.model === selectedB.model)}
              className="flex w-full items-center justify-center rounded-md bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {crossReviewMutation.isPending
                ? "正在进行交叉验证..."
                : "开始交叉验证（交叉验证：GPT 与 DeepSeek 互评）"}
            </button>
            </div>
          )}

          <ResultSummary
            grade={activeResult?.grade}
            gradeReason={activeResult?.grade_reason}
            score={activeResult?.score}
            scoreReason={activeResult?.score_reason}
            productId={productId}
            productTitle={productTitle}
            productTitleZh={productTitleZh}
            productImages={productImages}
          />

          {taskProductTypeReview && <ProductTypeReviewCard review={taskProductTypeReview} />}

          {/* Result view tabs */}
          <div className="flex gap-1 rounded-md border p-1">
            <button
              type="button"
              onClick={() => setResultView("details")}
              className={`flex-1 rounded-sm px-3 py-2 text-sm font-medium transition-colors ${
                resultView === "details"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              结果详情
            </button>
            <button
              type="button"
              onClick={() => setResultView("analysis")}
              className={`flex-1 rounded-sm px-3 py-2 text-sm font-medium transition-colors ${
                resultView === "analysis"
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              方案分析
            </button>
          </div>

          {resultView === "details" ? (
            <ResultSections sections={activeResult?.sections} />
          ) : isJudgment ? (
            <div className="space-y-4">
              {taskRejectedBProducts?.length ? (
                <section className="space-y-3 border border-rose-200 bg-rose-50/50 p-4" aria-labelledby="judgment-food-rejections">
                  <h2 id="judgment-food-rejections" className="text-sm font-semibold text-rose-950">食品辅品不准入</h2>
                  {taskRejectedBProducts.map((item, index) => <div key={`${item.url ?? item.title ?? "food"}-${index}`} className="space-y-2">
                    <p className="break-words text-sm font-medium text-rose-950">{item.title || "未记录商品标题"}：确认为食品，不符合准入范围</p>
                    {item.review && <ProductTypeReviewCard review={item.review} />}
                  </div>)}
                </section>
              ) : null}
              <JudgmentAnalysis
                sections={activeResult?.sections}
                grade={activeResult?.grade}
                complementEvidence={activeResult?.complement_evidence}
                bProducts={judgmentBProducts}
                bUrls={judgmentBUrls}
              />
              {hasCrossReview && (
                <CrossReviewPanel crossReview={crossReview!} models={models} />
              )}
            </div>
          ) : (
            <ResultAnalysisModule
              sections={activeResult?.sections}
              structuredDirections={activeResult?.structured_directions}
              productId={activeResult?.product_id ?? payload?.product_id ?? job.product_id ?? undefined}
              productTitle={productTitle}
              productTitleZh={productTitleZh}
              productUrl={activeResult?.product_url ?? payload?.product_url}
              productImages={productImages}
              productPrice={activeResult?.product_price ?? payload?.product_price}
              productRating={activeResult?.product_rating ?? payload?.product_rating}
              productReviewCount={activeResult?.product_review_count ?? payload?.product_review_count}
              keywordPack={activeResult?.keyword_pack ?? payload?.keyword_pack}
              crossReview={crossReview as never}
              models={models}
              modelVersion={activeResult?.model_version}
              resultStatus={activeResult?.result_status}
              resultMessage={activeResult?.result_message}
              auditOutcome={activeResult?.audit_outcome}
              rejectionSummary={activeResult?.rejection_summary}
              rejectedBProducts={taskRejectedBProducts}
            />
          )}
        </>
      )}
    </div>
  );
}
