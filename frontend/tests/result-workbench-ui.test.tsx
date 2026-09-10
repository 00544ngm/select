import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import ProductMedia from "@/components/jobs/product-media";
import ResultAnalysisModule from "@/components/jobs/result-analysis-module";
import StickinessScorecard from "@/components/jobs/stickiness-scorecard";
import JudgmentAnalysis from "@/components/jobs/judgment-analysis";
import ProductTypeReviewCard from "@/components/jobs/product-type-review-card";
import BatchLeaderboard from "@/components/jobs/batch-leaderboard";
import type { ComplementEvidencePayload, ProductTypeReview, StructuredDirection } from "@/lib/api/types";

const directions: StructuredDirection[] = [
  {
    name: "方向甲 (Direction A)",
    score: 70,
    type: "便利型",
    motivation: "便利闭环",
    motivation_evidence: "甲方向证据",
    evidence_level: "证据 3",
    cost: "¥8",
    strategy: "$15.99",
    stickiness: "中",
    keywords: { en: "direction a" },
    deep_arguments: { user_rationale: "甲方向用户理由" },
    delivery_checklist: { bundling_display: "甲方向展示" },
  },
  {
    name: "方向乙 (Direction B)",
    score: 91,
    type: "低成本价值附加",
    motivation: "痛点解决",
    motivation_evidence: "乙方向证据",
    evidence_level: "证据 2",
    cost: "¥3-6",
    strategy: "$16.97",
    stickiness: "高",
    keywords: { en: "direction b" },
    deep_arguments: { user_rationale: "乙方向用户理由" },
    delivery_checklist: { bundling_display: "乙方向展示" },
  },
];

const reviewEvidence = [{ source_field: "title", verbatim_quote: "Stainless steel bottle opener" }];

it.each([
  ["confirmed_non_food", "确认非食品", "规则判断", "允许继续分析"],
  ["confirmed_food", "确认食品（不符合准入范围）", "模型复核", "食品不准入，已阻断"],
  ["likely_non_food", "倾向非食品（建议复核）", "安全降级", "继续分析，建议人工复核"],
  ["needs_review", "需要人工复核", "模型复核", "继续分析，建议人工复核"],
] as const)("renders %s product review entirely in Chinese", (status, conclusion, source, action) => {
  render(<ProductTypeReviewCard review={{
    status,
    source: status === "confirmed_non_food" ? "rule" : status === "likely_non_food" ? "fallback" : "model",
    confidence: 0.87,
    reason: "根据商品标题复核",
    evidence: reviewEvidence,
    action: status === "confirmed_non_food" ? "continue" : status === "confirmed_food" ? "block" : "continue_with_review",
  }} />);

  expect(screen.getByText(conclusion)).toBeInTheDocument();
  expect(screen.getByText(source)).toBeInTheDocument();
  expect(screen.getByText(action)).toBeInTheDocument();
  expect(screen.getByText("来源字段：商品标题")).toBeInTheDocument();
  expect(screen.getByText("原文摘录：Stainless steel bottle opener")).toBeInTheDocument();
  if (status === "needs_review") expect(screen.queryByText(/任务失败/)).not.toBeInTheDocument();
});

it("shows top-level review but omits the card for an old payload", () => {
  const { rerender } = render(<ResultAnalysisModule
    productTypeReview={{
      status: "confirmed_non_food", source: "rule", confidence: 1,
      reason: "标题明确为工具", evidence: reviewEvidence, action: "continue",
    }}
  />);
  expect(screen.getByRole("heading", { name: "商品类型复核" })).toBeInTheDocument();
  rerender(<ResultAnalysisModule />);
  expect(screen.queryByRole("heading", { name: "商品类型复核" })).not.toBeInTheDocument();
});

it("shows a direction review inside its scorecard", () => {
  render(<StickinessScorecard direction={{
    ...directions[0],
    product_type_review: {
      status: "needs_review", source: "fallback", confidence: 0.35,
      reason: "标题信息不足", evidence: [], action: "continue_with_review",
    },
  }} />);
  expect(screen.getByRole("heading", { name: "商品类型复核" })).toBeInTheDocument();
  expect(screen.getByText("需要人工复核")).toBeInTheDocument();
  expect(screen.getByText("安全降级")).toBeInTheDocument();
});

it("explains rejected food products without exposing internal action codes", () => {
  render(<ResultAnalysisModule rejectedBProducts={[{
    title: "Chocolate Bar", action: "rejected_food_product",
    review: { status: "confirmed_food", source: "rule", confidence: 1, reason: "标题明确为巧克力食品", evidence: reviewEvidence, action: "block" },
  }]} />);
  expect(screen.getByText("食品辅品不准入")).toBeInTheDocument();
  expect(screen.getByText(/Chocolate Bar：确认为食品/)).toBeInTheDocument();
  expect(screen.queryByText("rejected_food_product")).not.toBeInTheDocument();
});

