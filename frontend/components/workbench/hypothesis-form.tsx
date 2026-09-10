"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { submitHypothesis } from "@/lib/api/jobs";
import { hypothesisSchema, type HypothesisFormData } from "@/lib/schemas/job-forms";
import ModelSelect from "./model-select";
import { ProviderSetupNotice, usePrimaryProviders } from "./provider-availability";
import type { RotationCandidate } from "@/lib/api/types";

interface HypothesisFormProps {
  isSubmitting?: boolean;
}

export default function HypothesisForm({ isSubmitting }: HypothesisFormProps) {
  const [showModelSettings, setShowModelSettings] = useState(false);
  const [rotation, setRotation] = useState<{ enabled: boolean; candidates: RotationCandidate[] }>({ enabled: false, candidates: [] });
  const providerQuery = usePrimaryProviders();
  const { register, handleSubmit, formState: { errors } } = useForm<HypothesisFormData>({
    resolver: zodResolver(hypothesisSchema),
  });

  const mutation = useMutation({
    mutationFn: (data: HypothesisFormData) => submitHypothesis({
      name: data.name || undefined,
      url: data.url,
      model: data.model || undefined,
      provider: data.provider || undefined,
      rotation_enabled: rotation.enabled,
      ...(rotation.enabled ? { rotation_candidates: rotation.candidates } : {}),
    }),
    onSuccess: (job) => {
      window.location.href = `/jobs/${job.id}`;
    },
  });

  const hasNoProviders = providerQuery.isSuccess && providerQuery.providers.length === 0;
  const rotationUnavailable = rotation.enabled && rotation.candidates.length === 0;
  const pending = isSubmitting || mutation.isPending || providerQuery.isLoading || hasNoProviders || rotationUnavailable;

  return (
    <form onSubmit={handleSubmit((data) => mutation.mutate(data))} className="space-y-4">
      <div className="space-y-1.5">
        <label htmlFor="hypothesis-name" className="text-sm text-muted-foreground">任务名称（可选）</label>
        <input
          id="hypothesis-name"
          {...register("name")}
          placeholder="给本次分析起个名字"
          className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground"
        />
        {errors.name?.message && <p className="text-xs text-destructive">{errors.name.message}</p>}
      </div>

      <div>
        <div className="flex gap-2">
          <input
            type="url"
            placeholder="https://www.walmart.com/ip/... 或亚马逊商品链接"
            aria-label="主品商品链接"
            aria-invalid={!!errors.url}
            className={`h-12 min-w-0 flex-1 rounded-lg border bg-background px-4 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring ${errors.url ? "border-destructive" : "border-input"}`}
            {...register("url")}
          />
          <button
            type="submit"
            disabled={pending}
            className="inline-flex h-12 shrink-0 items-center gap-1.5 rounded-lg bg-foreground px-6 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {hasNoProviders ? (
              <>请先配置 API</>
            ) : pending ? (
              <><Loader2 className="h-4 w-4 animate-spin" />提交中</>
            ) : (
              <>分析<ArrowRight className="h-4 w-4" /></>
            )}
          </button>
        </div>
        {errors.url?.message && <p className="mt-1.5 text-xs text-destructive" role="alert">{errors.url.message}</p>}
      </div>

      {hasNoProviders && <ProviderSetupNotice />}

      <div>
        <button
          type="button"
          onClick={() => setShowModelSettings((current) => !current)}
          className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          {showModelSettings ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
          模型设置
        </button>
        {showModelSettings && (
          <div className="mt-3 rounded-lg border p-4">
            {providerQuery.isLoading ? (
              <p className="text-sm text-muted-foreground">正在读取 API 配置...</p>
            ) : (
              <ModelSelect
                preferenceEntry="hypothesis"
                providers={providerQuery.providers}
                modelRegistration={register("model")}
                providerRegistration={register("provider")}
                onRotationChange={(enabled, candidates) => setRotation({ enabled, candidates })}
              />
            )}
          </div>
        )}
      </div>

      {mutation.isError && (
        <p className="text-xs text-destructive" role="alert">
          {mutation.error instanceof Error ? mutation.error.message : "提交失败，请重试"}
        </p>
      )}
    </form>
  );
}
