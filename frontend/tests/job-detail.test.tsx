import { it, expect, vi, beforeAll, afterAll, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import JobDetailPage from "@/app/jobs/[jobId]/page";

const API_BASE = "http://localhost:8000";

vi.stubEnv("NEXT_PUBLIC_API_BASE", API_BASE);

const mockJobId = vi.fn(() => "job-123");
const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ jobId: mockJobId() }),
  useRouter: () => ({ push: pushMock }),
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchOnWindowFocus: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

const handlers = [
  http.get(`${API_BASE}/api/v1/settings/providers`, () => HttpResponse.json([])),
  http.get(`${API_BASE}/api/v1/jobs/:jobId`, ({ params }) => {
    const { jobId } = params;
    if (jobId === "not-found") {
      return HttpResponse.json(
        { detail: { code: "NOT_FOUND", message: "任务不存在", retryable: false } },
        { status: 404 }
      );
    }
    return HttpResponse.json({
      id: jobId,
      mode: "hypothesis",
      status: "queued",
      progress: 0,
      error_code: null,
      error_message: null,
      retry_of_id: null,
      created_at: "2026-07-15T12:00:00Z",
      updated_at: "2026-07-15T12:00:00Z",
      request_payload: { url: "https://walmart.com/ip/123" },
      result_payload: null,
    });
  }),
];

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
beforeEach(() => {
  server.resetHandlers();
  pushMock.mockReset();
});

it("keeps one wrapper-level product review visible across model switches", async () => {
  const user = userEvent.setup();
  server.use(http.get(`${API_BASE}/api/v1/jobs/:jobId`, () => HttpResponse.json({
    id: "wrapped-review", name: "Wrapped review", mode: "hypothesis", status: "completed", progress: 100,
    error_code: null, error_message: null, retry_of_id: null,
    created_at: "2026-08-01T00:00:00Z", updated_at: "2026-08-01T00:01:00Z", request_payload: {},
    result_payload: {
      product_type_review: {
        status: "confirmed_non_food", source: "rule", action: "continue",
        reason: "商品标题与属性均表明为工具", evidence: [{ source_field: "title", verbatim_quote: "Steel tool" }],
      },
      models: {
        gpt: { product_title: "Primary result", score: 88, structured_directions: [] },
        deepseek: { product_title: "Secondary result", score: 77, structured_directions: [] },
      },
    },
  })));
  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findAllByText("确认非食品")).toHaveLength(1);
  expect(screen.getAllByText("规则判断")).toHaveLength(1);
  expect(screen.getAllByText("商品标题与属性均表明为工具")).toHaveLength(1);
  expect(screen.getAllByText("允许继续分析")).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "DeepSeek" }));
  expect(screen.getAllByText("确认非食品")).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: /OpenAI/ }));
  expect(screen.getAllByText("确认非食品")).toHaveLength(1);
  await user.click(screen.getByRole("button", { name: "方案分析" }));
  expect(screen.getAllByText("确认非食品")).toHaveLength(1);
});

it("shows queued status with progress indicator", async () => {
  const user = userEvent.setup();
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("排队中，等待执行...")).toBeInTheDocument();
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0");
  await user.click(screen.getByRole("button", { name: "返回工作台" }));
  expect(pushMock).toHaveBeenCalledWith("/");
});

it("shows running status with progress percentage", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "running",
        progress: 45,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:00Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: null,
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("45%")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "返回工作台" })).toBeInTheDocument();
});

it("shows Walmart verification guidance while the task remains running", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-walmart-verification",
        mode: "hypothesis",
        status: "running",
        progress: 5,
        error_code: "WALMART_CAPTCHA_REQUIRED",
        error_message: "已打开 Walmart 验证窗口",
        retry_of_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: null,
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("等待 Walmart 人工验证")).toBeInTheDocument();
  expect(screen.getByText(/请完成验证，不要关闭窗口/)).toBeInTheDocument();
  expect(screen.getByText(/当前尚未调用模型，不会消耗 Token/)).toBeInTheDocument();
});