it("renders a transition review with safe Chinese fallbacks", () => {
  render(<ProductTypeReviewCard review={{ status: "needs_review", reason: "历史结果只保存了结论" }} />);
  expect(screen.getByText("需要人工复核")).toBeInTheDocument();
  expect(screen.getByText("历史未记录")).toBeInTheDocument();
  expect(screen.getByText("继续分析，建议人工复核")).toBeInTheDocument();
  expect(screen.queryByText(/undefined|任务失败|已阻断/)).not.toBeInTheDocument();
});

it("shows a Chinese review reason and keeps historical English expandable", async () => {
  const user = userEvent.setup();
  render(<ProductTypeReviewCard review={{
    status: "confirmed_non_food",
    source: "model",
    action: "continue",
    reason: "The product is a kitchen utensil, not food itself.",
    reason_zh: "该商品是厨房工具，本身不是食品。",
    reason_original: "The product is a kitchen utensil, not food itself.",
  }} />);

  expect(screen.getByText("该商品是厨房工具，本身不是食品。")).toBeVisible();
  await user.click(screen.getByText("查看英文原文"));
  expect(screen.getByText("The product is a kitchen utensil, not food itself.")).toBeVisible();
});

it("summarizes an English-only historical reason without inventing product facts", () => {
  render(<ProductTypeReviewCard review={{
    status: "confirmed_non_food",
    source: "model",
    action: "continue",
    reason: "Legacy English reason.",
  }} />);
  expect(screen.getByText("确认非食品；判断来源为模型复核；系统允许继续分析。")).toBeVisible();
  expect(screen.getByText("查看英文原文")).toBeVisible();
});

it("renders a food-blocked batch item in Chinese and keeps old batch items compatible", async () => {
  const user = userEvent.setup();
  render(<BatchLeaderboard results={[
    {
      mode: "hypothesis", product_title: "Chocolate Bar", result_status: "food_blocked" as never,
      product_type_review: { status: "confirmed_food", reason: "标题明确为巧克力食品", action: "block" },
    },
    { mode: "hypothesis", product_title: "Legacy Tool", score: 72 },
  ]} />);

  await user.click(screen.getByRole("button", { name: /Chocolate Bar/ }));
  expect(screen.getByText("确认食品（不符合准入范围）")).toBeInTheDocument();
  expect(screen.getByText("标题明确为巧克力食品")).toBeInTheDocument();
  expect(screen.getByText("食品不准入，已阻断")).toBeInTheDocument();
  expect(screen.queryByText(/confirmed_food|food_blocked|\bblock\b/)).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /Legacy Tool/ }));
  expect(screen.queryByRole("heading", { name: "商品类型复核" })).not.toBeInTheDocument();
});

it.each([
  { evidence: { source_field: "title", verbatim_quote: "object" } },
  { evidence: "title text" },
  { evidence: [null, "bad", 3, {}, { source_field: "title" }, { verbatim_quote: "missing source" }, { source_field: "description", verbatim_quote: "Valid description" }] },
])("ignores malformed evidence without losing valid quotes", ({ evidence }) => {
  render(<ProductTypeReviewCard review={{
    status: "needs_review", reason: "安全复核", evidence,
  } as unknown as ProductTypeReview} />);
  expect(screen.getByText("需要人工复核")).toBeInTheDocument();
  if (Array.isArray(evidence)) {
    expect(screen.getByText("来源字段：商品描述")).toBeInTheDocument();
    expect(screen.getByText("原文摘录：Valid description")).toBeInTheDocument();
  }
});

it("renders unknown review enums and evidence fields as safe Chinese fallbacks", () => {
  render(<ProductTypeReviewCard review={{
    status: "new_status", source: "new_source", action: "new_action", reason: "待人工判断",
    evidence: [
      { source_field: "name_zh", verbatim_quote: "开瓶器" },
      { source_field: "name_en", verbatim_quote: "Bottle opener" },
      { source_field: "canonical_name", verbatim_quote: "bottle opener" },
      { source_field: "bullet_points[2]", verbatim_quote: "Steel body" },
      { source_field: "attributes.material", verbatim_quote: "Steel" },
      { source_field: "internal_new_field", verbatim_quote: "Unknown" },
    ],
  } as unknown as ProductTypeReview} />);
  expect(screen.getByText("未知商品类型（需要人工复核）")).toBeInTheDocument();
  expect(screen.getByText("历史未记录")).toBeInTheDocument();
  expect(screen.getByText("继续分析，建议人工复核")).toBeInTheDocument();
  ["中文名称", "英文名称", "规范名称", "商品要点 2", "商品属性", "商品信息"].forEach((label) => {
    expect(screen.getByText(`来源字段：${label}`)).toBeInTheDocument();
  });
  expect(screen.queryByText(/new_status|new_source|new_action|internal_new_field/)).not.toBeInTheDocument();
});

