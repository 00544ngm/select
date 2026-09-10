"use client";

import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { useMutation } from "@tanstack/react-query";
import { submitBatch } from "@/lib/api/jobs";
import type { ProviderSlug, RotationCandidate } from "@/lib/api/types";
import { isKnownPlatform, isLookalikeHost } from "@/lib/schemas/job-forms";
import ModelSelect from "./model-select";
import { ProviderSetupNotice, usePrimaryProviders } from "./provider-availability";

interface ParseResult { valid: string[]; invalid: string[]; }
interface BatchModelFields { provider: ProviderSlug | ""; model: string; }

function parseUrls(raw: string): ParseResult {
  const lines = raw.split("\n").map((line) => line.trim()).filter(Boolean);
  const seen = new Set<string>();
  const valid: string[] = [];
  const invalid: string[] = [];
  for (const url of lines) {
    if (seen.has(url)) continue;
    seen.add(url);
    try {
      const parsed = new URL(url);
      if (parsed.protocol !== "https:" || !isKnownPlatform(url) || isLookalikeHost(url)) throw new Error();
      valid.push(url);
    } catch {
      invalid.push(url);
    }
  }
  return { valid, invalid };
}

export default function BatchForm() {
  const [raw, setRaw] = useState("");
  const [name, setName] = useState("");
  const [rotation, setRotation] = useState<{ enabled: boolean; candidates: RotationCandidate[] }>({ enabled: false, candidates: [] });
  const providerQuery = usePrimaryProviders();
  const { register, getValues } = useForm<BatchModelFields>({
    defaultValues: { provider: "", model: "" },
  });
  const parsed = useMemo(() => parseUrls(raw), [raw]);

  const mutation = useMutation({
    mutationFn: () => {
      const selection = getValues();
      return submitBatch({
        name: name || undefined,
        urls: parsed.valid,
        model: selection.model || undefined,
        provider: selection.provider || undefined,
        rotation_enabled: rotation.enabled,
        ...(rotation.enabled ? { rotation_candidates: rotation.candidates } : {}),
      });
    },
  });

  const hasContent = raw.trim().length > 0;
  const hasNoProviders = providerQuery.isSuccess && providerQuery.providers.length === 0;
  const isUnavailable = providerQuery.isLoading || hasNoProviders;
  const rotationUnavailable = rotation.enabled && rotation.candidates.length === 0;

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (parsed.valid.length > 0) mutation.mutate();
      }}
      className="space-y-4"
    >
      <div className="space-y-1.5">
        <label htmlFor="batch-name" className="text-sm text-muted-foreground">任务名称（可选）</label>
        <input
          id="batch-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="给本次分析起个名字"
          className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground"
        />
      </div>
      <label htmlFor="batch-urls" className="text-sm text-muted-foreground">商品链接（每行一个）</label>
      <textarea
        id="batch-urls"
        value={raw}
        onChange={(event) => setRaw(event.target.value)}
        placeholder="每行一个商品链接"
        rows={8}
        className="h-40 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-ring"
      />

      {hasContent && (
        <div className="flex items-center gap-4 text-sm">
          {parsed.valid.length > 0 && <span className="text-muted-foreground">{parsed.valid.length} 个有效</span>}
          {parsed.invalid.length > 0 && <span className="text-destructive">{parsed.invalid.length} 个无效</span>}
        </div>
      )}

      {hasNoProviders ? <ProviderSetupNotice /> : providerQuery.isLoading ? (
        <p className="text-sm text-muted-foreground">正在读取 API 配置...</p>
      ) : (
        <ModelSelect
          preferenceEntry="batch"
          providers={providerQuery.providers}
          providerRegistration={register("provider")}
          modelRegistration={register("model")}
          onRotationChange={(enabled, candidates) => setRotation({ enabled, candidates })}
        />
      )}

      <button
        type="submit"
        disabled={parsed.valid.length === 0 || mutation.isPending || isUnavailable || rotationUnavailable}
        className="h-10 rounded-md bg-foreground px-6 text-sm font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {mutation.isPending ? "提交中..." : "提交"}
      </button>
      {mutation.isSuccess && <p className="text-sm text-green-600">提交成功</p>}
      {mutation.isError && <p className="text-sm text-destructive">提交失败，请重试</p>}
    </form>
  );
}
