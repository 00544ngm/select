"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock3, Loader2, Search, Save, TestTube2, XCircle } from "lucide-react";
import { listProviders, selectProviderModel, testProvider, updateProvider, verifyProviderModel } from "@/lib/api/providers";
import { ApiError } from "@/lib/api/client";
import type {
  ProviderConfiguration,
  ProviderDraftPayload,
  ProviderSlug,
} from "@/lib/api/types";
import { queryKeys } from "@/lib/query-keys";
import {
  providerSettingsSchema,
  type ProviderSettingsFormData,
} from "@/lib/schemas/provider-settings";
import SecretInput from "./secret-input";
import { formatModelIdentity, providerModelOptions } from "@/lib/model-identity";
import { isFreshVerifiedModel, providerModelStatusLabel } from "@/lib/provider-model-status";
import {
  filterAndSortModelCatalog,
  type ModelCatalogFilter,
  type ModelCatalogSort,
} from "@/lib/model-catalog";

const MODEL_CATALOG_PAGE_SIZE = 10;

function capabilityLabel(
  transportMode?: string | null,
  structuredOutputMode?: string | null
): string | null {
  if (!transportMode || !structuredOutputMode) return null;
  const transport = transportMode === "responses" ? "Responses" : "Chat Completions";
  const structured = {
    json_schema: "JSON Schema",
    json_object: "JSON Object",
    prompt_json: "提示词 JSON",
  }[structuredOutputMode];
  return structured ? `${transport} · ${structured}` : null;
}

function valuesFor(provider: ProviderConfiguration): ProviderSettingsFormData {
  return {
    apiProtocol: provider.api_protocol ?? "openai",
    displayName: provider.display_name,
    baseUrl: provider.base_url ?? "",
    defaultModel: provider.default_model,
    apiKey: undefined,
    isEnabled: provider.is_enabled,
  };
}

function draftPayload(values: ProviderSettingsFormData): ProviderDraftPayload {
  return {
    api_protocol: values.apiProtocol,
    display_name: values.displayName || undefined,
    base_url: values.baseUrl,
    default_model: values.defaultModel,
    api_key: values.apiKey || undefined,
  };
}

function connectionSignature(values: ProviderSettingsFormData): string {
  return JSON.stringify([
    values.apiProtocol,
    values.baseUrl.trim(),
    values.defaultModel.trim(),
  ]);
}

