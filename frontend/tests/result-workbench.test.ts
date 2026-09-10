import { expect, it } from "vitest";
import {
  directionQuery,
  directionFinalScore,
  highestDirection,
  rankDirections,
  recommendationLabel,
  splitDirectionName,
} from "@/lib/result-workbench";
import { extractBProducts } from "@/lib/result-format";
import { buildDecisionGuidance } from "@/lib/decision-guidance";
import { amazonSearchUrl, normalizeDirectionKeywords } from "@/lib/direction-keywords";

it("normalizes structured and legacy direction keywords without guessing precision", () => {
  expect(normalizeDirectionKeywords({
    amazon: "small torpedo level",
    en: "level tool for furniture",
  })).toEqual({
    amazon: "small torpedo level",
    en: "level tool for furniture",
  });
  expect(normalizeDirectionKeywords(
    "amazon: small torpedo level; en: level tool for furniture"
  )).toEqual({
    amazon: "small torpedo level",
    en: "level tool for furniture",
  });
  expect(normalizeDirectionKeywords("level tool for furniture")).toEqual({
    amazon: "",
    en: "level tool for furniture",
  });
  expect(normalizeDirectionKeywords(null)).toEqual({ amazon: "", en: "" });
});

it("builds an Amazon search URL from only the precise keyword", () => {
  expect(amazonSearchUrl("small torpedo level")).toBe(
    "https://www.amazon.com/s?k=small%20torpedo%20level"
  );
});

it("prefers saved keywords and keeps deterministic fallbacks", () => {
  expect(
    directionQuery({
      name: "防滑垫 (Non-Slip Mat)",
      keywords: {
        en: "non slip mat",
        amazon: "pizza cutting board non slip",
      },
    })
  ).toBe("pizza cutting board non slip");
  expect(
    directionQuery({
      name: "防滑垫 (Non-Slip Mat)",
      keywords: { en: "non slip mat" },
    })
  ).toBe("non slip mat");
  expect(
    directionQuery({ name: "防滑垫 (Non-Slip Mat)", keywords: {} })
  ).toBe("Non-Slip Mat");
});

it("selects the highest score without mutating the input", () => {
  const input = [
    { name: "A", score: 70 },
    { name: "B", score: 91 },
  ];

  expect(highestDirection(input)?.name).toBe("B");
  expect(input.map((item) => item.name)).toEqual(["A", "B"]);
});

it("ranks V2 final scores and keeps rejected candidates last", () => {
  const input = [
    { name: "Rejected", score: 99, final_score: 0, rejected: true },
    { name: "Capped", score: 80, final_score: 69, rejected: false },
    { name: "Strong", score: 88, final_score: 88, rejected: false },
  ];

  expect(rankDirections(input).map((item) => item.name)).toEqual([
    "Strong",
    "Capped",
    "Rejected",
  ]);
  expect(directionFinalScore(input[0])).toBe(0);
  expect(recommendationLabel("focus")).toBe("重点开发");
  expect(recommendationLabel("not_recommended")).toBe("不推荐");
});

it("uses the preserved V2.1 stickiness potential before execution score", () => {
  expect(directionFinalScore({ stickiness_score: 84, final_score: 0 })).toBe(84);
});

it("treats an unsupported historical reject as incomplete evidence", () => {
  expect(buildDecisionGuidance({
    name: "圆珠笔套装",
    score: 0,
    type: "耗材补充",
    motivation: "",
    evidence_level: "E1",
    cost: "",
    strategy: "",
    stickiness: "低",
    model_version: "combination_model_v2.1",
    stickiness_score: 94,
    execution_status: "reject",
    decision_action: "not_recommended",
    rejection_codes: ["incompatible", "safety_blocked"],
    source_fact_ids: ["title"],
    missing_evidence: ["未提供主品笔夹可容纳的最大笔杆直径。"],
  })).toMatchObject({
    status: "historical_incomplete",
    title: "历史判定证据不完整",
    nextStep: "建议按新规则重新分析，并核对：未提供主品笔夹可容纳的最大笔杆直径。",
  });
});

it("explains hold as evidence work rather than permanent rejection", () => {
  expect(buildDecisionGuidance({
    name: "圆珠笔套装",
    score: 94,
    type: "耗材补充",
    motivation: "",
    evidence_level: "E1",
    cost: "",
    strategy: "",
    stickiness: "低",
    model_version: "combination_model_v2.1",
    stickiness_score: 94,
    execution_status: "hold",
    missing_evidence: ["核对笔夹最大直径与候选笔杆直径"],
  })).toMatchObject({
    status: "hold",
    title: "补充证据后复核",
    meaning: "当前证据不足，不代表这个辅品不能做。",
  });
});

it("shows a concrete reason for a fully evidenced rejection", () => {
  expect(buildDecisionGuidance({
    name: "圆珠笔套装",
    score: 94,
    type: "耗材补充",
    motivation: "",
    evidence_level: "E2",
    cost: "",
    strategy: "",
    stickiness: "低",
    model_version: "combination_model_v2.1",
    execution_status: "reject",
    rejection_codes: ["incompatible"],
    compatibility_status: "blocked",
    incompatibility_reason: "主品孔径 8mm，小于候选直径 12mm",
    source_fact_ids: ["spec:main", "spec:candidate"],
  })).toMatchObject({
    status: "reject",
    title: "当前方案暂不进入测试",
    reason: "主品孔径 8mm，小于候选直径 12mm",
  });
});

it("splits an existing bilingual direction name", () => {
  expect(splitDirectionName("防滑垫 (Non-Slip Mat)")).toEqual({
    zh: "防滑垫",
    en: "Non-Slip Mat",
  });
});

it("extracts veto risks and keeps G3 as positive legacy evidence", () => {
  const products = extractBProducts([
    {
      title: "否决审查",
      content: [
        "• 各B品详情: • Candidate: • 节奏不匹配: False",
        "• 竞品冲突: False",
        "• 已验证需求: False",
        "• 品牌压制: True",
        "• 物流问题: False",
        "• 法律风险: False",
        "• 差评超标: False",
        "• 被否决: False",
        "• 否决原因: ",
      ].join("\n"),
    },
  ]);

  expect(products[0].vetoed).toBe(false);
  expect(products[0].legacyG3Validated).toBe(false);
  expect(products[0].vetoRisks).toEqual({
    rhythm: false,
    competition: false,
    brandOvershadow: true,
    logistics: false,
    legal: false,
    badReviews: false,
  });
  expect(products[0].vetoReason).toBeUndefined();
});