it("shows dedicated guidance when Walmart verification times out", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-walmart-timeout",
        mode: "hypothesis",
        status: "failed",
        progress: 5,
        error_code: "WALMART_CAPTCHA_TIMEOUT",
        error_message: "Walmart verification timed out",
        retry_of_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: null,
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("Walmart 人工验证未完成")).toBeInTheDocument();
  expect(screen.getByText(/验证成功前不会调用模型，也不会消耗 Token/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重新提交" })).toBeInTheDocument();
});

it("shows elapsed background guidance for a running gpt-5.5 report", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-slow-model",
        mode: "hypothesis",
        status: "running",
        progress: 35,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: new Date(Date.now() - 138_000).toISOString(),
        updated_at: new Date().toISOString(),
        request_payload: {
          url: "https://walmart.com/ip/123",
          provider: "openai",
          model: "gpt-5.5-2026-04-23",
        },
        result_payload: null,
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText(/模型正在生成完整报告，已等待 2 分/)).toBeInTheDocument();
  expect(screen.getByText("慢模型最长等待 10 分钟，超时不会自动重试。")).toBeInTheDocument();
  expect(screen.getByText("返回后任务继续在后台运行，可在历史记录查看。")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "返回工作台" })).toBeEnabled();
});

it("does not show the ten-minute slow-model message for gpt-5.4", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-normal-model",
        mode: "hypothesis",
        status: "running",
        progress: 35,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: new Date(Date.now() - 10_000).toISOString(),
        updated_at: new Date().toISOString(),
        request_payload: {
          url: "https://walmart.com/ip/123",
          provider: "openai",
          model: "gpt-5.4",
        },
        result_payload: null,
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText(/模型正在生成完整报告，已等待/)).toBeInTheDocument();
  expect(screen.queryByText("慢模型最长等待 10 分钟，超时不会自动重试。")).not.toBeInTheDocument();
});

it("shows product id, translated title, original title and product image", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "running",
        progress: 45,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:00Z",
        product_id: "123456789",
        product_title: "Portable Hanging Scale",
        product_title_zh: "便携式行李秤",
        product_image: "https://images.example/main.jpg",
        request_payload: { url: "https://walmart.com/ip/123456789" },
        result_payload: {
          product_id: "123456789",
          product_title: "Portable Hanging Scale",
          product_title_zh: "便携式行李秤",
          product_images: ["https://images.example/main.jpg"],
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("123456789")).toBeInTheDocument();
  expect(screen.getByText("便携式行李秤")).toBeInTheDocument();
  expect(screen.getByText("Portable Hanging Scale")).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Portable Hanging Scale" })).toHaveAttribute(
    "src",
    "https://images.example/main.jpg"
  );
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "45");
});

it("shows completed result with grade and score", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:01Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: {
          grade: "A",
          score: 85,
          directions: "Test directions",
        },
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect((await screen.findAllByText("A")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("85")).length).toBeGreaterThan(0);
});

it("shows expandable result sections", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "judgment",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:01Z",
        request_payload: { a_url: "https://walmart.com/ip/123", b_urls: ["https://walmart.com/ip/456"] },
        result_payload: {
          sections: [
            { title: "价格对比", content: "A商品价格更低" },
            { title: "评价对比", content: "B商品评价更好" },
          ],
        },
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("价格对比")).toBeInTheDocument();
});

it("shows error message for failed jobs", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "failed",
        progress: 30,
        error_code: "SCRAPE_FAILED",
        error_message: "无法抓取商品页面，请确认链接可访问",
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:02Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: null,
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("无法抓取商品页面，请确认链接可访问")).toBeInTheDocument();
});

it("shows retry button for failed jobs", async () => {
  const user = userEvent.setup();
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "failed",
        progress: 30,
        error_code: "SCRAPE_FAILED",
        error_message: "无法抓取商品页面，请确认链接可访问",
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:02Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: null,
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByRole("button", { name: /重新提交/i })).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "返回工作台" }));
  expect(pushMock).toHaveBeenCalledWith("/");
});

it("shows not found message for unknown jobs", async () => {
  mockJobId.mockReturnValue("not-found");
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText(/任务不存在/i)).toBeInTheDocument();
});

it("provides JSON and Excel download buttons for completed jobs", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:01Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: { grade: "A", score: 85 },
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByRole("button", { name: /下载 JSON/i })).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: /下载 Excel/i })).toBeInTheDocument();
});

