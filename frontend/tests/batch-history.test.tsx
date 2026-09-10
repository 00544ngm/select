import { it, expect, vi, beforeAll, afterAll, afterEach, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import BatchForm from "@/components/workbench/batch-form";
import HistoryPage from "@/app/history/page";

const API_BASE = "http://localhost:8000";

vi.stubEnv("NEXT_PUBLIC_API_BASE", API_BASE);

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
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

const mockJobs = {
  items: [
    {
      id: "job-1",
      name: "Pizza accessory research",
      mode: "hypothesis",
      status: "completed",
      progress: 100,
      error_code: null,
      error_message: null,
      retry_of_id: null,
      created_at: "2026-07-27T13:37:06Z",
      updated_at: "2026-07-27T14:09:23Z",
      product_title: "BUSATIA Blade Guard Pizza Cutter Rocker",
      product_image: null,
      top_direction_name: "防滑披萨切割垫 (Non-Slip Pizza Cutting Mat)",
      top_direction_keywords: { en: "non slip pizza cutting mat" },
      top_direction_score: 91,
      top_direction_type: "低成本价值附加",
      score: 77.6,
      request_payload: { url: "https://walmart.com/ip/111" },
      result_payload: { grade: "A", score: 90 },
    },
    {
      id: "job-2",
      name: "Failed comparison",
      mode: "judgment",
      status: "failed",
      progress: 50,
      error_code: "SCRAPE_FAILED",
      error_message: "无法抓取商品页面",
      retry_of_id: null,
      created_at: "2026-07-26T12:30:00Z",
      updated_at: "2026-07-26T12:31:00Z",
      product_title: null,
      product_image: null,
      top_direction_name: null,
      top_direction_keywords: {},
      top_direction_score: null,
      top_direction_type: null,
      score: null,
      request_payload: { a_url: "https://walmart.com/ip/222", b_urls: ["https://walmart.com/ip/223"] },
      result_payload: null,
    },
    {
      id: "job-3",
      name: "Running batch",
      mode: "batch",
      status: "running",
      progress: 60,
      error_code: null,
      error_message: null,
      retry_of_id: null,
      created_at: "2026-07-25T13:00:00Z",
      updated_at: "2026-07-25T13:00:30Z",
      request_payload: { urls: ["https://walmart.com/ip/333"] },
      result_payload: null,
    },
  ],
  total: 3,
  page: 1,
  page_size: 20,
};

const handlers = [
  http.get(`${API_BASE}/api/v1/settings/providers`, () =>
    HttpResponse.json([
      {
        slug: "openai",
        api_protocol: "openai",
        display_name: "OpenAI",
        role: "primary",
        base_url: "https://api.openai.com/v1",
        default_model: "gpt-4o",
        is_enabled: true,
        configured: true,
        masked_api_key: "********F2A",
        supported_models: ["gpt-4o"],
        model_options: [{
          provider: "openai",
          provider_display_name: "OpenAI",
          api_protocol: "openai",
          model: "gpt-4o",
          is_default: true,
          is_selected: true,
          is_enabled: true,
          test_status: "verified",
          tested_at: new Date().toISOString(),
          test_message: "结构化验证成功",
        }],
        last_test_status: "success",
        last_tested_at: null,
        last_test_message: null,
        updated_at: null,
      },
      {
        slug: "deepseek",
        api_protocol: "openai",
        display_name: "DeepSeek",
        role: "secondary",
        base_url: "https://api.deepseek.com",
        default_model: "deepseek-chat",
        is_enabled: true,
        configured: true,
        masked_api_key: "********2AA",
        supported_models: ["deepseek-chat"],
        last_test_status: "success",
        last_tested_at: null,
        last_test_message: null,
        updated_at: null,
      },
    ])
  ),
  http.get(`${API_BASE}/api/v1/jobs`, ({ request }) => {
    const url = new URL(request.url);
    const page = url.searchParams.get("page") || "1";
    const mode = url.searchParams.get("mode");
    const status = url.searchParams.get("status");

    let filtered = [...mockJobs.items];
    if (mode) filtered = filtered.filter((j) => j.mode === mode);
    if (status) filtered = filtered.filter((j) => j.status === status);

    return HttpResponse.json({
      items: filtered,
      total: filtered.length,
      page: Number(page),
      page_size: 20,
    });
  }),

  http.post(`${API_BASE}/api/v1/jobs/batch`, () =>
    HttpResponse.json({
      id: "batch-job-1",
      mode: "batch",
      status: "queued",
      progress: 0,
      error_code: null,
      error_message: null,
      retry_of_id: null,
      created_at: "2026-07-15T14:00:00Z",
      updated_at: "2026-07-15T14:00:00Z",
    })
  ),

  http.post(`${API_BASE}/api/v1/jobs/:jobId/retry`, ({ params }) => {
    return HttpResponse.json({
      id: "job-retry-1",
      mode: "hypothesis",
      status: "queued",
      progress: 0,
      error_code: null,
      error_message: null,
      retry_of_id: params.jobId,
      created_at: "2026-07-15T14:00:00Z",
      updated_at: "2026-07-15T14:00:00Z",
    });
  }),
];

const server = setupServer(...handlers);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
beforeEach(() => {
  localStorage.clear();
  server.resetHandlers();
});
afterEach(() => vi.useRealTimers());

it("shows list of jobs with IDs", async () => {
  render(<HistoryPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("job-1")).toBeInTheDocument();
  expect(screen.getByText("job-2")).toBeInTheDocument();
  expect(screen.getByText("job-3")).toBeInTheDocument();
});

it("shows mode labels for each job", async () => {
  render(<HistoryPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("假设分析")).toBeInTheDocument();
  expect(screen.getByText("对比审判")).toBeInTheDocument();
  expect(screen.getByText("批量处理")).toBeInTheDocument();
});

it("shows Beijing match time and the saved main-product to direction summary", async () => {
  render(<HistoryPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("21:37 开始")).toBeInTheDocument();
  expect(screen.getByText("22:09 完成")).toBeInTheDocument();
  expect(screen.getByText("32分17秒")).toBeInTheDocument();
  expect(screen.getByText("BUSATIA Blade Guard Pizza Cutter Rocker")).toBeInTheDocument();
  expect(screen.getByText("防滑披萨切割垫")).toBeInTheDocument();
  expect(screen.getByText("non slip pizza cutting mat")).toBeInTheDocument();
  expect(screen.getByText("方向分 91")).toBeInTheDocument();
  expect(screen.getByText("综合 77.6")).toBeInTheDocument();
  expect(screen.getAllByText("历史无图").length).toBeGreaterThan(0);

  expect(screen.getByText("20:31 结束")).toBeInTheDocument();
  expect(screen.getByText("无法抓取商品页面")).toBeInTheDocument();
  expect(screen.getAllByText("没有评分").length).toBeGreaterThan(0);
  expect(screen.getAllByText("未生成匹配结果").length).toBeGreaterThan(0);
});

it("shows and refreshes elapsed time for running jobs", async () => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"] });
  vi.setSystemTime(new Date("2026-07-25T13:01:30Z"));
  render(<HistoryPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("已运行 1分30秒")).toBeInTheDocument();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(screen.getByText("已运行 2分30秒")).toBeInTheDocument();
});