it("uses arbitrary nested model keys in insertion order and allows switching all models", async () => {
  const user = userEvent.setup();
  render(<BatchLeaderboard results={[{
    models: {
      "custom:alpha": { product_title: "Alpha Result", score: 88, product_type_review: { status: "likely_non_food", reason: "Alpha review" } },
      "azure:beta": { product_title: "Beta Result", score: 64, product_type_review: { status: "confirmed_non_food", reason: "Beta review", action: "continue" } },
    },
  }]} />);
  expect(screen.getByRole("button", { name: /Alpha Result/ })).toBeInTheDocument();
  expect(screen.getByText("88")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /Alpha Result/ }));
  expect(screen.getByText("Alpha review")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "custom:alpha" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "azure:beta" })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "azure:beta" }));
  expect(screen.getByText("Beta review")).toBeInTheDocument();
  expect(screen.getByText("确认非食品")).toBeInTheDocument();
});

const vetoSections = [
  {
    title: "否决审查",
    content: [
      "• 各B品详情: • Candidate Product: • 节奏不匹配: False",
      "• 竞品冲突: False",
      "• 已验证需求: False",
      "• 品牌压制: False",
      "• 物流问题: False",
      "• 法律风险: False",
      "• 差评超标: False",
      "• 被否决: False",
      "• 否决原因: ",
    ].join("\n"),
  },
];

const complementEvidence: ComplementEvidencePayload = {
  per_b_product: {
    "Candidate Product": {
      product_title: "Candidate Product",
      product_url: "https://www.walmart.com/ip/item/123",
      platform: "Walmart",
      verified_at: "2026-07-28T14:30:00+00:00",
      status: "verified",
      analysis_state: "completed",
      valid_review_count: 20,
      relevant_review_count: 3,
      hit_rate: 0.15,
      failure_reason: "",
      evidence: [
        {
          review_index: 0,
          original_text: "I need a matching holder to use this product properly.",
          translation_zh: "我需要一个配套支架才能正常使用。",
          keywords: ["matching holder"],
          reason: "明确表达配套需求",
          strength: "explicit",
          source_url: "https://www.walmart.com/ip/item/123",
        },
      ],
    },
  },
};

const API_BASE = "http://localhost:8000";
const server = setupServer(
  http.post(API_BASE + "/api/v1/search", async ({ request }) => {
    const body = (await request.json()) as { keyword: string };
    return HttpResponse.json({
      results: [
        {
          title: "Platform result for " + body.keyword,
          url: "https://www.walmart.com/ip/result/1",
          price: "$9.99",
          rating: "4.5",
          review_count: "20",
          image: "https://images.example/result.jpg",
        },
      ],
    });
  })
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
beforeEach(() => server.resetHandlers());

it("selects the actual highest-scoring direction and switches details", async () => {
  const user = userEvent.setup();
  render(
    <ResultAnalysisModule
      structuredDirections={directions}
      productTitle="Pizza Cutter"
      productImages={["https://images.example/main.jpg"]}
      keywordPack={["pizza cutter accessories"]}
    />
  );

  expect(screen.getByRole("button", { name: /方向乙/ })).toHaveAttribute(
    "aria-current",
    "true"
  );
  expect(screen.getByRole("heading", { name: "方向乙" })).toBeInTheDocument();
  expect(screen.getByText("Amazon 精准关键词")).toBeInTheDocument();
  expect(screen.getByText("英文通用关键词")).toBeInTheDocument();
  expect(screen.getByText("结论摘要")).toBeInTheDocument();
  expect(screen.getByText("核心理由")).toBeInTheDocument();
  expect(screen.getAllByText("购买链路").length).toBeGreaterThan(0);
  expect(screen.getByText("深度分析（点击展开）")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "深度分析（点击展开）" }));
  expect(screen.getByText("乙方向用户理由")).toBeInTheDocument();
  expect(screen.getByText("深度分析分组")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /方向甲/ }));

  expect(screen.getByRole("button", { name: /方向甲/ })).toHaveAttribute(
    "aria-current",
    "true"
  );
  expect(screen.getByRole("heading", { name: "方向甲" })).toBeInTheDocument();
  expect(screen.getByText("甲方向用户理由")).toBeInTheDocument();
});

it("shows one Chinese eligibility status with preserved stickiness potential", async () => {
  const user = userEvent.setup();
  render(
    <ResultAnalysisModule
      structuredDirections={[{
        ...directions[0],
        model_version: "combination_model_v2.1",
        stickiness_score: 84,
        final_score: 0,
        execution_status: "hold",
        decision_action: "not_recommended",
        recommendation_level: "not_recommended",
        missing_evidence: ["核对笔夹最大直径与候选笔杆直径"],
      }]}
      productTitle="Travel Bag"
      productImages={[]}
      keywordPack={[]}
    />
  );

  expect(screen.getByText("补充证据后复核")).toBeInTheDocument();
  expect(screen.getByText("粘性潜力：84/100")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "深度分析（点击展开）" }));
  expect(screen.getByText("为什么")).toBeInTheDocument();
  expect(screen.getByText("下一步")).toBeInTheDocument();
  expect(
    screen.getByText("当前证据不足，不代表这个辅品不能做。")
  ).toBeInTheDocument();
  expect(screen.queryByText("执行状态")).not.toBeInTheDocument();
  expect(screen.queryByText("最终动作")).not.toBeInTheDocument();
  expect(screen.queryByText("拒绝（reject）")).not.toBeInTheDocument();
  expect(screen.queryByText("不建议（not_recommended）")).not.toBeInTheDocument();
});

