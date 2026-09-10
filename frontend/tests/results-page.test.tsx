import { afterAll, beforeAll, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { ReactNode } from "react";
import ResultsPage from "@/app/results/page";

const API_BASE = "http://localhost:8000";
const server = setupServer(
  http.get(`${API_BASE}/api/v1/jobs`, () =>
    HttpResponse.json({
      items: [{
        id: "job-results", name: "结果页任务", mode: "hypothesis", status: "completed", progress: 100,
        error_code: null, error_message: null, retry_of_id: null,
        created_at: "2026-07-27T13:37:06Z", updated_at: "2026-07-27T14:09:23Z",
      }],
      total: 1, page: 1, page_size: 100,
    })
  ),
  http.get(`${API_BASE}/api/v1/jobs/job-results`, () =>
    HttpResponse.json({
      id: "job-results", name: "结果页任务", mode: "hypothesis", status: "completed", progress: 100,
      error_code: null, error_message: null, retry_of_id: null,
      created_at: "2026-07-27T13:37:06Z", updated_at: "2026-07-27T14:09:23Z",
      request_payload: { url: "https://walmart.com/ip/123" },
      result_payload: {
        grade: "A", score: 90, product_title: "Pizza Cutter",
        structured_directions: [{ name: "防滑垫", score: 91, keywords: { en: "non slip mat" } }],
        sections: [{ title: "商品分析", content: "结果页唯一商品分析" }],
      },
    })
  )
);

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

it("does not duplicate full result sections above the workbench", async () => {
  const user = userEvent.setup();
  render(<ResultsPage />, { wrapper: createWrapper() });

  const select = await screen.findByRole("combobox");
  await screen.findByRole("option", { name: /结果页任务/ });
  await user.selectOptions(select, "job-results");

  await screen.findByRole("tab", { name: "商品与证据" });
  expect(screen.queryByText("结果页唯一商品分析")).not.toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "商品与证据" }));
  expect(screen.getByText("结果页唯一商品分析")).toBeInTheDocument();
});
