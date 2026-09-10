import { expect, it } from "vitest";
import { resultModelLabel } from "@/lib/model-label";

it("labels the primary result with the provider and model actually requested", () => {
  expect(
    resultModelLabel("gpt", { provider: "cattoken", model: "gpt-5.5" })
  ).toBe("CatToken OpenAI · gpt-5.5");
});

it("distinguishes CatToken Claude without changing the historical CatToken slug", () => {
  expect(
    resultModelLabel("gpt", {
      provider: "cattoken_claude",
      model: "claude-sonnet-4-6",
    })
  ).toBe("CatToken Claude · claude-sonnet-4-6");
});

it("keeps the secondary result labeled as DeepSeek", () => {
  expect(resultModelLabel("deepseek", {})).toBe("DeepSeek");
});
