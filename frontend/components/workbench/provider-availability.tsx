"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { listMyProviders } from "@/lib/api/workbench";
import type { ProviderConfiguration } from "@/lib/api/types";
import { isFreshVerifiedModel } from "@/lib/provider-model-status";
import { useAuth } from "@/components/auth/auth-context";

/**
 * Providers the CURRENT user may actually run a task with: their assigned
 * ApiGroup's set (admin-configured, read-only) or the global default set when
 * the user has no group. Because this hits /workbench/providers (scoped by the
 * logged-in user server-side), an employee can never pick a provider/model
 * outside their group — even by tampering with the request.
 */
export function usePrimaryProviders() {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ["workbench", "providers", user?.id ?? "anonymous"],
    queryFn: listMyProviders,
  });
  const providers = (query.data ?? []).filter(
    (provider) =>
      provider.role === "primary" &&
      provider.is_enabled &&
      provider.configured &&
      (provider.model_options?.some(
        (option) => isFreshVerifiedModel(option) && option.is_selected === true
      ) ?? false)
  );
  return { ...query, providers } as typeof query & { providers: ProviderConfiguration[] };
}

export function ProviderSetupNotice() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  return (
    <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-warning-foreground">
      没有可用的主模型配置。
      {isAdmin ? (
        <Link href="/settings/api" className="ml-2 font-medium text-primary hover:underline">
          前往 API 设置
        </Link>
      ) : (
        <span className="ml-2">请联系管理员为你分配可用的接口分组。</span>
      )}
    </p>
  );
}
