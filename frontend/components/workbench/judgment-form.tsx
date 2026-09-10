"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { judgmentSchema, type JudgmentFormData } from "@/lib/schemas/job-forms";
import { submitJudgment } from "@/lib/api/jobs";
import { ApiError } from "@/lib/api/client";
import { queryKeys } from "@/lib/query-keys";
import UrlField from "./url-field";
import ModelSelect from "./model-select";
import { ProviderSetupNotice, usePrimaryProviders } from "./provider-availability";
import type { RotationCandidate } from "@/lib/api/types";

interface JudgmentFormProps {
  isSubmitting?: boolean;
  defaultBUrls?: string[];
}

export default function JudgmentForm({ isSubmitting, defaultBUrls }: JudgmentFormProps) {
  const [bUrlCount, setBUrlCount] = useState(defaultBUrls?.length || 1);
  const [rotation, setRotation] = useState<{ enabled: boolean; candidates: RotationCandidate[] }>({ enabled: false, candidates: [] });
  const queryClient = useQueryClient();
  const providerQuery = usePrimaryProviders();
  const rotationUnavailable = rotation.enabled && rotation.candidates.length === 0;

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<JudgmentFormData>({
    resolver: zodResolver(judgmentSchema),
    defaultValues: {
      aUrl: "",
      bUrls: defaultBUrls && defaultBUrls.length > 0 ? defaultBUrls : [""],
    },
  });

  // 当从搜索页选中B商品时，更新表单值
  useEffect(() => {
    if (defaultBUrls && defaultBUrls.length > 0) {
      reset({ aUrl: "", bUrls: defaultBUrls });
      setBUrlCount(defaultBUrls.length);
    }
  }, [defaultBUrls, reset]);

  const mutation = useMutation({
    mutationFn: (data: JudgmentFormData) =>
      submitJudgment({
        name: data.name || undefined,
        a_url: data.aUrl,
        b_urls: data.bUrls,
        model: data.model || undefined,
        provider: data.provider || undefined,
        rotation_enabled: rotation.enabled,
        ...(rotation.enabled ? { rotation_candidates: rotation.candidates } : {}),
      }),
    onSuccess: (job) => {
      window.location.href = `/jobs/${job.id}`;
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        [
          "PROVIDER_MODEL_INVALID",
          "PROVIDER_MODEL_ROUTE_UNAVAILABLE",
          "PROVIDER_MODEL_NOT_VERIFIED",
          "PROVIDER_UNAVAILABLE",
        ].includes(error.code)
      ) {
        void queryClient.invalidateQueries({ queryKey: queryKeys.providers.all });
      }
    },
  });

  const onSubmit = (data: JudgmentFormData) => {
    mutation.mutate(data);
  };

  const addBUrl = () => {
    setBUrlCount((c) => c + 1);
  };

  const removeBUrl = (index: number) => {
    setBUrlCount((c) => Math.max(1, c - 1));
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="space-y-1.5">
        <label className="text-sm text-muted-foreground">任务名称（可选）</label>
        <input
          {...register("name")}
          placeholder="给本次分析起个名字"
          className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground"
        />
        {errors.name?.message && (
          <p className="text-xs text-destructive">{errors.name.message}</p>
        )}
      </div>
      <UrlField
        placeholder="请输入 A 商品链接"
        registration={register("aUrl")}
        error={errors.aUrl?.message}
      />

      <div className="space-y-2">
        <label className="text-sm text-muted-foreground">B 商品链接</label>
        {Array.from({ length: bUrlCount }, (_, i) => (
          <UrlField
            key={i}
            placeholder={`B 商品链接 ${i + 1}`}
            registration={register(`bUrls.${i}` as const)}
            error={errors.bUrls?.[i]?.message}
            onRemove={bUrlCount > 1 ? () => removeBUrl(i) : undefined}
          />
        ))}
        <button
          type="button"
          onClick={addBUrl}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          + 添加
        </button>
      </div>

      {providerQuery.isSuccess && providerQuery.providers.length === 0 ? (
        <ProviderSetupNotice />
      ) : providerQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">正在读取 API 配置...</p>
      ) : (
        <ModelSelect
          preferenceEntry="judgment"
          providers={providerQuery.providers}
          modelRegistration={register("model")}
          providerRegistration={register("provider")}
          onRotationChange={(enabled, candidates) => setRotation({ enabled, candidates })}
        />
      )}

      {mutation.isError && (
        <p className="text-xs text-destructive" role="alert">
          {mutation.error instanceof Error ? mutation.error.message : "提交失败，请重试"}
        </p>
      )}

      <button
        type="submit"
        disabled={isSubmitting || mutation.isPending || providerQuery.isLoading || (providerQuery.isSuccess && providerQuery.providers.length === 0) || rotationUnavailable}
        className="h-10 rounded-md bg-foreground px-6 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {mutation.isPending ? "提交中..." : "提交"}
      </button>
    </form>
  );
}