it("shows cross-review text inside the workbench without rewriting characters", async () => {
  mockJobId.mockReturnValue("job-123");
  const user = userEvent.setup();
  const raw = [
    "## 合理之处",
    "",
    "### 核心场景",
    "",
    "正文包含 **评论证据**。",
    "",
    "- 风险一",
    "- 风险二",
    "",
    "| 搭配方向 | 判断 |",
    "| --- | --- |",
    "| 笔 | 合理 |",
  ].join("\n");
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:01Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: {
          models: {
            gpt: {
              grade: "A",
              score: 85,
              structured_directions: [{ name: "方向甲", score: 85 }],
            },
            deepseek: {
              grade: "B",
              score: 80,
              structured_directions: [{ name: "方向乙", score: 80 }],
            },
          },
          cross_review: {
            status: "completed",
            reviewers: [
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
            ],
            results: { gpt_reviews_deepseek: { raw } },
          },
        },
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });

  await user.click(await screen.findByRole("button", { name: "方案分析" }));
  await user.click(screen.getByRole("tab", { name: "交叉验证" }));

  expect(
    screen.getByRole("button", {
      name: /DeepSeek（deepseek-v4-pro）评审 Claude（claude-opus-5）/,
    }),
  ).toBeInTheDocument();
  expect(screen.getByText("DeepSeek · OpenAI 兼容 · deepseek-v4-pro")).toBeInTheDocument();
  expect(screen.getByText("Claude · Anthropic 兼容 · claude-opus-5")).toBeInTheDocument();
  expect(screen.queryByText(/reviewer_a|reviewer_b/)).not.toBeInTheDocument();

  expect(
    screen.getByRole("heading", { name: "合理之处", level: 2 })
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "核心场景", level: 3 })
  ).toBeInTheDocument();
  expect(screen.getByRole("list")).toBeInTheDocument();
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.getByText("评论证据").tagName).toBe("STRONG");
  expect(screen.queryByText("## 合理之处")).not.toBeInTheDocument();
  expect(
    screen.queryByTestId("cross-review-raw-gpt_reviews_deepseek")
  ).not.toBeInTheDocument();
  await user.click(screen.getByText("查看模型原文"));
  expect(
    screen.getByTestId("cross-review-raw-gpt_reviews_deepseek").textContent
  ).toBe(raw);
  expect(screen.getAllByText("交叉验证结果")).toHaveLength(1);
});

it("makes the cross-review action visually prominent before it is run", async () => {
  mockJobId.mockReturnValue("job-cross-action");
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-cross-action",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-30T02:00:00Z",
        updated_at: "2026-07-30T02:03:00Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: {
          models: {
            gpt: { grade: "A", score: 85, structured_directions: [] },
            deepseek: { grade: "A", score: 84, structured_directions: [] },
          },
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });
  const button = await screen.findByRole("button", { name: /交叉验证：GPT 与 DeepSeek 互评/ });
  expect(button).toHaveClass("bg-primary");
  expect(screen.getByText("比较两个模型的结论与评分差异")).toBeInTheDocument();
});

