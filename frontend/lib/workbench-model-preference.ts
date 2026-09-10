import type { ProviderSlug } from "@/lib/api/types";

export type WorkbenchEntry = "hypothesis" | "judgment" | "batch";

export interface WorkbenchModelPreference {
  version: 1;
  provider: ProviderSlug;
  model: string;
}

const STORAGE_PREFIX = "workbench-model-preference";
const PROVIDERS = new Set<ProviderSlug>([
  "openai",
  "deepseek",
  "custom",
  "claude",
]);
const RETIRED_PROVIDERS = new Set(["cattoken", "cattoken_claude"]);

function storageFor(preferred?: Storage): Storage | null {
  if (preferred) return preferred;
  return typeof window === "undefined" ? null : window.localStorage;
}

function storageKey(entry: WorkbenchEntry) {
  return `${STORAGE_PREFIX}:${entry}`;
}

export function readWorkbenchModelPreference(
  entry: WorkbenchEntry,
  preferredStorage?: Storage
): WorkbenchModelPreference | null {
  try {
    const storage = storageFor(preferredStorage);
    const raw = storage?.getItem(storageKey(entry));
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object") return null;
    const candidate = value as Record<string, unknown>;
    if (
      typeof candidate.provider === "string" &&
      RETIRED_PROVIDERS.has(candidate.provider)
    ) {
      storage?.removeItem(storageKey(entry));
      return null;
    }
    if (
      candidate.version !== 1 ||
      typeof candidate.provider !== "string" ||
      !PROVIDERS.has(candidate.provider as ProviderSlug) ||
      typeof candidate.model !== "string" ||
      !candidate.model.trim()
    ) {
      return null;
    }
    return {
      version: 1,
      provider: candidate.provider as ProviderSlug,
      model: candidate.model,
    };
  } catch {
    return null;
  }
}

export function writeWorkbenchModelPreference(
  entry: WorkbenchEntry,
  value: Omit<WorkbenchModelPreference, "version">,
  preferredStorage?: Storage
): void {
  try {
    storageFor(preferredStorage)?.setItem(
      storageKey(entry),
      JSON.stringify({ version: 1, provider: value.provider, model: value.model })
    );
  } catch {
    // Browser storage may be disabled; the task form must remain usable.
  }
}
