import { expect, it } from "vitest";
import { isFreshVerifiedModel, providerModelStatusLabel } from "@/lib/provider-model-status";
import type { ProviderModelOption } from "@/lib/api/types";

function option(overrides: Partial<ProviderModelOption> = {}): ProviderModelOption {
  return {
    provider: "custom",
    provider_display_name: "自定义 API",
    api_protocol: "openai",
    model: "model-a",
    is_default: true,
    is_enabled: true,
    test_status: "verified",
    tested_at: new Date("2026-08-01T00:00:00Z").toISOString(),
    test_message: "结构化验证成功",
    ...overrides,
  };
}

it("accepts historical verification without a 24-hour expiry on the same connection", () => {
  const now = Date.parse("2026-08-01T23:59:00Z");
  expect(isFreshVerifiedModel(option(), now)).toBe(true);
  expect(isFreshVerifiedModel(option({ tested_at: "2026-06-01T23:59:00Z" }), now)).toBe(true);
  expect(isFreshVerifiedModel(option({ is_current_connection: false }), now)).toBe(false);
  expect(isFreshVerifiedModel(option({ test_status: "discovered" }), now)).toBe(false);
});

it("explains historical, stale connection and discovered states in Chinese", () => {
  expect(providerModelStatusLabel(option())).toBe("历史验证通过");
  expect(providerModelStatusLabel(option({ is_current_connection: false }))).toBe(
    "历史验证通过 · 当前连接待验证"
  );
  expect(providerModelStatusLabel(option({ test_status: "discovered", tested_at: null }))).toBe("仅目录发现，尚未验证");
  expect(providerModelStatusLabel(option({ test_status: "expired" }))).toBe("验证已过期");
});
