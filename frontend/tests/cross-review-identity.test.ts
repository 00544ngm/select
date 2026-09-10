import { describe, expect, it } from "vitest";

import {
  describeCrossReviewEntry,
  extractCrossReviewSummary,
  formatFullIdentity,
} from "@/lib/cross-review-identity";

const reviewers = [
  {
    provider: "deepseek",
    display_name: "DeepSeek",
    api_protocol: "openai",
    model: "deepseek-v4-pro",
  },
  {
    provider: "claude",
    display_name: "Claude",
    api_protocol: "anthropic",
    model: "claude-opus-5",
  },
];

describe("describeCrossReviewEntry", () => {
  it("maps reviewer_a to reviewer_b using persisted identities", () => {
    expect(
      describeCrossReviewEntry("reviewer_a_reviews_reviewer_b", reviewers).title,
    ).toBe("DeepSeek（deepseek-v4-pro）评审 Claude（claude-opus-5）");
  });

  it("maps the reverse direction", () => {
    expect(
      describeCrossReviewEntry("reviewer_b_reviews_reviewer_a", reviewers).title,
    ).toBe("Claude（claude-opus-5）评审 DeepSeek（deepseek-v4-pro）");
  });

  it("uses persisted identities for a legacy key", () => {
    expect(describeCrossReviewEntry("gpt_reviews_deepseek", reviewers).title).toBe(
      "DeepSeek（deepseek-v4-pro）评审 Claude（claude-opus-5）",
    );
  });

  it("never exposes internal reviewer keys when identities are absent", () => {
    expect(
      describeCrossReviewEntry("reviewer_a_reviews_reviewer_b", []).title,
    ).toBe("评审模型 A 评审 评审模型 B");
  });

  it("does not guess when reviewer count is invalid", () => {
    expect(
      describeCrossReviewEntry("reviewer_a_reviews_reviewer_b", reviewers.slice(0, 1))
        .title,
    ).toBe("交叉评审结果");
  });

  it("formats the protocol in the full identity", () => {
    expect(formatFullIdentity(reviewers[1])).toBe(
      "Claude · Anthropic 兼容 · claude-opus-5",
    );
    expect(formatFullIdentity(undefined)).toBe("历史任务未记录");
  });
});

describe("extractCrossReviewSummary", () => {
  it("extracts the fixed conclusion type and one-line conclusion", () => {
    const raw = [
      "## 结论摘要",
      "",
      "结论类型：部分认可",
      "",
      "一句话结论：方向合理，但证据不足。",
      "",
      "## 认可之处",
      "- 场景成立",
    ].join("\n");

    expect(extractCrossReviewSummary(raw)).toEqual({
      conclusionType: "部分认可",
      conclusion: "方向合理，但证据不足。",
    });
  });

  it("falls back safely for historical free-form output", () => {
    expect(extractCrossReviewSummary("旧任务自由文本")).toEqual({
      conclusionType: "无法判断",
      conclusion: "旧任务未提供结构化结论，请查看评审原文。",
    });
  });
});
