"use client";

import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import type { UseFormRegisterReturn } from "react-hook-form";
import type { ProviderConfiguration, ProviderSlug, RotationCandidate } from "@/lib/api/types";
import { isFreshVerifiedModel } from "@/lib/provider-model-status";
import {
  readWorkbenchModelPreference,
  writeWorkbenchModelPreference,
  type WorkbenchEntry,
  type WorkbenchModelPreference,
} from "@/lib/workbench-model-preference";

interface ModelSelectProps {
  preferenceEntry: WorkbenchEntry;
  providers: ProviderConfiguration[];
  modelRegistration: UseFormRegisterReturn;
  providerRegistration: UseFormRegisterReturn;
  onRotationChange?: (enabled: boolean, candidates: RotationCandidate[]) => void;
}

export function defaultModelHint(provider: ProviderConfiguration) {
  return provider.default_model || "gpt-4o";
}

export function availableModelsFor(provider: ProviderConfiguration) {
  return (provider.model_options ?? [])
    .filter((option) => isFreshVerifiedModel(option) && option.is_selected === true)
    .map((option) => option.model);
}

function isAvailablePreference(
  preference: WorkbenchModelPreference,
  providers: ProviderConfiguration[]
) {
  const provider = providers.find((item) => item.slug === preference.provider);
  if (!provider) return false;
  return availableModelsFor(provider).includes(preference.model);
}

function registrationEvent(registration: UseFormRegisterReturn, value: string) {
  return { target: { name: registration.name, value } };
}