it("groups history by Beijing calendar date", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-07-27T15:00:00Z"));
  render(<HistoryPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("今天 · 2026年7月27日")).toBeInTheDocument();
  expect(screen.getByText("昨天 · 2026年7月26日")).toBeInTheDocument();
  expect(screen.getByText("2026年7月25日")).toBeInTheDocument();
});

it("shows empty state when no jobs exist", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs`, () =>
      HttpResponse.json({ items: [], total: 0, page: 1, page_size: 20 })
    )
  );
  render(<HistoryPage />, { wrapper: createWrapper() });
  expect(await screen.findByText(/暂无任务/i)).toBeInTheDocument();
});

it("filters by mode", async () => {
  const user = userEvent.setup();
  render(<HistoryPage />, { wrapper: createWrapper() });
  await screen.findByText("job-1");

  await user.click(screen.getByRole("button", { name: /模式/i }));
  await user.click(screen.getByRole("option", { name: /假设分析/i }));

  await waitFor(() => {
    expect(screen.getByText("job-1")).toBeInTheDocument();
    expect(screen.queryByText("job-2")).not.toBeInTheDocument();
  });
});

it("filters by status", async () => {
  const user = userEvent.setup();
  render(<HistoryPage />, { wrapper: createWrapper() });
  await screen.findByText("job-1");

  await user.click(screen.getByRole("button", { name: /状态/i }));
  await user.click(screen.getByRole("option", { name: /失败/i }));

  await waitFor(() => {
    expect(screen.getByText("job-2")).toBeInTheDocument();
    expect(screen.queryByText("job-1")).not.toBeInTheDocument();
  });
});

it("shows retry button for failed jobs", async () => {
  render(<HistoryPage />, { wrapper: createWrapper() });
  expect(await screen.findByRole("button", { name: /重新提交/i })).toBeInTheDocument();
});

it("shows a dedicated status while Walmart verification is required", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/jobs`, () =>
      HttpResponse.json({
        items: [{
          ...mockJobs.items[2],
          error_code: "WALMART_CAPTCHA_REQUIRED",
          error_message: "已打开 Walmart 验证窗口",
        }],
        total: 1,
        page: 1,
        page_size: 20,
      })
    )
  );

  render(<HistoryPage />, { wrapper: createWrapper() });

  expect(await screen.findByText("等待 Walmart 验证")).toBeInTheDocument();
  expect(screen.queryByText("处理中 60%")).not.toBeInTheDocument();
});

