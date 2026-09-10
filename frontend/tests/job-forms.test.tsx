import { beforeEach, it, expect, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import WorkbenchTabs from "@/components/workbench/workbench-tabs";
import { listProviders } from "@/lib/api/providers";
import { submitJudgment } from "@/lib/api/jobs";
import { ApiError } from "@/lib/api/client";

vi.mock("@/lib/api/providers", () => ({
  listProviders: vi.fn(),
}));
vi.mock("@/lib/api/jobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/jobs")>();
  return { ...actual, submitJudgment: vi.fn() };
});

const listProvidersMock = vi.mocked(listProviders);
const submitJudgmentMock = vi.mocked(submitJudgment);
const availableProviders = [
  {
    slug: "openai" as const,
    api_protocol: "openai" as const,
    display_name: "OpenAI",
    role: "primary" as const,
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
    supported_models: ["gpt-4o"],
    model_options: [{
      provider: "openai" as const,
      provider_display_name: "OpenAI",
      api_protocol: "openai" as const,
      model: "gpt-4o",
      is_default: true,
      is_selected: true,
      is_enabled: true,
      test_status: "verified" as const,
      tested_at: new Date().toISOString(),
      test_message: "结构化验证成功",
    }],
    is_enabled: true,
    configured: true,
    masked_api_key: "••••4F2A",
    last_test_status: "success" as const,
    last_tested_at: null,
    last_test_message: null,
    updated_at: null,
  },
  {
    slug: "deepseek" as const,
    api_protocol: "openai" as const,
    display_name: "DeepSeek",
    role: "secondary" as const,
    base_url: "https://api.deepseek.com",
    default_model: "deepseek-chat",
    is_enabled: true,
    configured: true,
    masked_api_key: "••••22AA",
    last_test_status: "success" as const,
    last_tested_at: null,
    last_test_message: null,
    updated_at: null,
  },
];

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  listProvidersMock.mockResolvedValue(availableProviders);
});

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  );
}

function getActivePanel() {
  const panel = document.querySelector<HTMLElement>('[role="tabpanel"][data-state="active"]');
  expect(panel).not.toBeNull();
  return panel!;
}

it("renders hypothesis and judgment tabs", () => {
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  expect(screen.getByRole("tab", { name: "假设分析" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "对比审判" })).toBeInTheDocument();
});

it("shows hypothesis form by default", () => {
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  expect(screen.getByRole("textbox", { name: "主品商品链接" })).toBeInTheDocument();
});

it("switches to judgment tab on click", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  await user.click(screen.getByRole("tab", { name: "对比审判" }));
  expect(screen.getByPlaceholderText("请输入 A 商品链接")).toBeInTheDocument();
});

it("shows initial B URL field in judgment form", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  await user.click(screen.getByRole("tab", { name: "对比审判" }));
  expect(screen.getByPlaceholderText("B 商品链接 1")).toBeInTheDocument();
});

it("requires a URL in hypothesis form", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  await user.click(await screen.findByRole("button", { name: "分析" }));
  expect(screen.getByText("请输入商品链接")).toBeInTheDocument();
});

it("rejects lookalike URLs", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  const input = screen.getByRole("textbox", { name: "主品商品链接" });
  await user.type(input, "https://walmart.com.evil.example/ip/123");
  await user.click(await screen.findByRole("button", { name: "分析" }));
  expect(screen.getByText(/域名不合法/)).toBeInTheDocument();
});

it("allows adding B URLs via the add button", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  await user.click(screen.getByRole("tab", { name: "对比审判" }));
  await user.click(screen.getByRole("button", { name: /添加/ }));
  expect(screen.getByPlaceholderText("B 商品链接 2")).toBeInTheDocument();
});

it("disables submit button while submitting", () => {
  render(<WorkbenchTabs isSubmitting />, { wrapper: Wrapper });
  expect(screen.getByRole("button", { name: /提交中/ })).toBeDisabled();
});

it("disables hypothesis submission while provider settings are loading", () => {
  listProvidersMock.mockReturnValue(new Promise(() => {}));
  render(<WorkbenchTabs />, { wrapper: Wrapper });

  expect(screen.getByRole("button", { name: /提交中/ })).toBeDisabled();
});

it("shows only enabled primary providers in advanced options", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });

  const activePanel = getActivePanel();
  await user.click(within(activePanel).getByText("模型设置"));

  expect((await screen.findAllByRole("option", { name: /OpenAI/ })).length).toBeGreaterThan(0);
  expect(screen.queryByRole("option", { name: /DeepSeek/ })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "CatToken OpenAI" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "CatToken Claude" })).not.toBeInTheDocument();
});

it("keeps the hypothesis task name beside the URL instead of inside model settings", async () => {
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });

  const activePanel = getActivePanel();
  expect(within(activePanel).getByPlaceholderText("给本次分析起个名字")).toBeInTheDocument();
  expect(within(activePanel).queryByRole("button", { name: "保存为此入口默认选择" })).not.toBeInTheDocument();
  await user.click(within(activePanel).getByText("模型设置"));
  expect(within(activePanel).getByRole("button", { name: "保存为此入口默认选择" })).toBeInTheDocument();
  expect(within(activePanel).getAllByPlaceholderText("给本次分析起个名字")).toHaveLength(1);
});

it("hides primary providers whose latest test failed or has no verified model", async () => {
  listProvidersMock.mockResolvedValue([
    availableProviders[0],
    { ...availableProviders[1], last_test_status: "failed" as const },
  ]);
  const user = userEvent.setup();
  render(<WorkbenchTabs />, { wrapper: Wrapper });
  const activePanel = getActivePanel();
  await user.click(within(activePanel).getByText("模型设置"));

  expect((await screen.findAllByRole("option", { name: "OpenAI" })).length).toBeGreaterThan(0);
  expect(screen.queryByRole("option", { name: "CatToken OpenAI" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "CatToken Claude" })).not.toBeInTheDocument();
});

it("links to API settings when no primary provider is available", async () => {
  listProvidersMock.mockResolvedValue([]);
  render(<WorkbenchTabs />, { wrapper: Wrapper });

  expect((await screen.findAllByRole("link", { name: "前往 API 设置" }))[0]).toHaveAttribute(
    "href",
    "/settings/api"
  );
  expect(screen.getByRole("button", { name: "请先配置 API" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: /提交中/ })).not.toBeInTheDocument();
});

it("refreshes the provider catalog when judgment rejects an invalid model", async () => {
  const user = userEvent.setup();
  submitJudgmentMock.mockRejectedValue(
    new ApiError(
      "PROVIDER_MODEL_INVALID",
      "当前模型不存在或暂不可用",
      false,
      409
    )
  );
  render(<WorkbenchTabs />, { wrapper: Wrapper });

  await user.click(screen.getByRole("tab", { name: "对比审判" }));
  await user.type(screen.getByPlaceholderText("请输入 A 商品链接"), "https://www.walmart.com/ip/a/1");
  await user.type(screen.getByPlaceholderText("B 商品链接 1"), "https://www.walmart.com/ip/b/2");
  await user.click(await screen.findByRole("button", { name: "提交" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("当前模型不存在或暂不可用");
  await waitFor(() => expect(listProvidersMock).toHaveBeenCalledTimes(2));
});
