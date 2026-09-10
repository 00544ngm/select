import { afterAll, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { ReactNode } from "react";
import JobDetailPage from "@/app/jobs/[jobId]/page";
import ResultsPage from "@/app/results/page";

const API_BASE = "http://localhost:8000";
vi.stubEnv("NEXT_PUBLIC_API_BASE", API_BASE);
vi.mock("next/navigation", () => ({
  useParams: () => ({ jobId: "job-judgment" }),
  useRouter: () => ({ push: vi.fn() }),
}));

const vetoContent = [
  "• 各B品详情: • Candidate Product: • 节奏不匹配: False",
  "• 竞品冲突: False",
  "• 已验证需求: False",
  "• 品牌压制: False",
  "• 物流问题: False",
  "• 法律风险: False",
  "• 差评超标: False",
  "• 被否决: False",
].join("\n");

const evidence = {
  per_b_product: {
    "Candidate Product": {
      product_title: "Candidate Product",
      product_url: "https://walmart.com/ip/456",
      platform: "Walmart",
      verified_at: "2026-07-28T14:30:00Z",
      status: "signal",
      analysis_state: "completed",
      valid_review_count: 12,
      relevant_review_count: 1,
      hit_rate: 0.0833,
      evidence: [],
      failure_reason: "",
    },
  },
};

const job = {
  id: "job-judgment",
  name: "判定历史任务",
  mode: "judgment",
  status: "completed",
  progress: 100,
  error_code: null,
  error_message: null,
  retry_of_id: null,
  created_at: "2026-07-28T13:37:06Z",
  updated_at: "2026-07-28T14:09:23Z",
  request_payload: {
    a_url: "https://walmart.com/ip/123",
    b_urls: ["https://walmart.com/ip/456"],
  },
  result_payload: {
    mode: "judgment",
    grade: "A",
    sections: [{ title: "否决审查", content: vetoContent }],
    complement_evidence: evidence,
  },
};

const server = setupServer(
  http.get(API_BASE + "/api/v1/jobs", () =>
    HttpResponse.json({ items: [job], total: 1, page: 1, page_size: 100 })
  ),
  http.get(API_BASE + "/api/v1/jobs/job-judgment", () => HttpResponse.json(job))
);

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());
beforeEach(() => server.resetHandlers());

it("shows complement evidence in task detail judgment analysis", async () => {
  const user = userEvent.setup();
  render(<JobDetailPage />, { wrapper: createWrapper() });

  await user.click(await screen.findByRole("button", { name: "方案分析" }));
  await user.click(screen.getByRole("button", { name: /Candidate Product/ }));

  expect(screen.getByText("有需求线索")).toBeInTheDocument();
  expect(screen.getByText("抽样评论 12 条")).toBeInTheDocument();
});

it("uses the same judgment evidence view for historical results", async () => {
  const user = userEvent.setup();
  render(<ResultsPage />, { wrapper: createWrapper() });

  const select = await screen.findByRole("combobox");
  await screen.findByRole("option", { name: /判定历史任务/ });
  await user.selectOptions(select, "job-judgment");
  await user.click(await screen.findByRole("button", { name: /Candidate Product/ }));

  expect(screen.getByText("有需求线索")).toBeInTheDocument();
  expect(screen.getByText("抽样评论 12 条")).toBeInTheDocument();
  expect(screen.queryByText("历史结果暂无结构化方向")).not.toBeInTheDocument();
});
