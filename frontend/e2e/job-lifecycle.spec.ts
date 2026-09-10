import { test, expect } from "@playwright/test";

test.describe("Job lifecycle", () => {
  test("navigates to history page", async ({ page }) => {
    await page.goto("/history");
    await expect(page.getByRole("heading", { name: "任务历史" })).toBeVisible();
  });

  test("shows filters on history page", async ({ page }) => {
    await page.goto("/history");
    await expect(page.getByRole("button", { name: /模式/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /状态/i })).toBeVisible();
  });

  test("shows empty state on history page", async ({ page }) => {
    // Mock empty response
    await page.route("**/api/v1/jobs*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
      });
    });
    await page.goto("/history");
    await expect(page.getByText(/暂无任务/)).toBeVisible();
  });

  test("shows job detail page for a mock job", async ({ page }) => {
    const mockJob = {
      id: "e2e-test-job",
      mode: "hypothesis",
      status: "completed",
      progress: 100,
      error_code: null,
      error_message: null,
      retry_of_id: null,
      created_at: "2026-07-15T12:00:00Z",
      updated_at: "2026-07-15T12:01:00Z",
      request_payload: { url: "https://walmart.com/ip/123" },
      result_payload: { grade: "A", score: 90, directions: "推荐" },
    };

    await page.route("**/api/v1/jobs/e2e-test-job", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockJob),
      });
    });

    await page.goto("/jobs/e2e-test-job");
    await expect(page.getByText("任务详情")).toBeVisible();
    await expect(page.getByText("A", { exact: true }).first()).toBeVisible();
    await expect(page.getByText("90", { exact: true }).first()).toBeVisible();
  });

  test("shows download buttons for completed job", async ({ page }) => {
    const mockJob = {
      id: "e2e-download-job",
      mode: "hypothesis",
      status: "completed",
      progress: 100,
      error_code: null,
      error_message: null,
      retry_of_id: null,
      created_at: "2026-07-15T12:00:00Z",
      updated_at: "2026-07-15T12:01:00Z",
      request_payload: { url: "https://walmart.com/ip/123" },
      result_payload: { grade: "A", score: 90 },
    };

    await page.route("**/api/v1/jobs/e2e-download-job", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(mockJob),
      });
    });

    await page.goto("/jobs/e2e-download-job");
    await expect(page.getByRole("button", { name: /下载 JSON/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /下载 Excel/i })).toBeVisible();
  });
});