it.skip("offers both CatToken protocols for cross-review and hides provider-level failures", async () => {
  mockJobId.mockReturnValue("job-cattoken-cross-review");
  const user = userEvent.setup();
  const provider = (overrides: Record<string, unknown>) => ({
    slug: "cattoken",
    api_protocol: "openai",
    display_name: "CatToken OpenAI",
    role: "primary",
    base_url: "https://www.cattoken.vip/v1",
    default_model: "gpt-5.5",
    supported_models: ["gpt-5.5"],
    is_enabled: true,
    configured: true,
    masked_api_key: "synthetic-mask",
    last_test_status: "success",
    last_tested_at: null,
    last_test_message: null,
    updated_at: null,
    model_options: [{
      provider: "cattoken",
      provider_display_name: "CatToken OpenAI",
      api_protocol: "openai",
      model: "gpt-5.5",
      is_default: true,
      is_enabled: true,
      test_status: "success",
      tested_at: null,
      test_message: null,
    }],
    ...overrides,
  });
  server.use(
    http.get(`${API_BASE}/api/v1/settings/providers`, () =>
      HttpResponse.json([
        provider({}),
        provider({
          slug: "cattoken_claude",
          api_protocol: "anthropic",
          display_name: "CatToken Claude",
          base_url: "https://www.cattoken.vip",
          default_model: "claude-sonnet-4-6",
          supported_models: ["claude-sonnet-4-6"],
          model_options: [{
            provider: "cattoken_claude",
            provider_display_name: "CatToken Claude",
            api_protocol: "anthropic",
            model: "claude-sonnet-4-6",
            is_default: true,
            is_enabled: true,
            test_status: "success",
            tested_at: null,
            test_message: null,
          }],
        }),
        provider({
          slug: "custom",
          display_name: "Residual Unconfigured Provider",
          configured: false,
          last_test_status: "success",
          model_options: [{
            provider: "custom",
            provider_display_name: "Residual Unconfigured Provider",
            api_protocol: "openai",
            model: "unconfigured-success-model",
            is_default: true,
            is_enabled: true,
            test_status: "success",
            tested_at: null,
            test_message: null,
          }],
        }),
        provider({
          slug: "openai",
          display_name: "Residual Failed Provider",
          configured: true,
          last_test_status: "failed",
          model_options: [{
            provider: "openai",
            provider_display_name: "Residual Failed Provider",
            api_protocol: "openai",
            model: "failed-success-model",
            is_default: true,
            is_enabled: true,
            test_status: "success",
            tested_at: null,
            test_message: null,
          }],
        }),
      ])
    ),
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-cattoken-cross-review",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-30T02:00:00Z",
        updated_at: "2026-07-30T02:03:00Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: {
          models: {
            gpt: { grade: "A", score: 85, structured_directions: [] },
            deepseek: { grade: "A", score: 84, structured_directions: [] },
          },
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });
  const reviewerA = await screen.findByRole("combobox", { name: "评审模型 A" });
  const reviewerB = screen.getByRole("combobox", { name: "评审模型 B" });
  expect(screen.getAllByRole("option", { name: "CatToken OpenAI · gpt-5.5" })).toHaveLength(2);
  expect(screen.getAllByRole("option", { name: "CatToken Claude · claude-sonnet-4-6" })).toHaveLength(2);
  for (const reviewer of [reviewerA, reviewerB]) {
    expect(within(reviewer).queryByRole("option", { name: /Residual Unconfigured Provider/ })).not.toBeInTheDocument();
    expect(within(reviewer).queryByRole("option", { name: /Residual Failed Provider/ })).not.toBeInTheDocument();
  }
  await user.selectOptions(reviewerA, "cattoken:gpt-5.5");
  await user.selectOptions(reviewerB, "cattoken_claude:claude-sonnet-4-6");
  expect(reviewerA).toHaveValue("cattoken:gpt-5.5");
  expect(reviewerB).toHaveValue("cattoken_claude:claude-sonnet-4-6");
});

