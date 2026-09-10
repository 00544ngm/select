const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  cattoken: "CatToken OpenAI",
  cattoken_claude: "CatToken Claude",
  custom: "自定义 API",
  deepseek: "DeepSeek",
  claude: "Claude",
};

export function providerModelLabel(provider: string, model: string) {
  const providerLabel = PROVIDER_LABELS[provider] ?? provider;
  return model ? `${providerLabel} · ${model}` : `${providerLabel} · 默认模型`;
}

export function resultModelLabel(
  modelKey: string,
  requestPayload: Record<string, unknown>
) {
  if (modelKey === "deepseek") return "DeepSeek";
  if (modelKey !== "gpt") return modelKey;

  const provider = typeof requestPayload.provider === "string"
    ? requestPayload.provider
    : "openai";
  const model = typeof requestPayload.model === "string"
    ? requestPayload.model
    : "";
  return providerModelLabel(provider, model);
}
