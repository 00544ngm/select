import { apiFetch } from "./client";
import type {
  ProviderConfiguration,
  ProviderDraftPayload,
  ProviderModelVerifyResult,
  ProviderModelSelectionResult,
  ProviderSlug,
  ProviderTestResult,
  ProviderUpdatePayload,
} from "./types";

const RETIRED_PROVIDER_SLUGS = new Set(["cattoken", "cattoken_claude"]);

/**
 * Provider CRUD is scoped: global `/settings/providers` (admin's default set)
 * when no groupId is given, else the ApiGroup's own provider set under
 * `/admin/api-groups/{groupId}/providers` (admin only).
 */
function providerBase(groupId?: string): string {
  return groupId
    ? `/admin/api-groups/${groupId}/providers`
    : "/settings/providers";
}

export async function listProviders(
  groupId?: string
): Promise<ProviderConfiguration[]> {
  const providers = await apiFetch<Array<ProviderConfiguration & { slug: string }>>(
    providerBase(groupId)
  );
  return providers.filter(
    (provider): provider is ProviderConfiguration =>
      !RETIRED_PROVIDER_SLUGS.has(provider.slug)
  );
}

export function verifyProviderModel(
  slug: ProviderSlug,
  model: string,
  setDefault = false,
  isAutomatic = false,
  groupId?: string
): Promise<ProviderModelVerifyResult> {
  return apiFetch<ProviderModelVerifyResult>(
    `${providerBase(groupId)}/${slug}/models/verify`,
    {
      method: "POST",
      body: {
        model,
        set_default: setDefault,
        ...(isAutomatic ? { is_automatic: true } : {}),
      },
    }
  );
}

export function selectProviderModel(
  slug: ProviderSlug,
  model: string,
  isSelected: boolean,
  groupId?: string
): Promise<ProviderModelSelectionResult> {
  return apiFetch<ProviderModelSelectionResult>(
    `${providerBase(groupId)}/${slug}/models/${encodeURIComponent(model)}/selection`,
    { method: "PATCH", body: { is_selected: isSelected } }
  );
}

export function testProvider(
  slug: ProviderSlug,
  payload: ProviderDraftPayload,
  groupId?: string
): Promise<ProviderTestResult> {
  return apiFetch<ProviderTestResult>(`${providerBase(groupId)}/${slug}/test`, {
    method: "POST",
    body: payload,
  });
}

export function updateProvider(
  slug: ProviderSlug,
  payload: ProviderUpdatePayload,
  groupId?: string
): Promise<ProviderConfiguration> {
  return apiFetch<ProviderConfiguration>(`${providerBase(groupId)}/${slug}`, {
    method: "PUT",
    body: payload,
  });
}
