import { afterAll, beforeAll, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { renameJob } from "@/lib/api/jobs";

const API_BASE = "http://localhost:8000";
const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

it("patches a historical job name", async () => {
  let requestBody: unknown;
  server.use(
    http.patch(`${API_BASE}/api/v1/jobs/:jobId/name`, async ({ request, params }) => {
      expect(params.jobId).toBe("job-1");
      requestBody = await request.json();
      return HttpResponse.json({ id: "job-1", name: "采购复核" });
    }),
  );

  const result = await renameJob("job-1", "采购复核");

  expect(requestBody).toEqual({ name: "采购复核" });
  expect(result.name).toBe("采购复核");
});

it("can clear a historical job name", async () => {
  let requestBody: unknown;
  server.use(
    http.patch(`${API_BASE}/api/v1/jobs/:jobId/name`, async ({ request }) => {
      requestBody = await request.json();
      return HttpResponse.json({ id: "job-1", name: null });
    }),
  );

  await renameJob("job-1", null);

  expect(requestBody).toEqual({ name: null });
});
