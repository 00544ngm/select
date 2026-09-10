import { expect, test, type Page } from "@playwright/test";

const JOB_ID = "ff03dd2a-7a22-4c79-9d36-e62f150b37fa";
const imageUrl = "https://images.example/pizza-cutter.jpg";
const resultImageUrl = "https://images.example/pastry-mat.jpg";
const tinyPng = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=", "base64");

const directions = [
  {
    name: "耐热披萨手套 (Heat Resistant Pizza Gloves)", score: 80, type: "便利型",
    motivation: "便利闭环", evidence_level: "3", cost: "¥8", strategy: "$18.97", stickiness: "中",
    keywords: { en: "heat resistant pizza gloves" }, deep_arguments: { user_rationale: "避免烫伤" },
  },
  {
    name: "防滑披萨切割垫 (Non-Slip Pizza Cutting Mat)", score: 91, type: "低成本价值附加",
    motivation: "痛点解决", motivation_evidence: "披萨切割时容易滑动", evidence_level: "2",
    cost: "¥3-6", strategy: "$16.97", stickiness: "高",
    keywords: { en: "non slip pizza cutting mat" }, deep_arguments: { user_rationale: "稳定披萨" },
    delivery_checklist: { bundling_display: "展示防滑前后对比" },
  },
];

const jobDetail = {
  id: JOB_ID, name: "Pizza accessory research", mode: "hypothesis", status: "completed", progress: 100,
  error_code: null, error_message: null, retry_of_id: null,
  created_at: "2026-07-27T13:37:06Z", updated_at: "2026-07-27T14:09:23Z",
  request_payload: { url: "https://www.walmart.com/ip/123" },
  result_payload: {
    grade: "B+", score: 77.6, product_title: "BUSATIA Blade Guard Pizza Cutter Rocker",
    product_url: "https://www.walmart.com/ip/123", product_images: [imageUrl], product_price: "$10.92",
    product_rating: "4.7", product_review_count: "414", keyword_pack: ["pizza cutter accessories"],
    structured_directions: directions,
    sections: [{ title: "商品分析", content: "原始商品分析证据" }],
  },
};

async function mockApis(page: Page) {
  await page.route("https://images.example/**", (route) => route.fulfill({ status: 200, contentType: "image/png", body: tinyPng }));
  await page.route(`**/api/v1/jobs/${JOB_ID}`, (route) => route.fulfill({ json: jobDetail }));
  await page.route(/\/api\/v1\/jobs\?.*$/, (route) => route.fulfill({ json: {
    items: [{
      id: JOB_ID, name: "Pizza accessory research", mode: "hypothesis", status: "completed", progress: 100,
      error_code: null, error_message: null, retry_of_id: null,
      created_at: "2026-07-27T13:37:06Z", updated_at: "2026-07-27T14:09:23Z",
      grade: "B+", score: 77.6, product_title: "BUSATIA Blade Guard Pizza Cutter Rocker", product_image: null,
      top_direction_name: "防滑披萨切割垫 (Non-Slip Pizza Cutting Mat)",
      top_direction_keywords: { en: "non slip pizza cutting mat" }, top_direction_score: 91,
      top_direction_type: "低成本价值附加",
    }], total: 1, page: 1, page_size: 20,
  } }));
  await page.route("**/api/v1/search", (route) => route.fulfill({ json: { results: [{
    title: "Silicone Baking Pastry Dough Mat", url: "https://www.walmart.com/ip/result/1", price: "$9.99",
    rating: "4.5", review_count: "20", image: resultImageUrl,
  }] } }));
}

async function expectNoHorizontalOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
}

test.beforeEach(async ({ page }) => mockApis(page));

test("uses the result workbench and verifies platform candidates on demand", async ({ page }, testInfo) => {
  await page.goto(`/jobs/${JOB_ID}`);
  await page.getByRole("button", { name: "方案分析" }).click();

  await expect(page.getByRole("img", { name: "BUSATIA Blade Guard Pizza Cutter Rocker" })).toBeVisible();
  await expect(page.getByRole("button", { name: /防滑披萨切割垫，评分 91/ })).toHaveAttribute("aria-current", "true");
  await expect(page.getByText("non slip pizza cutting mat").first()).toBeVisible();
  await expect(page.getByText("¥3-6")).toBeVisible();

  await page.getByRole("button", { name: "核验 Walmart" }).click();
  await expect(page.getByText("平台已返回")).toBeVisible();
  await expect(page.getByText("Silicone Baking Pastry Dough Mat")).toBeVisible();
  await expect(page.getByRole("img", { name: "Silicone Baking Pastry Dough Mat" })).toBeVisible();
  await expect(page.getByText("相似候选（未确认精准）")).toBeVisible();
  await expect(page.getByText("精准匹配")).toHaveCount(0);

  await page.getByRole("button", { name: /耐热披萨手套，评分 80/ }).click();
  const detailHeading = page.getByRole("heading", { name: "耐热披萨手套" });
  await expect(detailHeading).toBeVisible();
  const headingBox = await detailHeading.boundingBox();
  const viewport = page.viewportSize();
  expect(headingBox).not.toBeNull();
  expect(headingBox!.width).toBeGreaterThan(0);
  expect(headingBox!.x).toBeGreaterThanOrEqual(0);
  expect(headingBox!.x + headingBox!.width).toBeLessThanOrEqual(viewport!.width);
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath(`workbench-${testInfo.project.name}.png`), fullPage: true });
});

test("shows Beijing match history and saved direction summary", async ({ page }, testInfo) => {
  await page.goto("/history");

  await expect(page.getByText("21:37 开始")).toBeVisible();
  await expect(page.getByText("22:09 完成")).toBeVisible();
  await expect(page.getByText("32分17秒")).toBeVisible();
  await expect(page.getByText("BUSATIA Blade Guard Pizza Cutter Rocker")).toBeVisible();
  await expect(page.getByText("防滑披萨切割垫")).toBeVisible();
  await expect(page.getByText("方向分 91")).toBeVisible();
  await expect(page.getByText("综合 77.6")).toBeVisible();
  await expect(page.getByText("历史无图")).toBeVisible();
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path: testInfo.outputPath(`history-${testInfo.project.name}.png`), fullPage: true });
});
