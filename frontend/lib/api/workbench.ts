import { apiFetch } from "./client";
import type { ProviderConfiguration } from "./types";

const RETIRED_PROVIDER_SLUGS = new Set(["cattoken", "cattoken_claude"]);

/**
 * The provider catalog the LOGGED-IN user may actually use: their assigned
 * ApiGroup's set (masked keys, read-only) or the global default set when the
 * user has no group. Read-only — used by the task model picker so an employee
 * can never see providers/models outside their group.
 */
export async function listMyProviders(): Promise<ProviderConfiguration[]> {
  const providers = await apiFetch<Array<ProviderConfiguration & { slug: string }>>(
    "/workbench/providers"
  );
  return providers.filter(
    (provider): provider is ProviderConfiguration =>
      !RETIRED_PROVIDER_SLUGS.has(provider.slug)
  );
}
