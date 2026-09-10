import { it, expect, vi, beforeAll, afterAll } from "vitest";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import WorkbenchTabs from "@/components/workbench/workbench-tabs";
import JobProgress from "@/components/jobs/job-progress";
import JobError from "@/components/jobs/job-error";
import BatchForm from "@/components/workbench/batch-form";

const API_BASE = "http://localhost:8000";

vi.stubEnv("NEXT_PUBLIC_API_BASE", API_BASE);

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

const server = setupServer(
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
        last_test_status: "success",
        last_tested_at: null,
        last_test_message: null,
        updated_at: null,
      },
    ])
  ),
  http.post(`${API_BASE}/api/v1/jobs/batch`, () =>
    HttpResponse.json({
      id: "batch-job-1", mode: "batch", status: "queued", progress: 0,
      error_code: null, error_message: null, retry_of_id: null,
      created_at: "2026-07-15T12:00:00Z", updated_at: "2026-07-15T12:00:00Z",
    })
  ),
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

it("icon-only buttons have accessible names", () => {
  render(<JobError errorCode="ERR" errorMessage="fail" onRetry={() => {}} />);
  expect(screen.getByRole("button", { name: /重新提交/i })).toBeInTheDocument();
});

it("progress bar has accessible role and values", () => {
  render(<JobProgress status="running" progress={45} />);
  const bar = screen.getByRole("progressbar");
  expect(bar).toHaveAttribute("aria-valuenow", "45");
  expect(bar).toHaveAttribute("aria-valuemin", "0");
  expect(bar).toHaveAttribute("aria-valuemax", "100");
});

it("inputs have associated placeholders as labels", () => {
  render(
    <WorkbenchTabs />,
    { wrapper: createWrapper() }
  );
  const inputs = screen.getAllByRole("textbox");
  expect(inputs.length).toBeGreaterThan(0);
  inputs.forEach((input) => {
    expect(input).toHaveAttribute("placeholder");
  });
});

it("status labels are not conveyed by color alone", () => {
  render(<JobProgress status="completed" progress={100} />);
  expect(screen.getByText("任务已完成")).toBeInTheDocument();

  render(<JobProgress status="failed" progress={50} />);
  expect(screen.getByText("任务失败")).toBeInTheDocument();

  render(<JobProgress status="running" progress={50} />);
  expect(screen.getByText("正在模型分析...")).toBeInTheDocument();

  render(<JobProgress status="queued" progress={0} />);
  expect(screen.getByText("排队中，等待执行...")).toBeInTheDocument();
});

it("no text overflow at 320px viewport", () => {
  const { container } = render(
    <div style={{ width: "320px" }}>
      <JobProgress status="running" progress={100} />
    </div>
  );
  const outer = container.firstElementChild!;
  expect(outer.scrollWidth).toBeLessThanOrEqual(outer.clientWidth + 1);
});

it("textarea in batch form has placeholder label", () => {
  render(<BatchForm />, { wrapper: createWrapper() });
  expect(screen.getByPlaceholderText(/每行一个商品链接/i)).toBeInTheDocument();
});

it("batch form submit button is reachable", () => {
  render(<BatchForm />, { wrapper: createWrapper() });
  expect(screen.getByRole("button", { name: /提交/i })).toBeInTheDocument();
});

it("uses clear Chinese typography without compressed letter spacing", () => {
  const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8");

  expect(css).toContain('font-family: "Microsoft YaHei UI", "Noto Sans SC", sans-serif;');
  expect(css).toMatch(/body\s*{[\s\S]*?font-size:\s*(?:1[4-9]|[2-9]\d)px;/);
  expect(css).toMatch(/body\s*{[\s\S]*?letter-spacing:\s*0;/);
  expect(css).toMatch(/\.analysis-copy\s*{[\s\S]*?line-height:\s*1\.7;/);
  expect(css).toMatch(/\.keyword-text\s*{[\s\S]*?font-family:\s*Consolas,/);
});