export default function ModelSelect({
  preferenceEntry,
  providers,
  modelRegistration,
  providerRegistration,
  onRotationChange,
}: ModelSelectProps) {
  const [providerSlug, setProviderSlug] = useState<ProviderSlug | "">("");
  const [model, setModel] = useState("");
  const [savedPreference, setSavedPreference] = useState<WorkbenchModelPreference | null>(null);
  const [invalidSavedPreference, setInvalidSavedPreference] = useState(false);
  const [rotationEnabled, setRotationEnabled] = useState(false);
  const [rotationOrder, setRotationOrder] = useState<string[]>([]);
  const catalogFingerprint = useMemo(
    () => providers
      .map((provider) => `${provider.slug}:${defaultModelHint(provider)}:${availableModelsFor(provider).join(",")}`)
      .join("|"),
    [providers]
  );

  const selectedProvider = providers.find((provider) => provider.slug === providerSlug) ?? providers[0];
  const models = selectedProvider ? availableModelsFor(selectedProvider) : [];
  const resolvedModel = selectedProvider ? model || models[0] || "" : "";
  const availableRotationCandidates = useMemo<RotationCandidate[]>(
    () => (selectedProvider?.model_options ?? [])
      .filter((option) => models.includes(option.model))
      .map((option) => ({
        provider: option.provider,
        model: option.model,
        api_protocol: option.api_protocol,
        connection_revision: option.current_connection_revision ?? option.connection_revision ?? 1,
      })),
    [selectedProvider, models]
  );
  const orderedCandidates = useMemo(
    () => rotationOrder
      .map((item) => availableRotationCandidates.find((candidate) => candidate.model === item))
      .filter((item): item is RotationCandidate => !!item),
    [availableRotationCandidates, rotationOrder]
  );
  const currentIsSaved = !!selectedProvider && !!savedPreference &&
    savedPreference.provider === selectedProvider.slug && savedPreference.model === resolvedModel;

  useEffect(() => {
    if (!providers[0]) return;
    const stored = readWorkbenchModelPreference(preferenceEntry);
    const validStored = stored && isAvailablePreference(stored, providers) ? stored : null;
    const nextProvider = validStored
      ? providers.find((provider) => provider.slug === validStored.provider) ?? providers[0]
      : providers[0];
    const nextModel = validStored?.model ?? availableModelsFor(nextProvider)[0] ?? "";

    setProviderSlug(nextProvider.slug);
    setModel(nextModel);
    setSavedPreference(validStored);
    setInvalidSavedPreference(!!stored && !validStored);
    setRotationOrder([nextModel, ...availableModelsFor(nextProvider).filter((item) => item !== nextModel)]);
    providerRegistration.onChange(registrationEvent(providerRegistration, nextProvider.slug));
    modelRegistration.onChange(registrationEvent(modelRegistration, nextModel));
    // The fingerprint intentionally represents the latest verified catalog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preferenceEntry, catalogFingerprint]);

  const rotationFingerprint = orderedCandidates
    .map((candidate) => `${candidate.provider}:${candidate.api_protocol}:${candidate.model}:${candidate.connection_revision}`)
    .join("|");
  useEffect(() => {
    onRotationChange?.(rotationEnabled, rotationEnabled ? orderedCandidates : []);
    // The parent callback is intentionally excluded: forms provide an inline
    // state adapter and should only receive updates when the selection changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rotationEnabled, rotationFingerprint]);

  if (!selectedProvider) return null;
  const providerId = `${preferenceEntry}-provider`;
  const modelId = `${preferenceEntry}-model`;

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <label htmlFor={providerId} className="text-sm text-muted-foreground">供应商</label>
        <select
          id={providerId}
          name={providerRegistration.name}
          ref={providerRegistration.ref}
          onBlur={providerRegistration.onBlur}
          value={selectedProvider.slug}
          onChange={(event) => {
            const nextSlug = event.target.value as ProviderSlug;
            const nextProvider = providers.find((provider) => provider.slug === nextSlug);
            const nextModel = nextProvider ? availableModelsFor(nextProvider)[0] ?? "" : "";
            setProviderSlug(nextSlug);
            setModel(nextModel);
            setRotationOrder([nextModel, ...availableModelsFor(nextProvider ?? selectedProvider).filter((item) => item !== nextModel)]);
            providerRegistration.onChange(event);
            modelRegistration.onChange(registrationEvent(modelRegistration, nextModel));
          }}
          className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground"
        >
          {providers.map((provider) => (
            <option key={provider.slug} value={provider.slug}>{provider.display_name}</option>
          ))}
        </select>
      </div>

      <div className="space-y-2 border-t border-border pt-3">
        <label className="flex items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            checked={rotationEnabled}
            onChange={(event) => {
              const enabled = event.target.checked;
              setRotationEnabled(enabled);
              if (enabled && rotationOrder.length === 0) {
                setRotationOrder([resolvedModel, ...models.filter((item) => item !== resolvedModel)]);
              }
            }}
            className="h-4 w-4 rounded border-border"
          />
          启用模型轮换
        </label>
        {rotationEnabled && (
          <div className="space-y-1.5 rounded-md border border-border bg-muted/20 p-2">
            <p className="text-xs text-muted-foreground">技术失败时按以下顺序尝试，每个模型最多一次</p>
            {orderedCandidates.map((candidate, index) => (
              <div key={`${candidate.provider}:${candidate.model}`} className="flex items-center gap-2 text-sm">
                <span className="w-5 text-center text-xs text-muted-foreground">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate">{candidate.model}</span>
                <button
                  type="button"
                  aria-label={`上移 ${candidate.model}`}
                  title="上移"
                  disabled={index === 0}
                  onClick={() => setRotationOrder((items) => {
                    const next = [...items];
                    [next[index - 1], next[index]] = [next[index], next[index - 1]];
                    return next;
                  })}
                  className="rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
                ><ArrowUp className="h-3.5 w-3.5" /></button>
                <button
                  type="button"
                  aria-label={`下移 ${candidate.model}`}
                  title="下移"
                  disabled={index === orderedCandidates.length - 1}
                  onClick={() => setRotationOrder((items) => {
                    const next = [...items];
                    [next[index], next[index + 1]] = [next[index + 1], next[index]];
                    return next;
                  })}
                  className="rounded p-1 text-muted-foreground hover:bg-muted disabled:opacity-30"
                ><ArrowDown className="h-3.5 w-3.5" /></button>
              </div>
            ))}
            {orderedCandidates.length === 0 && <p className="text-xs text-warning-foreground">没有可轮换的已验证模型</p>}
          </div>
        )}
      </div>

      <div className="space-y-1.5">
        <label htmlFor={modelId} className="text-sm text-muted-foreground">模型</label>
        {models.length > 0 ? (
          <select
            id={modelId}
            name={modelRegistration.name}
            ref={modelRegistration.ref}
            onBlur={modelRegistration.onBlur}
            value={model}
            onChange={(event) => {
              const nextModel = event.target.value;
              setModel(nextModel);
              if (rotationEnabled) {
                setRotationOrder([nextModel, ...models.filter((item) => item !== nextModel)]);
              }
              modelRegistration.onChange(event);
            }}
            className="h-10 w-full rounded-md border border-border bg-background px-3 text-sm focus:outline-none focus:ring-1 focus:ring-foreground"
          >
            {models.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        ) : (
          <p className="flex h-10 items-center rounded-md border border-warning/40 bg-warning/10 px-3 text-sm text-warning-foreground">
            请先在 API 设置中验证并勾选模型
          </p>
        )}
      </div>

      {invalidSavedPreference && (
        <p className="text-xs text-warning-foreground" role="status">
          原默认模型已不可用，请重新保存
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => {
            const preference = {
              provider: selectedProvider.slug,
              model: resolvedModel,
            };
            writeWorkbenchModelPreference(preferenceEntry, preference);
            setSavedPreference({ version: 1, ...preference });
            setInvalidSavedPreference(false);
          }}
          className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium hover:bg-muted"
        >
          保存为此入口默认选择
        </button>
        <span className="text-xs text-muted-foreground">
          {currentIsSaved ? "已保存默认" : "尚未保存"}
        </span>
      </div>
    </div>
  );
}