it("opens deep analysis and focuses the current direction evidence", async () => {
  const user = userEvent.setup();
  const scrollIntoView = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoView,
  });
  render(
    <ResultAnalysisModule
      structuredDirections={[{
        ...directions[0],
        model_version: "combination_model_v2.1",
        execution_status: "hold",
        missing_evidence: ["核对主品尺寸与候选规格"],
      }]}
    />
  );

  await user.click(screen.getByRole("button", { name: "查看待补证据" }));

  const target = screen.getByRole("region", { name: "待验证证据" });
  expect(target).toHaveFocus();
  expect(target).toHaveAttribute("data-highlighted", "true");
  expect(scrollIntoView).toHaveBeenCalled();
  expect(screen.getByText("核对主品尺寸与候选规格")).toBeInTheDocument();
});

it("opens and focuses the explanation for incomplete historical judgments", async () => {
  const user = userEvent.setup();
  const scrollIntoView = vi.fn();
  Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
    configurable: true,
    value: scrollIntoView,
  });
  render(
    <ResultAnalysisModule
      structuredDirections={[{
        ...directions[0],
        model_version: "combination_model_v2.1",
        execution_status: "reject",
        rejected: true,
        rejection_codes: ["incompatible"],
        source_fact_ids: ["title"],
        missing_evidence: ["核对具体兼容条件"],
      }]}
    />
  );

  await user.click(screen.getByRole("button", { name: "查看历史判定说明" }));

  const target = screen.getByRole("region", { name: "处理说明" });
  expect(target).toHaveFocus();
  expect(target).toHaveAttribute("data-highlighted", "true");
  expect(scrollIntoView).toHaveBeenCalled();
  expect(screen.getByRole("region", { name: "待验证证据" })).toBeInTheDocument();
});

it("does not present an unsupported historical rejection as a confirmed fact", () => {
  render(<StickinessScorecard direction={{
    ...directions[0],
    model_version: "combination_model_v2.1",
    stickiness_score: 94,
    final_score: 0,
    rejected: true,
    execution_status: "reject",
    decision_action: "not_recommended",
    rejection_codes: ["incompatible", "safety_blocked"],
    source_fact_ids: ["title"],
    missing_evidence: ["未提供主品笔夹可容纳的最大笔杆直径。"],
  }} />);

  expect(screen.getByText("历史判定证据不完整")).toBeInTheDocument();
  expect(
    screen.getByText("不能据此判断这个辅品永久不能做。")
  ).toBeInTheDocument();
  expect(screen.queryByText("确认不符合准入条件")).not.toBeInTheDocument();
  expect(screen.queryByText("不建议（not_recommended）")).not.toBeInTheDocument();
});

it("renders deep analysis as scan-friendly grouped cards", async () => {
  const user = userEvent.setup();
  render(
    <ResultAnalysisModule
      structuredDirections={[{
        ...directions[0],
        deep_arguments: {
          assumptions: ["规格兼容"],
          consistency: { user: { score: 5, reason: "用户重合" } },
          purchase_chain: { before_use: "准备主品", using_main: "执行主品任务" },
        },
      }]}
    />
  );

  await user.click(screen.getByRole("button", { name: "深度分析（点击展开）" }));
  expect(screen.getByText("深度分析分组")).toBeInTheDocument();
  expect(screen.getByText("分析假设")).toBeInTheDocument();
  expect(screen.getByText("一致性评分")).toBeInTheDocument();
  expect(screen.getAllByText("购买链路").length).toBeGreaterThan(0);
});

it("does not duplicate bilingual deep-analysis labels", async () => {
  const user = userEvent.setup();
  render(<ResultAnalysisModule structuredDirections={[{
    ...directions[0],
    consistency: { user: { score: 5, reason: "鐢ㄦ埛閲嶅悎" } },
  }]} />);

  const deepButton = screen.getAllByRole("button").find((button) => button.getAttribute("aria-expanded") === "false");
  expect(deepButton).toBeDefined();
  await user.click(deepButton!);
  const consistencyText = (screen.getAllByText(/user/).find((element) => element.tagName === "SPAN")?.textContent) ?? "";
  expect(consistencyText.match(/user/g)).toHaveLength(1);
  const scoreText = (screen.getAllByText(/score/).find((element) => element.tagName === "SPAN")?.textContent) ?? "";
  expect(scoreText.match(/score/g)).toHaveLength(1);
});

it("presents evidence metadata as a readable field grid", () => {
  render(<StickinessScorecard direction={{
    ...directions[0],
    evidence: { market: { query: "cat backpack carrier pet carrier backpack", matched_count: 20, verified_at: "2026-07-30T12:00:00Z" } },
  }} />);

  expect(screen.getAllByText(/English/).length).toBeGreaterThan(0);
  expect(screen.getByText(/cat backpack carrier pet carrier backpack/)).toBeInTheDocument();
  expect(screen.getAllByText(/^20$/).length).toBeGreaterThan(0);
});