it("shows pagination when total exceeds page size", async () => {
  const manyJobs = Array.from({ length: 25 }, (_, i) => ({
    id: `job-${i + 1}`,
    mode: "hypothesis" as const,
    status: "completed" as const,
    progress: 100,
    error_code: null,
    error_message: null,
    retry_of_id: null,
    created_at: "2026-07-15T12:00:00Z",
    updated_at: "2026-07-15T12:01:00Z",
    request_payload: { url: `https://walmart.com/ip/${i + 1}` },
    result_payload: { grade: "A", score: 90 },
  }));

  server.use(
    http.get(`${API_BASE}/api/v1/jobs`, ({ request }) => {
      const url = new URL(request.url);
      const page = Number(url.searchParams.get("page") || "1");
      const page_size = 20;
      const start = (page - 1) * page_size;
      return HttpResponse.json({
        items: manyJobs.slice(start, start + page_size),
        total: manyJobs.length,
        page,
        page_size,
      });
    })
  );

  render(<HistoryPage />, { wrapper: createWrapper() });
  expect(await screen.findByText("job-1")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /下一页/i })).toBeInTheDocument();
});

it("navigates to next page on pagination click", async () => {
  const manyJobs = Array.from({ length: 25 }, (_, i) => ({
    id: `job-${i + 1}`,
    mode: "hypothesis" as const,
    status: "completed" as const,
    progress: 100,
    error_code: null,
    error_message: null,
    retry_of_id: null,
    created_at: "2026-07-15T12:00:00Z",
    updated_at: "2026-07-15T12:01:00Z",
    request_payload: { url: `https://walmart.com/ip/${i + 1}` },
    result_payload: { grade: "A", score: 90 },
  }));

  server.use(
    http.get(`${API_BASE}/api/v1/jobs`, ({ request }) => {
      const url = new URL(request.url);
      const page = Number(url.searchParams.get("page") || "1");
      const page_size = 20;
      const start = (page - 1) * page_size;
      return HttpResponse.json({
        items: manyJobs.slice(start, start + page_size),
        total: manyJobs.length,
        page,
        page_size,
      });
    })
  );

  const user = userEvent.setup();
  render(<HistoryPage />, { wrapper: createWrapper() });
  await screen.findByText("job-1");

  await user.click(screen.getByRole("button", { name: /下一页/i }));
  expect(await screen.findByText("job-21")).toBeInTheDocument();
});

// --- Batch form tests ---

it("parses newline-separated URLs in batch form", async () => {
  const user = userEvent.setup();
  render(<BatchForm />, { wrapper: createWrapper() });

  const textarea = screen.getByPlaceholderText(/每行一个商品链接/i);
  await user.type(textarea, "https://walmart.com/ip/111\nhttps://amazon.com/dp/222");

  expect(await screen.findByText(/2.*个有效/)).toBeInTheDocument();
});

