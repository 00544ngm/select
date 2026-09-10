import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api/client";
import { resetDesktopSessionForTests } from "@/lib/api/desktop-session";

describe("desktop API session", () => {
  beforeEach(() => {
    resetDesktopSessionForTests();
    vi.restoreAllMocks();
  });

  it("injects the session and dynamic API base", async () => {
    window.desktop = {
      getSession: vi.fn().mockResolvedValue({ token: "session-token" }),
      getDesktopStatus: vi.fn().mockResolvedValue({
        apiBase: "http://127.0.0.1:43127",
      }),
      requestQuit: vi.fn(),
      openLogDirectory: vi.fn(),
      openWindowsSecurity: vi.fn(),
    };
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await apiFetch("/health/ready");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:43127/api/v1/health/ready",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Desktop-Session": "session-token",
        }),
      }),
    );
  });
});