it.skip("revalidates cross-review selections when the verified model catalog refreshes", async () => {
  mockJobId.mockReturnValue("job-refresh-cross-review");
  const user = userEvent.setup();
  const option = (provider: string, displayName: string, model: string, apiProtocol = "openai") => ({
    provider,
    provider_display_name: displayName,
    api_protocol: apiProtocol,
    model,
    is_default: true,
    is_enabled: true,
    test_status: "success",
    tested_at: null,
    test_message: null,
  });
  const provider = (slug: string, displayName: string, model: string, apiProtocol = "openai") => ({
    slug,
    api_protocol: apiProtocol,
    display_name: displayName,
    role: "primary",
    base_url: "https://synthetic.invalid",
    default_model: model,
    supported_models: [model],
    is_enabled: true,
    configured: true,
    masked_api_key: "synthetic-mask",
    last_test_status: "success",
    last_tested_at: null,
    last_test_message: null,
    updated_at: null,
    model_options: [option(slug, displayName, model, apiProtocol)],
  });
  const catOpenAI = provider("cattoken", "CatToken OpenAI", "gpt-5.5");
  const catClaude = provider("cattoken_claude", "CatToken Claude", "claude-sonnet-4-6", "anthropic");
  const fallback = provider("custom", "Fallback Reviewer", "fallback-model", "anthropic");
  let currentProviders = [catOpenAI, catClaude, fallback];
  const postedReviews: Array<Record<string, unknown>> = [];
  server.use(
    http.get(`${API_BASE}/api/v1/settings/providers`, () => HttpResponse.json(currentProviders)),
    http.post(`${API_BASE}/api/v1/jobs/:jobId/cross-review`, async ({ request }) => {
      postedReviews.push(await request.json() as Record<string, unknown>);
      return HttpResponse.json({ status: "queued" });
    }),
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-refresh-cross-review",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-30T02:00:00Z",
        updated_at: "2026-07-30T02:03:00Z",
        request_payload: { url: "https://walmart.com/ip/123" },
        result_payload: {
          models: {
            gpt: { grade: "A", score: 85, structured_directions: [] },
            deepseek: { grade: "A", score: 84, structured_directions: [] },
          },
        },
      })
    )
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  render(<JobDetailPage />, { wrapper: Wrapper });
  const reviewerA = await screen.findByRole("combobox", { name: "评审模型 A" });
  const reviewerB = screen.getByRole("combobox", { name: "评审模型 B" });
  await user.selectOptions(reviewerA, "cattoken:gpt-5.5");
  await user.selectOptions(reviewerB, "cattoken_claude:claude-sonnet-4-6");

  currentProviders = [catOpenAI, fallback];
  await queryClient.invalidateQueries({ queryKey: ["providers", "cross-review"] });
  await waitFor(() => expect(reviewerB).toHaveValue("custom:fallback-model"));
  await user.click(screen.getByRole("button", { name: /\u5f00\u59cb\u4ea4\u53c9\u9a8c\u8bc1/ }));
  await waitFor(() => expect(postedReviews).toHaveLength(1));
  expect(postedReviews[0]).toMatchObject({
    reviewer_a: { provider: "cattoken", model: "gpt-5.5" },
    reviewer_b: { provider: "custom", model: "fallback-model" },
  });

  currentProviders = [catOpenAI];
  await queryClient.invalidateQueries({ queryKey: ["providers", "cross-review"] });
  await waitFor(() => expect(reviewerB).toHaveValue(""));
  expect(screen.getByRole("button", { name: /\u5f00\u59cb\u4ea4\u53c9\u9a8c\u8bc1/ })).toBeDisabled();
  expect(postedReviews).toHaveLength(1);
});

it("keeps judgment cross-review visible in the analysis view", async () => {
  mockJobId.mockReturnValue("job-123");
  const user = userEvent.setup();
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-123",
        mode: "judgment",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:01Z",
        request_payload: { a_url: "https://walmart.com/ip/123", b_urls: ["https://walmart.com/ip/456"] },
        result_payload: {
          models: {
            gpt: { mode: "judgment", grade: "A", score: 85, sections: [{ title: "裁决", content: "GPT 裁决" }] },
            deepseek: { mode: "judgment", grade: "B", score: 80, sections: [{ title: "裁决", content: "DeepSeek 裁决" }] },
          },
          cross_review: {
            gpt_reviews_deepseek: { raw: "Judgment 交叉验证原文" },
          },
        },
      })
    )
  );
  render(<JobDetailPage />, { wrapper: createWrapper() });

  await user.click(await screen.findByRole("button", { name: "方案分析" }));

  expect(screen.getByText("Judgment 交叉验证原文")).toBeInTheDocument();
});

it("shows the persisted V2.1 reliability summary for the active model", async () => {
  mockJobId.mockReturnValue("job-reliability");
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-reliability",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-30T02:00:00Z",
        updated_at: "2026-07-30T02:03:00Z",
        request_payload: {
          url: "https://walmart.com/ip/123",
          provider: "custom",
          model: "claude-fable-5",
          expected_model_version: "combination_model_v2.1",
        },
        result_payload: {
          mode: "hypothesis",
          model_version: "combination_model_v2.1",
          provider: "custom",
          provider_model: "claude-fable-5",
          result_status: "completed_needs_evidence",
          result_message: "发现潜在方向，但当前不可执行，请先补齐兼容、安全或商品类型证据。",
          raw_direction_count: 3,
          qualified_direction_count: 0,
          hold_direction_count: 2,
          rejected_direction_count: 1,
          structured_directions: [],
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("结果可靠性")).toBeInTheDocument();
  expect(screen.getByText("combination_model_v2.1")).toBeInTheDocument();
  expect(screen.getByText("自定义 Anthropic · claude-fable-5")).toBeInTheDocument();
  expect(screen.getByText("job-reliability")).toBeInTheDocument();
  expect(screen.getByLabelText("待补证据 2")).toBeInTheDocument();
  expect(screen.getByLabelText("已淘汰 1")).toBeInTheDocument();
});

