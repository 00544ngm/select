import type { ProviderConfiguration, ProviderModelOption } from "./api/types";

const protocolLabels: Record<ProviderModelOption["api_protocol"], string> = {
  openai: "OpenAI 兼容",
  anthropic: "Anthropic 兼容",
};

export function providerModelOptions(
  providers: ProviderConfiguration[]
): ProviderModelOption[] {
  return providers.flatMap((provider) =>
    provider.model_options ?? (provider.supported_models ?? []).map((model) => ({
      provider: provider.slug,
      provider_display_name: provider.display_name,
      api_protocol: provider.api_protocol,
      model,
      is_default: model === provider.default_model,
      is_selected: false,
      is_enabled: provider.is_enabled,
      test_status: "discovered" as const,
      tested_at: provider.last_tested_at,
      test_message: provider.last_test_message,
      error_code: null,
    }))
  );
}

export function formatModelIdentity(option: Pick<ProviderModelOption, "provider_display_name" | "api_protocol" | "model">): string {
  return `${option.provider_display_name} · ${protocolLabels[option.api_protocol]} · ${option.model}`;
}
