import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import DesktopPreflight from "@/components/layout/desktop-preflight";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));

vi.mock("@/lib/api/client", () => ({ apiFetch }));

beforeEach(() => {
  apiFetch.mockReset();
  window.desktop = {
    getSession: vi.fn(),
    getDesktopStatus: vi.fn(),
    requestQuit: vi.fn(),
    openLogDirectory: vi.fn(),
    openWindowsSecurity: vi.fn(),
  };
});

it("runs once and stays silent when browser preflight passes", async () => {
  apiFetch.mockResolvedValue({
    status: "passed",
    checks: { browser: { status: "passed", selected: "edge" } },
  });

  const { container } = render(<DesktopPreflight />);

  await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(1));
  expect(apiFetch).toHaveBeenCalledWith("/desktop/diagnostics", {
    timeoutMs: 30_000,
  });
  expect(container).toBeEmptyDOMElement();
});

it("shows an actionable warning only when all browser channels fail", async () => {
  apiFetch.mockResolvedValue({
    status: "failed",
    checks: {
      browser: {
        status: "failed",
        code: "DESKTOP_BROWSER_START_FAILED",
        summary: "浏览器组件无法启动",
      },
    },
  });

  render(<DesktopPreflight />);

  expect(
    await screen.findByText("浏览器环境未就绪，提交任务前请检查 Windows 安全中心或日志。")
  ).toBeInTheDocument();
  expect(apiFetch).toHaveBeenCalledTimes(1);
});

it("does not run desktop browser diagnostics in the web application", async () => {
  delete window.desktop;

  const { container } = render(<DesktopPreflight />);

  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(apiFetch).not.toHaveBeenCalled();
  expect(container).toBeEmptyDOMElement();
});