it.each([
  ["cattoken", "gpt-5.5", "CatToken OpenAI · gpt-5.5"],
  ["cattoken_claude", "claude-sonnet-4-6", "CatToken Claude · claude-sonnet-4-6"],
])("renders the persisted %s provider identity without rewriting history", async (provider, model, label) => {
  mockJobId.mockReturnValue(`job-${provider}-identity`);
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: `job-${provider}-identity`,
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-30T02:00:00Z",
        updated_at: "2026-07-30T02:03:00Z",
        request_payload: { provider, model },
        result_payload: {
          model_version: "combination_model_v2.1",
          provider,
          provider_model: model,
          result_status: "completed_no_qualified_candidates",
          qualified_direction_count: 0,
          hold_direction_count: 0,
          rejected_direction_count: 1,
          structured_directions: [],
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });
  expect(await screen.findByText(label)).toBeInTheDocument();
});

it("updates persisted reliability identity and counts when switching dual models", async () => {
  mockJobId.mockReturnValue("job-dual-reliability");
  const user = userEvent.setup();
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-dual-reliability",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-30T02:00:00Z",
        updated_at: "2026-07-30T02:03:00Z",
        request_payload: { provider: "custom", model: "claude-primary" },
        result_payload: {
          models: {
            gpt: {
              model_version: "combination_model_v2.1",
              provider: "custom",
              provider_model: "claude-primary",
              result_status: "completed_with_qualified_candidates",
              qualified_direction_count: 1,
              hold_direction_count: 0,
              rejected_direction_count: 2,
              structured_directions: [],
            },
            deepseek: {
              model_version: "combination_model_v2.1",
              provider: "deepseek",
              provider_model: "deepseek-reasoner",
              result_status: "completed_needs_evidence",
              qualified_direction_count: 0,
              hold_direction_count: 3,
              rejected_direction_count: 4,
              structured_directions: [],
            },
          },
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("自定义 Anthropic · claude-primary")).toBeInTheDocument();
  expect(screen.getByLabelText("合格 1")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "DeepSeek" }));
  expect(screen.getByText("DeepSeek · deepseek-reasoner")).toBeInTheDocument();
  expect(screen.getByLabelText("待补证据 3")).toBeInTheDocument();
  expect(screen.getByLabelText("已淘汰 4")).toBeInTheDocument();
  expect(screen.queryByText("自定义 Anthropic · claude-primary")).not.toBeInTheDocument();
});

it("marks missing V2.0 reliability identity and counts as not recorded", async () => {
  mockJobId.mockReturnValue("job-v20-history");
  server.use(
    http.get(`${API_BASE}/api/v1/jobs/:jobId`, () =>
      HttpResponse.json({
        id: "job-v20-history",
        mode: "hypothesis",
        status: "completed",
        progress: 100,
        error_code: null,
        error_message: null,
        retry_of_id: null,
        created_at: "2026-07-15T12:00:00Z",
        updated_at: "2026-07-15T12:00:01Z",
        request_payload: { provider: "custom", model: "requested-only-model" },
        result_payload: {
          model_version: "combination_model_v2.0",
          structured_directions: [],
        },
      })
    )
  );

  render(<JobDetailPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("供应商与实际模型")).toBeInTheDocument();
  expect(screen.getByText("历史未记录", { selector: "dd" })).toBeInTheDocument();
  expect(screen.getByLabelText("合格 未记录")).toBeInTheDocument();
  expect(screen.getByLabelText("待补证据 未记录")).toBeInTheDocument();
  expect(screen.getByLabelText("已淘汰 未记录")).toBeInTheDocument();
  expect(screen.queryByText(/requested-only-model/)).not.toBeInTheDocument();
});
