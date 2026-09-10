import type { ProviderModelOption } from "./api/types";

export function isFreshVerifiedModel(
  option: ProviderModelOption,
  _now = Date.now()
): boolean {
  return Boolean(
    option.is_enabled &&
      option.test_status === "verified" &&
      option.tested_at &&
      option.is_current_connection !== false
  );
}

export function providerModelStatusLabel(option: ProviderModelOption): string {
  if (option.test_status === "verified") {
    return option.is_current_connection === false
      ? "历史验证通过 · 当前连接待验证"
      : "历史验证通过";
  }
  if (option.test_status === "unavailable") return "当前不可用";
  if (option.test_status === "temporary_error") return "上游暂时异常";
  if (option.test_status === "expired") return "验证已过期";
  return "仅目录发现，尚未验证";
}