export default function ProviderSettingsPanel({
  scope,
}: {
  /** When present, this panel edits ONE ApiGroup's own provider set instead of
   * the global default set. Rendered only on the admin page. */
  scope?: { kind: "group"; groupId: string; groupName: string };
}) {
  const queryClient = useQueryClient();
  const groupId = scope?.kind === "group" ? scope.groupId : undefined;
  const groupName = scope?.kind === "group" ? scope.groupName : undefined;
  // Every list/read/write is namespaced by scope so a group editor never shows
  // or overwrites another group's (or the global) provider cache.
  const readKey = groupId ? ["providers", "group", groupId] : ["providers", "global"];
  const [activeSlug, setActiveSlug] = useState<ProviderSlug>("openai");
  const activeSlugRef = useRef<ProviderSlug>(activeSlug);
  const [successMessage, setSuccessMessage] = useState("");
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [testedSignature, setTestedSignature] = useState<string | null>(null);
  const [modelCatalogPage, setModelCatalogPage] = useState(1);
  const [modelQuery, setModelQuery] = useState("");
  const [modelFilter, setModelFilter] = useState<ModelCatalogFilter>("all");
  const [modelSort, setModelSort] = useState<ModelCatalogSort>("smart");
  const [autoVerifyingModels, setAutoVerifyingModels] = useState<Set<string>>(new Set());
  const providerQuery = useQuery({
    queryKey: readKey,
    queryFn: () => listProviders(groupId),
  });
  const providers = providerQuery.data ?? [];
  const active = useMemo(
    () => providers.find((provider) => provider.slug === activeSlug) ?? providers[0],
    [activeSlug, providers]
  );

  const {
    register,
    reset,
    setValue,
    watch,
    handleSubmit,
    formState: { errors },
  } = useForm<ProviderSettingsFormData>({
    resolver: zodResolver(providerSettingsSchema),
    defaultValues: {
      apiProtocol: "openai",
      displayName: "",
      baseUrl: "",
      defaultModel: "",
      apiKey: undefined,
      isEnabled: false,
    },
  });

  useEffect(() => {
    if (active) {
      const values = valuesFor(active);
      reset(values);
      setAvailableModels(
        active.last_test_status === "success" ? active.supported_models ?? [] : []
      );
      setModelCatalogPage(1);
      setModelQuery("");
      setModelFilter("all");
      setModelSort("smart");
      setSuccessMessage("");
      setTestedSignature(
        active.last_test_status === "success" ? connectionSignature(values) : null
      );
      testMutation.reset();
      saveMutation.reset();
    }
  // Mutations are intentionally reset when the selected provider changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, reset]);

  const invalidateConnectionTest = () => {
    setTestedSignature(null);
    setSuccessMessage("");
    setAvailableModels([]);
    setModelCatalogPage(1);
    testMutation.reset();
    saveMutation.reset();
  };

  const testMutation = useMutation({
    mutationFn: ({ slug, values }: { slug: ProviderSlug; values: ProviderSettingsFormData }) =>
      testProvider(slug, draftPayload(values), groupId),
    onSuccess: (result, { slug, values }) => {
      if (activeSlugRef.current !== slug) {
        return;
      }
      setAvailableModels(result.models);
      setModelCatalogPage(1);
      const currentModel = values.defaultModel;
      let verifiedModel = currentModel;
      if (result.models.length > 0 && !result.models.includes(currentModel)) {
        verifiedModel = result.models[0];
        setValue("defaultModel", verifiedModel, { shouldDirty: true });
      }
      setTestedSignature(connectionSignature({ ...values, defaultModel: verifiedModel }));
      setSuccessMessage(
        result.message.startsWith("Connection successful")
          ? "连接成功"
          : result.message
      );
    },
    onError: (_error, { slug }) => {
      if (activeSlugRef.current !== slug) {
        return;
      }
      setAvailableModels([]);
      setModelCatalogPage(1);
      setTestedSignature(null);
      setSuccessMessage("");
    },
  });

  const saveMutation = useMutation({
    mutationFn: ({ slug, values }: { slug: ProviderSlug; values: ProviderSettingsFormData }) =>
      updateProvider(slug, {
        ...draftPayload(values),
        is_enabled: values.isEnabled,
      }, groupId),
    onSuccess: async (updatedProvider, { slug }) => {
      queryClient.setQueryData<ProviderConfiguration[]>(
        readKey,
        (currentProviders) =>
          currentProviders?.map((provider) =>
            provider.slug === updatedProvider.slug ? updatedProvider : provider
          )
      );
      if (activeSlugRef.current === slug) {
        testMutation.reset();
        verifyMutation.reset();
        selectionMutation.reset();
      }

      const defaultOption = updatedProvider.model_options?.find(
        (option) => option.model === updatedProvider.default_model
      );
      const needsAutomaticVerification =
        updatedProvider.is_enabled &&
        updatedProvider.configured &&
        (!defaultOption ||
          defaultOption.test_status !== "verified" ||
          defaultOption.is_current_connection === false);
      if (!needsAutomaticVerification) {
        if (activeSlugRef.current === slug) {
          setSuccessMessage("配置已保存，无需重复验证");
        }
        return;
      }

      setAutoVerifyingModels((current) => new Set(current).add(updatedProvider.default_model));
      if (activeSlugRef.current === slug) {
        setSuccessMessage("配置已保存，正在自动验证连接...");
      }
      try {
        const result = await verifyProviderModel(
          slug,
          updatedProvider.default_model,
          false,
          true,
          groupId
        );
        if (activeSlugRef.current === slug) {
          setSuccessMessage(
            result.test_status === "verified"
              ? "配置已保存，连接自动验证成功"
              : `配置已保存，自动验证失败：${result.test_message}`
          );
        }
        await queryClient.invalidateQueries({ queryKey: readKey });
      } catch {
        if (activeSlugRef.current === slug) {
          setSuccessMessage("");
        }
      } finally {
        setAutoVerifyingModels((current) => {
          const next = new Set(current);
          next.delete(updatedProvider.default_model);
          return next;
        });
      }
    },
    onError: (_error, { slug }) => {
      if (activeSlugRef.current === slug) {
        setSuccessMessage("");
      }
    },
  });

  const verifyMutation = useMutation({
    mutationFn: ({ slug, model }: { slug: ProviderSlug; model: string }) =>
      verifyProviderModel(slug, model, false, false, groupId),
    onSuccess: (result, { slug }) => {
      queryClient.setQueryData<ProviderConfiguration[]>(
        readKey,
        (currentProviders) => currentProviders?.map((provider) => {
          if (provider.slug !== slug) return provider;
          const currentOptions = provider.model_options ?? [];
          return {
            ...provider,
            model_options: [
              ...currentOptions.filter((option) => option.model !== result.model),
              {
                provider: slug,
                provider_display_name: provider.display_name,
                api_protocol: provider.api_protocol,
                model: result.model,
                is_default: result.is_default,
                is_selected: currentOptions.find((option) => option.model === result.model)?.is_selected ?? false,
                is_enabled: provider.is_enabled,
                test_status: result.test_status,
                tested_at: result.tested_at,
                test_message: result.test_message,
                error_code: result.error_code,
                transport_mode: result.transport_mode,
                structured_output_mode: result.structured_output_mode,
              },
            ],
          };
        })
      );
      setSuccessMessage(
        result.test_status === "verified"
          ? `模型 ${result.model} 已通过真实任务路径验证`
          : result.test_message
      );
      if (result.test_status === "verified") {
        setModelCatalogPage(1);
      }
    },
    onError: () => setSuccessMessage(""),
  });

  const selectionMutation = useMutation({
    mutationFn: ({ slug, model, isSelected }: { slug: ProviderSlug; model: string; isSelected: boolean }) =>
      selectProviderModel(slug, model, isSelected, groupId),
    onSuccess: (result) => {
      queryClient.setQueryData<ProviderConfiguration[]>(
        readKey,
        (currentProviders) => currentProviders?.map((provider) =>
          provider.slug !== result.provider
            ? provider
            : {
                ...provider,
                model_options: provider.model_options?.map((option) =>
                  option.model === result.model
                    ? { ...option, is_selected: result.is_selected }
                    : option
                ),
              }
        )
      );
      verifyMutation.reset();
      saveMutation.reset();
      setSuccessMessage("模型选择已自动保存");
    },
    onError: () => setSuccessMessage(""),
  });

  if (providerQuery.isLoading) {
    return <p className="py-12 text-center text-sm text-muted-foreground">正在读取 API 配置...</p>;
  }
  if (providerQuery.isError || !active) {
    const code =
      providerQuery.error instanceof ApiError ? providerQuery.error.code : null;
    const permissionDenied =
      code === "ADMIN_ONLY" || code === "ACCOUNT_DISABLED" || code === "AUTH_REQUIRED";
    const localOnly = code === "SETTINGS_LOCAL_ONLY";
    return (
      <p role="alert" className="text-sm text-destructive">
        {permissionDenied
          ? "API 设置仅管理员可访问，当前账号无权查看。"
          : localOnly
            ? "API 设置仅可在本机（localhost）访问。"
            : "无法读取 API 配置，请检查后端服务。"}
      </p>
    );
  }

  const mutationError =
    (testMutation.variables?.slug === active.slug ? testMutation.error : null) ??
    (verifyMutation.variables?.slug === active.slug ? verifyMutation.error : null) ??
    (selectionMutation.variables?.slug === active.slug ? selectionMutation.error : null) ??
    (saveMutation.variables?.slug === active.slug ? saveMutation.error : null);
  const operationSuccessMessage =
    successMessage ||
    (selectionMutation.isSuccess && selectionMutation.variables?.slug === active.slug
      ? "模型选择已自动保存"
      : "");
  const configuredCount = providers.filter((provider) => provider.configured && provider.is_enabled).length;
  const currentValues = watch();
  const requiresRetest =
    currentValues.isEnabled &&
    availableModels.length === 0 &&
    testedSignature !== connectionSignature(currentValues);
  const savedModelOptions = providerModelOptions([active]);
  const discoveredModelOptions = availableModels
    .filter((model) => !savedModelOptions.some((option) => option.model === model))
    .map((model) => ({
      provider: active.slug,
      provider_display_name: active.display_name,
      api_protocol: currentValues.apiProtocol,
      model,
      is_default: false,
      is_selected: false,
      is_enabled: active.is_enabled,
      test_status: "discovered" as const,
      tested_at: null,
      test_message: null,
      error_code: null,
    }));
  const catalogModelOptions = requiresRetest
    ? []
    : [...savedModelOptions, ...discoveredModelOptions];
  const filteredModelOptions = filterAndSortModelCatalog(catalogModelOptions, {
    query: modelQuery,
    filter: modelFilter,
    sort: modelSort,
  });
  const modelOptions = modelFilter === "recent"
    ? filteredModelOptions.slice(0, 10)
    : filteredModelOptions;
  const modelCatalogPageCount = Math.max(1, Math.ceil(modelOptions.length / MODEL_CATALOG_PAGE_SIZE));
  const currentModelCatalogPage = Math.min(modelCatalogPage, modelCatalogPageCount);
  const visibleModelOptions = modelOptions.slice(
    (currentModelCatalogPage - 1) * MODEL_CATALOG_PAGE_SIZE,
    currentModelCatalogPage * MODEL_CATALOG_PAGE_SIZE
  );
  const savedProtocolLabel =
    active.api_protocol === "anthropic" ? "Anthropic 兼容" : "OpenAI 兼容";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">
            {groupName ? `组 API 设置 · ${groupName}` : "API 设置"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {groupName
              ? "此分组专属的 API 配置：分配给该分组的员工任务会使用这里填写的服务地址与 Key，员工本人无法修改。"
              : "配置一次，后续任务立即使用最新有效设置。"}
          </p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full bg-success/10 px-3 py-1.5 text-xs font-medium text-success">
          <CheckCircle2 className="h-3.5 w-3.5" />
          {configuredCount} 个服务已启用
        </span>
      </div>

      <div className="overflow-x-auto border-b border-border" role="tablist" aria-label="API 供应商">
        <div className="flex min-w-max gap-1">
          {providers.map((provider) => (
            <button
              key={provider.slug}
              type="button"
              role="tab"
              aria-selected={provider.slug === active.slug}
              onClick={() => {
                activeSlugRef.current = provider.slug;
                setActiveSlug(provider.slug);
                setSuccessMessage("");
                setAvailableModels(
                  provider.last_test_status === "success"
                    ? provider.supported_models ?? []
                    : []
                );
                testMutation.reset();
                saveMutation.reset();
              }}
              className={`border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
                provider.slug === active.slug
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              {provider.display_name}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit((values) => saveMutation.mutate({ slug: active.slug, values }))} className="space-y-5 rounded-lg border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-4">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold">{active.display_name}</h2>
              {active.role === "secondary" && (
                <span className="rounded bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">二次验证</span>
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {active.last_test_message ?? "尚未测试连接"}
            </p>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
            <input type="checkbox" className="h-4 w-4 accent-primary" {...register("isEnabled")} />
            启用
          </label>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          {active.slug === "custom" && (
            <label className="space-y-1.5">
              <span className="text-sm text-muted-foreground">服务名称</span>
              <input {...register("displayName")} className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring" />
            </label>
          )}
          {active.slug === "custom" && (
            <fieldset className="space-y-1.5">
              <legend className="text-sm text-muted-foreground">接口协议</legend>
              <div className="grid h-10 grid-cols-2 rounded-md border border-input bg-muted/40 p-1">
                {[
                  { value: "openai", label: "OpenAI 兼容" },
                  { value: "anthropic", label: "Anthropic 兼容" },
                ].map((option) => (
                  <label key={option.value} className="relative cursor-pointer">
                    <input
                      type="radio"
                      value={option.value}
                      {...register("apiProtocol", { onChange: invalidateConnectionTest })}
                      className="peer sr-only"
                    />
                    <span className="flex h-full items-center justify-center rounded-sm px-3 text-sm font-medium text-muted-foreground transition-colors peer-checked:bg-background peer-checked:text-primary peer-checked:shadow-sm peer-checked:ring-2 peer-checked:ring-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring">
                      {option.label}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}
          {active.slug !== "custom" && (
            <div className="space-y-1.5">
              <span className="text-sm text-muted-foreground">接口协议</span>
              <p className="flex h-10 items-center rounded-md border border-input bg-muted/40 px-3 text-sm font-medium text-foreground">
                固定协议：{savedProtocolLabel}
              </p>
            </div>
          )}
          {active.slug === "custom" &&
            currentValues.apiProtocol !== active.api_protocol && (
              <div
                role="alert"
                className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-foreground md:col-span-2"
              >
                <p className="font-medium">你已切换接口协议，测试将使用当前选中的协议。</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Claude 模型名称不代表接口使用 Anthropic 协议。已保存协议：
                  {savedProtocolLabel}。只有服务商明确支持 Anthropic Messages API
                  （/v1/messages）时才选择 Anthropic 兼容。
                </p>
              </div>
            )}
          <label className="space-y-1.5">
            <span className="text-sm text-muted-foreground">服务地址</span>
            <input
              {...register("baseUrl", { onChange: invalidateConnectionTest })}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
            {active.slug === "custom" && currentValues.apiProtocol === "anthropic" && (
              <span className="block text-xs leading-5 text-muted-foreground">
                服务必须支持 POST /v1/messages。可填写基础地址、/v1 或完整的 /v1/messages 地址，保存时会自动规范化。自动验证会发送一次极短请求，并消耗少量 Token。
              </span>
            )}
            {active.slug === "custom" && currentValues.apiProtocol === "openai" && (
              <span className="block text-xs leading-5 text-muted-foreground">
                服务需支持 POST /v1/chat/completions 或 POST /v1/responses。可填写基础地址、/v1 或完整接口地址，保存时会自动规范化。连接检测和模型验证会消耗少量 Token；配置不变时不会定时重复验证。
              </span>
            )}
            {errors.baseUrl && <span className="text-xs text-destructive">{errors.baseUrl.message}</span>}
          </label>
          <input type="hidden" {...register("defaultModel")} />
        </div>

        <section className="space-y-3 rounded-md border border-border bg-muted/20 p-4" aria-label="模型目录">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">模型目录</h3>
              <p className="mt-1 text-xs text-muted-foreground">验证成功后持续有效；仅在连接配置变化或任务调用失败时自动复核。</p>
            </div>
            <span className="text-xs text-muted-foreground">共 {modelOptions.length} 个模型</span>
          </div>
          <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto]">
            <label className="relative block">
              <span className="sr-only">搜索模型</span>
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="search"
                aria-label="搜索模型"
                value={modelQuery}
                onChange={(event) => {
                  setModelQuery(event.target.value);
                  setModelCatalogPage(1);
                }}
                placeholder="搜索模型名称，例如 gpt-5.6"
                className="h-9 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none focus:ring-2 focus:ring-ring"
              />
            </label>
            <select
              aria-label="模型排序"
              value={modelSort}
              onChange={(event) => {
                setModelSort(event.target.value as ModelCatalogSort);
                setModelCatalogPage(1);
              }}
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="smart">智能排序</option>
              <option value="recent">最近使用排序</option>
              <option value="usage">使用次数排序</option>
              <option value="verified">历史验证排序</option>
              <option value="name">模型名称排序</option>
            </select>
          </div>
          <div className="flex flex-wrap gap-2" aria-label="模型筛选">
            {([
              ["all", "全部模型"],
              ["recent", "最近使用模型"],
              ["verified", "已验证模型"],
            ] as const).map(([value, label]) => (
              <button
                key={value}
                type="button"
                aria-pressed={modelFilter === value}
                onClick={() => {
                  setModelFilter(value);
                  setModelSort(value === "recent" ? "recent" : "smart");
                  setModelCatalogPage(1);
                }}
                className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium ${modelFilter === value ? "border-primary bg-primary text-primary-foreground" : "border-input bg-background hover:bg-muted"}`}
              >
                {value === "recent" && <Clock3 className="h-3.5 w-3.5" />}
                {label}
              </button>
            ))}
          </div>
          {modelOptions.length === 0 ? (
            <p className="text-sm text-muted-foreground">尚未发现可用模型，请先测试连接。</p>
          ) : (
            <div className="grid gap-2 md:grid-cols-2">
              {visibleModelOptions.map((option) => {
                const usable = isFreshVerifiedModel(option);
                const capability = capabilityLabel(
                  option.transport_mode,
                  option.structured_output_mode
                );
                return (
                  <div key={`${option.provider}:${option.model}`} className="rounded-md border border-border bg-background p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="min-w-0 break-words text-sm font-medium">{formatModelIdentity(option)}</p>
                      <div className="flex shrink-0 gap-1 text-[11px]">
                        <span className={`rounded px-2 py-0.5 ${usable ? "bg-success/10 text-success" : "bg-muted text-muted-foreground"}`}>
                          {providerModelStatusLabel(option)}
                        </span>
                      </div>
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">{option.test_message ?? "尚未测试连接"}</p>
                    {capability && (
                      <p className="mt-1 text-xs font-medium text-foreground">{capability}</p>
                    )}
                    {option.tested_at && <p className="mt-1 text-xs text-muted-foreground">最近测试：{new Date(option.tested_at).toLocaleString("zh-CN")}</p>}
                    {option.last_used_at && <p className="mt-1 text-xs text-muted-foreground">最近使用：{new Date(option.last_used_at).toLocaleString("zh-CN")} · 共 {option.use_count ?? 0} 次</p>}
                    <button
                      type="button"
                      disabled={verifyMutation.isPending || saveMutation.isPending || autoVerifyingModels.has(option.model)}
                      onClick={() => verifyMutation.mutate({ slug: active.slug, model: option.model })}
                      className="mt-3 h-8 rounded-md border border-input px-3 text-xs font-medium hover:bg-muted disabled:opacity-50"
                    >
                      {autoVerifyingModels.has(option.model)
                        ? "自动验证中…"
                        : verifyMutation.isPending && verifyMutation.variables?.model === option.model
                          ? "正在验证…"
                          : usable
                            ? "重新验证"
                            : "验证此模型"}
                    </button>
                    <label className={`mt-3 flex items-center gap-2 text-xs font-medium ${usable ? "cursor-pointer" : "cursor-not-allowed text-muted-foreground"}`}>
                      <input
                        type="checkbox"
                        aria-label={`使用 ${option.model}`}
                        checked={option.is_selected === true}
                        disabled={!usable || selectionMutation.isPending}
                        onChange={(event) => selectionMutation.mutate({
                          slug: active.slug,
                          model: option.model,
                          isSelected: event.target.checked,
                        })}
                        className="h-4 w-4 accent-primary"
                      />
                      使用此模型
                    </label>
                  </div>
                );
              })}
            </div>
          )}
          {modelOptions.length > MODEL_CATALOG_PAGE_SIZE && (
            <nav className="flex items-center justify-center gap-3 border-t border-border pt-3" aria-label="模型目录分页">
              <button
                type="button"
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={currentModelCatalogPage === 1}
                onClick={() => setModelCatalogPage((page) => Math.max(1, page - 1))}
              >
                上一页
              </button>
              <span className="min-w-24 text-center text-sm text-muted-foreground">
                第 {currentModelCatalogPage} / {modelCatalogPageCount} 页
              </span>
              <button
                type="button"
                className="rounded-md border border-input bg-background px-3 py-1.5 text-sm disabled:cursor-not-allowed disabled:opacity-50"
                disabled={currentModelCatalogPage === modelCatalogPageCount}
                onClick={() => setModelCatalogPage((page) => Math.min(modelCatalogPageCount, page + 1))}
              >
                下一页
              </button>
            </nav>
          )}
        </section>

        <div className="space-y-1.5">
          <span className="text-sm text-muted-foreground">API Key</span>
          <SecretInput
            key={active.slug}
            maskedValue={active.masked_api_key}
            value={watch("apiKey")}
            onChange={(value) => {
              invalidateConnectionTest();
              setValue("apiKey", value, { shouldDirty: true });
            }}
          />
        </div>

        {mutationError && (
          <p role="alert" className="flex items-center gap-2 text-sm text-destructive">
            <XCircle className="h-4 w-4 shrink-0" />
            {mutationError instanceof Error ? mutationError.message : "操作失败"}
          </p>
        )}
        {operationSuccessMessage && !mutationError && (
          <p role="status" className="flex items-center gap-2 text-sm text-success">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            {operationSuccessMessage}
          </p>
        )}

        <div className="flex flex-wrap justify-end gap-2 border-t border-border pt-4">
          <button
            type="button"
            onClick={handleSubmit((values) => {
              setSuccessMessage("");
              testMutation.mutate({ slug: active.slug, values });
            })}
            disabled={testMutation.isPending || saveMutation.isPending}
            className="inline-flex h-10 items-center gap-2 rounded-md border border-input px-4 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            {testMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube2 className="h-4 w-4" />}
            测试连接
          </button>
          <button
            type="submit"
            disabled={testMutation.isPending || saveMutation.isPending || verifyMutation.isPending || selectionMutation.isPending}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            {saveMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            保存配置
          </button>
        </div>
        {requiresRetest && (
          <p className="text-right text-xs text-muted-foreground">参数已变化：保存后会自动发送一次极短验证请求，可能产生少量 Token。</p>
        )}
      </form>
    </div>
  );
}