it("makes deep analysis an explicit primary action", () => {
  render(<ResultAnalysisModule structuredDirections={directions} />);
  const button = screen.getAllByRole("button").find((candidate) => candidate.getAttribute("aria-expanded") === "false");
  expect(button).toBeDefined();
  const actionButton = button!;
  expect(actionButton.className).toContain("bg-primary");
  expect(actionButton.className).toContain("justify-between");
});

it("renders extended scenarios as separate readable cards", async () => {
  const user = userEvent.setup();
  render(<ResultAnalysisModule structuredDirections={[{
    ...directions[0],
    extended_scenarios: [
      { name: "户外徒步携带宠物", reason: "组合降低走失风险", assumption: "宠物会短暂离开背包" },
      { name: "机场候机", reason: "牵引绳便于短时活动", assumption: "允许宠物离开背包" },
    ],
  }]} />);
  await user.click(screen.getByRole("button", { name: "深度分析（点击展开）" }));
  expect(screen.getAllByText("户外徒步携带宠物").length).toBeGreaterThan(0);
  expect(screen.getAllByText("机场候机").length).toBeGreaterThan(0);
  expect(screen.getAllByText(/理由/).length).toBeGreaterThan(0);
});

it("keeps the first screen focused on an actionable conclusion", () => {
  render(
    <ResultAnalysisModule
      structuredDirections={[{
        ...directions[1],
        recommendation_level: "focus",
        motivation: "解决连续使用中的补充需求",
        purchase_chain: { before_use: "准备主品", using_main: "执行主要任务", using_candidate: "补充辅品" },
        assumptions: ["主品规格与辅品兼容"],
        deep_arguments: { user_rationale: "重复展示的深度依据" },
      }]}
      productTitleZh="主品中文标题"
    />
  );

  expect(screen.getAllByText("可进入测试").length).toBeGreaterThan(0);
  expect(screen.getAllByText("解决连续使用中的补充需求").length).toBeGreaterThan(0);
  expect(screen.getByText("购买链路")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "深度分析（点击展开）" })).toHaveAttribute("aria-expanded", "false");
});

it("renders source images and explicit image fallbacks", () => {
  const { rerender } = render(
    <ProductMedia
      src="https://images.example/main.jpg"
      alt="Pizza Cutter"
      emptyLabel="历史无图"
    />
  );
  const image = screen.getByRole("img", { name: "Pizza Cutter" });
  expect(image).toHaveAttribute("src", "https://images.example/main.jpg");
  fireEvent.error(image);
  expect(screen.getByText("图片加载失败")).toBeInTheDocument();

  rerender(<ProductMedia alt="Old product" emptyLabel="历史无图" />);
  expect(screen.getByText("历史无图")).toBeInTheDocument();
});

it("shows approved veto groups and traceable complementary evidence", async () => {
  const user = userEvent.setup();
  render(
    <JudgmentAnalysis
      sections={vetoSections}
      complementEvidence={complementEvidence}
    />
  );

  await user.click(screen.getByRole("button", { name: /Candidate Product/ }));

  expect(screen.getByText("否决审查")).toBeInTheDocument();
  expect(screen.getByText("未触发任何一票否决条件")).toBeInTheDocument();
  expect(screen.getByText("风险检查")).toBeInTheDocument();
  expect(screen.getAllByText("未触发")).toHaveLength(6);
  expect(screen.getByText("正向证据")).toBeInTheDocument();
  expect(screen.getByText("互补需求证据")).toBeInTheDocument();
  expect(screen.getByText("已验证")).toBeInTheDocument();
  expect(screen.getByText("抽样评论 20 条")).toBeInTheDocument();
  expect(screen.getByText("相关评论 3 条")).toBeInTheDocument();
  expect(screen.queryByText("False")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "查看证据原文" }));
  expect(
    screen.getByText("I need a matching holder to use this product properly.")
  ).toBeInTheDocument();
  expect(screen.getByText("我需要一个配套支架才能正常使用。")).toBeInTheDocument();
  expect(screen.getByText("明确表达配套需求")).toBeInTheDocument();
});

it("matches evidence when the judgment uses an unambiguous shortened product title", async () => {
  const user = userEvent.setup();
  const shortenedSections = vetoSections.map((section) => ({
    ...section,
    content: section.content.replaceAll(
      "Candidate Product",
      "Candidate Product Short"
    ),
  }));
  const sourceRecord = complementEvidence.per_b_product["Candidate Product"];
  const fullTitleEvidence: ComplementEvidencePayload = {
    per_b_product: {
      "Candidate Product Short Full Variant": {
        ...sourceRecord,
        product_title: "Candidate Product Short Full Variant",
      },
    },
  };

  render(
    <JudgmentAnalysis
      sections={shortenedSections}
      complementEvidence={fullTitleEvidence}
    />
  );

  await user.click(screen.getByRole("button", { name: /Candidate Product Short/ }));

  expect(screen.getByText("抽样评论 20 条")).toBeInTheDocument();
  expect(screen.queryByText("旧任务初判：暂未确认")).not.toBeInTheDocument();
});

