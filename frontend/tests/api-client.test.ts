import { it, expect, beforeAll, afterAll, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { apiFetch } from "@/lib/api/client";
import { getJobPollingInterval } from "@/lib/job-status";

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

it("apiFetch constructs the correct URL", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/test", () =>
      HttpResponse.json({ ok: true })
    )
  );
  const data = await apiFetch<{ ok: boolean }>("/test");
  expect(data.ok).toBe(true);
});

it("apiFetch sends JSON request bodies", async () => {
  server.use(
    http.post("http://localhost:8000/api/v1/jobs/hypothesis", async ({ request }) => {
      const body = await request.json();
      return HttpResponse.json(body, { status: 202 });
    })
  );
  const payload = { url: "https://walmart.com/ip/test" };
  const data = await apiFetch<{ url: string }>("/jobs/hypothesis", {
    method: "POST",
    body: payload,
  });
  expect(data.url).toBe(payload.url);
});

it("apiFetch throws ApiError on non-JSON error", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/error", () =>
      HttpResponse.text("Gateway Timeout", { status: 502 })
    )
  );
  try {
    await apiFetch("/error");
    expect.unreachable("should have thrown");
  } catch (e: unknown) {
    const err = e as { code: string; message: string; retryable: boolean; status: number };
    expect(err.code).toBe("UPSTREAM_ERROR");
    expect(err.status).toBe(502);
  }
});

it("apiFetch throws ApiError with decoded detail", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/jobs/999", () =>
      HttpResponse.json(
        { detail: { code: "JOB_NOT_FOUND", message: "not found", retryable: false } },
        { status: 404 }
      )
    )
  );
  try {
    await apiFetch("/jobs/999");
    expect.unreachable("should have thrown");
  } catch (e: unknown) {
    const err = e as { code: string; message: string; retryable: boolean; status: number };
    expect(err.code).toBe("JOB_NOT_FOUND");
    expect(err.status).toBe(404);
  }
});

it("apiFetch aborts a hung desktop request and returns a stable timeout error", async () => {
  const originalFetch = globalThis.fetch;
  vi.stubGlobal("fetch", (_url: string, init?: RequestInit) =>
    new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () =>
        reject(new DOMException("aborted", "AbortError"))
      );
    })
  );

  await expect(apiFetch("/hung", { timeoutMs: 10 })).rejects.toMatchObject({
    code: "DESKTOP_API_TIMEOUT",
    retryable: true,
    status: 504,
  });
  vi.stubGlobal("fetch", originalFetch);
});

it("getJobPollingInterval returns 1500 for running jobs", () => {
  expect(getJobPollingInterval("running")).toBe(1500);
});

it("getJobPollingInterval returns false for completed jobs", () => {
  expect(getJobPollingInterval("completed")).toBe(false);
});

it("getJobPollingInterval returns false for failed jobs", () => {
  expect(getJobPollingInterval("failed")).toBe(false);
});

it("getJobPollingInterval returns 1500 for queued jobs", () => {
  expect(getJobPollingInterval("queued")).toBe(1500);
});
