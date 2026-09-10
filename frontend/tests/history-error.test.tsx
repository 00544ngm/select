import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import HistoryPage from "@/app/history/page";
import { listJobs, retryJob } from "@/lib/api/jobs";

vi.mock("@/lib/api/jobs", () => ({
  listJobs: vi.fn(),
  renameJob: vi.fn(),
  retryJob: vi.fn(),
}));

const listJobsMock = vi.mocked(listJobs);
const retryJobMock = vi.mocked(retryJob);

function renderHistory() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <HistoryPage />
    </QueryClientProvider>,
  );
}

const interruptedJob = {
  id: "interrupted-job",
  name: "中断任务",
  mode: "hypothesis" as const,
  status: "interrupted" as const,
  progress: 35,
  error_code: "APP_INTERRUPTED",
  error_message: "软件上次运行被中断，请手动重新提交",
  retry_of_id: null,
  created_at: "2026-08-06T01:00:00Z",
  updated_at: "2026-08-06T01:01:00Z",
  product_title: null,
  product_image: null,
};

describe("history failure states", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a retryable query error instead of an empty history state", async () => {
    listJobsMock.mockRejectedValueOnce(new Error("history unavailable"));

    renderHistory();

    expect(await screen.findByText("历史加载失败")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新加载历史" })).toBeInTheDocument();
    expect(screen.queryByText("暂无任务记录")).not.toBeInTheDocument();
  });

  it("shows interrupted jobs and exposes retry", async () => {
    listJobsMock.mockResolvedValueOnce({
      items: [interruptedJob],
      total: 1,
      page: 1,
      page_size: 20,
    });
    retryJobMock.mockResolvedValueOnce({ ...interruptedJob, id: "retry-job", status: "queued" });

    renderHistory();

    expect(await screen.findByText("已中断")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新提交" })).toBeInTheDocument();
  });
});