it("does not attach evidence when a shortened product title is ambiguous", async () => {
  const user = userEvent.setup();
  const shortenedSections = vetoSections.map((section) => ({
    ...section,
    content: section.content.replaceAll(
      "Candidate Product",
      "Candidate Product Shared"
    ),
  }));
  const sourceRecord = complementEvidence.per_b_product["Candidate Product"];
  const ambiguousEvidence: ComplementEvidencePayload = {
    per_b_product: {
      "Candidate Product Shared Red": {
        ...sourceRecord,
        product_title: "Candidate Product Shared Red",
      },
      "Candidate Product Shared Blue": {
        ...sourceRecord,
        product_title: "Candidate Product Shared Blue",
      },
    },
  };

  render(
    <JudgmentAnalysis
      sections={shortenedSections}
      complementEvidence={ambiguousEvidence}
    />
  );

  await user.click(screen.getByRole("button", { name: /Candidate Product Shared/ }));

  expect(screen.getByText("旧任务初判：暂未确认")).toBeInTheDocument();
  expect(screen.queryByText("抽样评论 20 条")).not.toBeInTheDocument();
});

it("labels evidence-free historical G3 as an initial judgment", async () => {
  const user = userEvent.setup();
  render(<JudgmentAnalysis sections={vetoSections} />);

  await user.click(screen.getByRole("button", { name: /Candidate Product/ }));

  expect(screen.getByText("旧任务初判：暂未确认")).toBeInTheDocument();
  expect(screen.getByText("没有保存评论证据明细，建议重新运行验证")).toBeInTheDocument();
  expect(screen.queryByText(/抽样评论/)).not.toBeInTheDocument();
});

it("falls back to the next product image when the first image fails", () => {
  render(
    <ProductMedia
      src={["https://images.example/broken.jpg", "https://images.example/backup.jpg"]}
      alt="Pizza Cutter"
    />
  );

  const image = screen.getByRole("img", { name: "Pizza Cutter" });
  fireEvent.error(image);
  expect(screen.getByRole("img", { name: "Pizza Cutter" })).toHaveAttribute(
    "src",
    "https://images.example/backup.jpg"
  );
});

it("keeps old section-only results readable", () => {
  render(
    <ResultAnalysisModule
      sections={[{ title: "商品分析", content: "旧任务原始内容" }]}
    />
  );
  expect(screen.getByText("历史结果暂无结构化方向")).toBeInTheDocument();
  expect(screen.getByText("旧任务原始内容")).toBeInTheDocument();
});

it("shows a confirmed V2.1 zero-candidate conclusion", () => {
  render(
    <ResultAnalysisModule
      modelVersion="combination_model_v2.1"
      resultStatus="completed_no_qualified_candidates"
      resultMessage="分析已完成，未发现达到高粘性门槛的辅品，不建议为了凑数量强行组合。"
      auditOutcome="confirmed_no_candidates"
      rejectionSummary={{ food_blocked: 2, no_valid_relation: 1 }}
    />
  );

  expect(
    screen.getByText(/分析已完成，未发现达到高粘性门槛的辅品/)
  ).toBeInTheDocument();
  expect(screen.getByText("遗漏复核已完成")).toBeInTheDocument();
  expect(screen.getByText("food_blocked · 2")).toBeInTheDocument();
  expect(screen.queryByText("历史结果暂无结构化方向")).not.toBeInTheDocument();
});

it("shows a non-executable notice while preserving hold directions", () => {
  render(
    <ResultAnalysisModule
      modelVersion="combination_model_v2.1"
      resultStatus="completed_needs_evidence"
      resultMessage="发现潜在方向，但当前不可执行，请先补齐兼容、安全或商品类型证据。"
      structuredDirections={[
        {
          ...directions[0],
          execution_status: "hold",
          decision_action: "needs_evidence",
          hold_reasons: ["需要确认规格兼容"],
        },
      ]}
    />
  );

  expect(screen.getByText(/发现潜在方向，但当前不可执行/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /方向甲/ })).toBeInTheDocument();
});

it("keeps the explicit V2.0 historical empty-state copy", () => {
  render(
    <ResultAnalysisModule
      modelVersion="combination_model_v2.0"
      sections={[{ title: "商品分析", content: "旧任务原始内容" }]}
    />
  );

  expect(
    screen.getByText("历史 V2.0 快照，未保存结构化方向")
  ).toBeInTheDocument();
  expect(screen.queryByText(/未发现达到高粘性门槛/)).not.toBeInTheDocument();
});

it("keeps cross-review readable when structured directions are unavailable", () => {
  render(
    <ResultAnalysisModule
      sections={[{ title: "商品分析", content: "旧任务原始内容" }]}
      crossReview={{ gpt_reviews_deepseek: { raw: "旧任务交叉验证原文" } }}
    />
  );

  expect(screen.getByText("旧任务交叉验证原文")).toBeInTheDocument();
});

