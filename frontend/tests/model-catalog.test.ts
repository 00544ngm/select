import { describe, expect, it } from "vitest";
import {
  filterAndSortModelCatalog,
  recentModelOptions,
  type ModelCatalogFilter,
  type ModelCatalogSort,
} from "@/lib/model-catalog";
import type { ProviderModelOption } from "@/lib/api/types";

function model(
  name: string,
  overrides: Partial<ProviderModelOption> = {}
): ProviderModelOption {
  return {
    provider: "openai",
    provider_display_name: "OpenAI",
    api_protocol: "openai",
    model: name,
    is_default: false,
    is_selected: false,
    is_enabled: true,
    test_status: "discovered",
    tested_at: null,
    test_message: null,
    ...overrides,
  };
}

describe("model catalog", () => {
  const options = [
    model("gpt-3.5-turbo"),
    model("gpt-5.6-sol", {
      is_selected: true,
      test_status: "verified",
      tested_at: "2026-08-01T10:00:00Z",
      last_used_at: "2026-08-04T10:00:00Z",
      use_count: 8,
      is_current_connection: true,
    }),
    model("gpt-5.5", {
      test_status: "verified",
      tested_at: "2026-08-03T10:00:00Z",
      last_used_at: "2026-08-02T10:00:00Z",
      use_count: 3,
      is_current_connection: true,
    }),
    model("text-embedding-3-large", {
      last_used_at: "2026-08-01T10:00:00Z",
      use_count: 1,
    }),
  ];

  it("searches model names case-insensitively", () => {
    const result = filterAndSortModelCatalog(options, {
      query: "GPT-5",
      filter: "all",
      sort: "smart",
    });
    expect(result.map((item) => item.model)).toEqual(["gpt-5.6-sol", "gpt-5.5"]);
  });

  it.each<[ModelCatalogFilter, string[]]>([
    ["recent", ["gpt-5.6-sol", "gpt-5.5", "text-embedding-3-large"]],
    ["verified", ["gpt-5.6-sol", "gpt-5.5"]],
  ])("filters %s models", (filter, expected) => {
    const result = filterAndSortModelCatalog(options, {
      query: "",
      filter,
      sort: "smart",
    });
    expect(result.map((item) => item.model)).toEqual(expected);
  });

  it.each<[ModelCatalogSort, string[]]>([
    ["recent", ["gpt-5.6-sol", "gpt-5.5", "text-embedding-3-large", "gpt-3.5-turbo"]],
    ["usage", ["gpt-5.6-sol", "gpt-5.5", "text-embedding-3-large", "gpt-3.5-turbo"]],
    ["verified", ["gpt-5.5", "gpt-5.6-sol", "gpt-3.5-turbo", "text-embedding-3-large"]],
    ["name", ["gpt-3.5-turbo", "gpt-5.5", "gpt-5.6-sol", "text-embedding-3-large"]],
  ])("sorts by %s", (sort, expected) => {
    const result = filterAndSortModelCatalog(options, {
      query: "",
      filter: "all",
      sort,
    });
    expect(result.map((item) => item.model)).toEqual(expected);
  });

  it("returns only the latest ten used models for automatic verification", () => {
    const many = Array.from({ length: 12 }, (_, index) =>
      model(`model-${index}`, {
        last_used_at: `2026-08-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
      })
    );
    const recent = recentModelOptions(many, 10);
    expect(recent).toHaveLength(10);
    expect(recent[0].model).toBe("model-11");
    expect(recent.at(-1)?.model).toBe("model-2");
  });
});