it("shows invalid URL count for bad entries", async () => {
  const user = userEvent.setup();
  render(<BatchForm />, { wrapper: createWrapper() });

  const textarea = screen.getByPlaceholderText(/每行一个商品链接/i);
  await user.type(textarea, "https://walmart.com/ip/111\nnot-a-url\nhttps://evil.com/ip/333");

  expect(await screen.findByText(/1.*个有效/)).toBeInTheDocument();
  expect(screen.getByText(/2.*个无效/)).toBeInTheDocument();
});

it("deduplicates repeated URLs", async () => {
  const user = userEvent.setup();
  render(<BatchForm />, { wrapper: createWrapper() });

  const textarea = screen.getByPlaceholderText(/每行一个商品链接/i);
  await user.type(textarea, "https://walmart.com/ip/111\nhttps://walmart.com/ip/111");

  expect(await screen.findByText(/1.*个有效/)).toBeInTheDocument();
});

it("submits batch form with valid URLs", async () => {
  const user = userEvent.setup();
  render(<BatchForm />, { wrapper: createWrapper() });

  const textarea = screen.getByPlaceholderText(/每行一个商品链接/i);
  await user.type(textarea, "https://walmart.com/ip/111\nhttps://amazon.com/dp/222");

  await screen.findByText(/2.*个有效/);
  await user.click(screen.getByRole("button", { name: /提交/i }));

  expect(await screen.findByText(/提交成功/i)).toBeInTheDocument();
});

it("shows only enabled primary providers in the batch form", async () => {
  render(<BatchForm />, { wrapper: createWrapper() });

  expect((await screen.findAllByRole("option", { name: "OpenAI" })).length).toBeGreaterThan(0);
  expect(screen.queryByRole("option", { name: /CatToken/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /DeepSeek/ })).not.toBeInTheDocument();
});

it("edits a task note inline and saves it with Enter", async () => {
  const user = userEvent.setup();
  let requestBody: unknown;
  server.use(
    http.patch(`${API_BASE}/api/v1/jobs/job-1/name`, async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({ ...mockJobs.items[0], name: "采购复核" });
    }),
  );
  render(<HistoryPage />, { wrapper: createWrapper() });

  await screen.findByText("Pizza accessory research");
  await user.click(screen.getAllByRole("button", { name: "修改任务备注" })[0]);
  const input = screen.getByRole("textbox", { name: "任务备注" });
  expect(input).toHaveValue("Pizza accessory research");
  await user.clear(input);
  await user.type(input, "采购复核{Enter}");

  expect(await screen.findByText("采购复核")).toBeInTheDocument();
  expect(requestBody).toEqual({ name: "采购复核" });
});

it("cancels task-note editing with Escape", async () => {
  const user = userEvent.setup();
  render(<HistoryPage />, { wrapper: createWrapper() });

  await screen.findByText("Pizza accessory research");
  await user.click(screen.getAllByRole("button", { name: "修改任务备注" })[0]);
  const input = screen.getByRole("textbox", { name: "任务备注" });
  await user.clear(input);
  await user.type(input, "不会保存{Escape}");

  expect(screen.queryByRole("textbox", { name: "任务备注" })).not.toBeInTheDocument();
  expect(screen.getByText("Pizza accessory research")).toBeInTheDocument();
});

it("saves the batch model preference without changing other entry preferences", async () => {
  const user = userEvent.setup();
  render(<BatchForm />, { wrapper: createWrapper() });

  await screen.findByRole("option", { name: "OpenAI" });
  await user.click(screen.getByRole("button", { name: "保存为此入口默认选择" }));

  expect(localStorage.getItem("workbench-model-preference:batch")).toContain('"provider":"openai"');
  expect(localStorage.getItem("workbench-model-preference:hypothesis")).toBeNull();
  expect(localStorage.getItem("workbench-model-preference:judgment")).toBeNull();
});

it("blocks batch submission and links to settings when no primary provider is available", async () => {
  server.use(
    http.get(`${API_BASE}/api/v1/settings/providers`, () => HttpResponse.json([]))
  );
  render(<BatchForm />, { wrapper: createWrapper() });

  expect(await screen.findByRole("link", { name: "前往 API 设置" })).toHaveAttribute(
    "href",
    "/settings/api"
  );
  expect(screen.getByRole("button", { name: "提交" })).toBeDisabled();
});