it("keeps on-demand search results isolated by direction", async () => {
  const user = userEvent.setup();
  render(<ResultAnalysisModule structuredDirections={directions} />);

  expect(screen.getByText("待核验")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "核验 Walmart" }));

  expect(await screen.findByText("平台已返回")).toBeInTheDocument();
  expect(screen.getByText("相似候选（未确认精准）")).toBeInTheDocument();
  expect(screen.getByText("Platform result for direction b")).toBeInTheDocument();
  expect(screen.queryByText("精准匹配")).not.toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: /方向甲/ }));
  expect(screen.getByText("待核验")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: /方向乙/ }));
  expect(screen.getByText("Platform result for direction b")).toBeInTheDocument();
});

it("does not reuse platform results when the same direction gets a different model query", async () => {
  const user = userEvent.setup();
  const sharedDirection = [{ ...directions[1], name: "同名方向", keywords: { en: "model one query" } }];
  const { rerender } = render(
    <ResultAnalysisModule structuredDirections={sharedDirection} />
  );

  await user.click(screen.getByRole("button", { name: "核验 Walmart" }));
  expect(await screen.findByText("Platform result for model one query")).toBeInTheDocument();

  rerender(
    <ResultAnalysisModule
      structuredDirections={[{ ...sharedDirection[0], keywords: { en: "model two query" } }]}
    />
  );

  expect(screen.getByText("待核验")).toBeInTheDocument();
  expect(screen.queryByText("Platform result for model one query")).not.toBeInTheDocument();
});

it("limits the evidence view to product, evidence, and strategy sections", async () => {
  const user = userEvent.setup();
  render(
    <ResultAnalysisModule
      structuredDirections={directions}
      sections={[
        { title: "商品分析", content: "保留商品内容" },
        { title: "证据表", content: "保留证据内容" },
        { title: "策略判断", content: "保留策略内容" },
        { title: "假设方向", content: "不要重复方向内容" },
        { title: "关键词包", content: "不要重复关键词内容" },
      ]}
    />
  );

  await user.click(screen.getByRole("tab", { name: "商品与证据" }));
  expect(screen.getByRole("button", { name: "商品分析" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "证据表" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "策略判断" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "假设方向" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "关键词包" })).not.toBeInTheDocument();
});

it("shows empty and failed Walmart searches distinctly", async () => {
  const user = userEvent.setup();
  server.use(
    http.post(API_BASE + "/api/v1/search", () =>
      HttpResponse.json({ results: [] })
    )
  );
  const { unmount } = render(
    <ResultAnalysisModule structuredDirections={directions} />
  );
  await user.click(screen.getByRole("button", { name: "核验 Walmart" }));
  expect(await screen.findByText("无结果")).toBeInTheDocument();
  unmount();

  server.use(
    http.post(API_BASE + "/api/v1/search", () =>
      HttpResponse.json(
        { detail: { code: "SEARCH_FAILED", message: "network down" } },
        { status: 502 }
      )
    )
  );
  render(<ResultAnalysisModule structuredDirections={directions} />);
  await user.click(screen.getByRole("button", { name: "核验 Walmart" }));
  expect(await screen.findByText("搜索失败")).toBeInTheDocument();
  expect(screen.getByText("network down")).toBeInTheDocument();
});

it("copies a legacy generic keyword without presenting it as Amazon precise", async () => {
  const user = userEvent.setup();
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  render(<ResultAnalysisModule structuredDirections={directions} />);

  await user.click(screen.getByRole("button", { name: "复制通用词" }));
  expect(writeText).toHaveBeenCalledWith("direction b");
  expect(screen.queryByRole("link", { name: "打开 Amazon 搜索" })).not.toBeInTheDocument();
});

it("shows each auxiliary product image and id in the row and drawer", async () => {
  const user = userEvent.setup();
  render(
    <JudgmentAnalysis
      sections={vetoSections}
      bProducts={[{
        title: "Candidate Product",
        product_id: "456",
        product_url: "https://www.walmart.com/ip/candidate/456",
        product_image: "https://images.example/candidate.jpg",
      }]}
    />
  );

  expect(screen.getByRole("img", { name: "Candidate Product" })).toHaveAttribute(
    "src", "https://images.example/candidate.jpg"
  );
  expect(screen.getByText("商品 ID：456")).toBeVisible();
  await user.click(screen.getByRole("button", { name: /Candidate Product/ }));
  expect(screen.getAllByRole("img", { name: "Candidate Product" })).toHaveLength(2);
  expect(screen.getAllByText("商品 ID：456")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "打开商品" })).toHaveAttribute(
    "href", "https://www.walmart.com/ip/candidate/456"
  );
});

it("shows separate keyword accordions with precise Amazon actions", async () => {
  const user = userEvent.setup();
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
  render(<ResultAnalysisModule structuredDirections={[{
    ...directions[0],
    keywords: {
      amazon: "small torpedo level",
      en: "level tool for furniture",
    },
  }]} />);

  expect(screen.getByText("Amazon 精准关键词")).toBeInTheDocument();
  expect(screen.getByText("英文通用关键词")).toBeInTheDocument();
  expect(screen.queryByText(/amazon:.*en:/i)).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "打开 Amazon 搜索" })).toHaveAttribute(
    "href",
    "https://www.amazon.com/s?k=small%20torpedo%20level"
  );
  await user.click(screen.getByRole("button", { name: "复制精准词" }));
  expect(writeText).toHaveBeenCalledWith("small torpedo level");
});

it("renders the V2 scorecard with evidence, gates, and consumer chain", () => {
  const direction: StructuredDirection = {
    name: "Matching Ink (Printer Ink)",
    score: 89,
    type: "spec_compatibility",
    motivation: "replacement",
    evidence_level: "E3",
    cost: "$4",
    strategy: "$19.99",
    stickiness: "high",
    model_version: "combination_model_v2.0",
    canonical_name: "printer ink",
    primary_relation: "spec_compatibility",
    lifecycle_stage: "use",
    purchase_chain: {
      before_use: "Printer runs low",
      using_main: "Print document",
      using_candidate: "Replace cartridge",
    },
    consistency: {
      user: { score: 5, reason: "Same owner" },
      scenario: { score: 5, reason: "Same task" },
      lifecycle: { score: 5, reason: "Immediate" },
      mental: { score: 4, reason: "Expected pairing" },
    },
    consumer_simulation: "A",
    consumer_simulation_reason: "Natural purchase",
    score_breakdown: {
      relation_strength: 30,
      lifecycle_connection: 20,
      repeat_value: 15,
      function_gain: 10,
      mental_copurchase: 8,
      market_evidence: 8,
      user_scene: 5,
    },
    raw_score: 96,
    score_cap: 89,
    final_score: 89,
    recommendation_level: "focus",
    evidence: {
      level: "E3",
      market: {
        query: "printer printer ink",
        source_urls: ["https://walmart.com/ip/1"],
        verified_at: "2026-07-29T00:00:00Z",
      },
    },
    risk_analysis: "Confirm cartridge model",
    missing_evidence: ["Transaction data"],
  };

  render(<StickinessScorecard direction={direction} />);

  expect(screen.getByText("V2.0 全品类购买链路")).toBeInTheDocument();
  expect(screen.getByText("原始分")).toBeInTheDocument();
  expect(screen.getByText("96")).toBeInTheDocument();
  expect(screen.getByText("分数上限")).toBeInTheDocument();
  expect(screen.getByText("消费者购买链路")).toBeInTheDocument();
  expect(screen.getByText("Printer runs low")).toBeInTheDocument();
  expect(screen.getByText("用户一致")).toBeInTheDocument();
  expect(screen.getByText("A · 自然一起购买")).toBeInTheDocument();
  expect(screen.getByText("Confirm cartridge model")).toBeInTheDocument();
  expect(screen.getByText(/Transaction data/)).toBeInTheDocument();
});

it("renders link-driven filter, reasons, and extended scenarios without inline JSON", () => {
  const direction = {
    name: "打印机墨盒 (Printer Ink Cartridge)", score: 96, type: "required_dependency",
    motivation: "replacement", evidence_level: "E1", cost: "-", strategy: "-",
    stickiness: "high", model_version: "combination_model_v2.0",
    food_filter_status: "allowed", food_filter_reason: "不可食用耗材",
    relation_reasons: ["主品工作必须使用墨盒"],
    extended_scenarios: [{ name: "家庭办公", assumption: "主品用于家庭办公", reason: "连续打印任务" }],
    purchase_chain: { before: "准备文件", primary_use: "打印", auxiliary_use: "补充墨盒" },
  } as StructuredDirection;
  render(<StickinessScorecard direction={direction} />);
  expect(screen.getByText("产品关系依据")).toBeInTheDocument();
  expect(screen.getByText("已通过：非食品产品")).toBeInTheDocument();
  expect(screen.getByText("拓展场景")).toBeInTheDocument();
  expect(screen.getByText("家庭办公")).toBeInTheDocument();
  expect(screen.queryByText(/\"purchase_chain\"/)).not.toBeInTheDocument();
});

it("shows the scorecard for legacy directions and labels purchase-chain steps", () => {
  const direction = {
    name: "Legacy Ink", score: 80, type: "replacement", motivation: "replacement",
    evidence_level: "E1", cost: "-", strategy: "-", stickiness: "high",
    purchase_chain: { before_use: "墨水不足", using_main: "打印文件", using_candidate: "更换墨盒" },
  } as StructuredDirection;
  render(<StickinessScorecard direction={direction} />);
  expect(screen.getByText("使用前（before_use）")).toBeInTheDocument();
  expect(screen.getByText("使用辅品（using_candidate）")).toBeInTheDocument();
  expect(screen.getByText("待验证：未确认产品类型")).toBeInTheDocument();
});
