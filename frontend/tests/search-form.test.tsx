import { beforeEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import SearchForm from "@/components/workbench/search-form";
import { searchWalmart } from "@/lib/api/search";
import { ApiError } from "@/lib/api/client";

vi.mock("@/lib/api/search", () => ({
  searchWalmart: vi.fn(),
}));

const searchWalmartMock = vi.mocked(searchWalmart);

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {children}
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

it("submits the trimmed keyword through the shared search API client", async () => {
  const user = userEvent.setup();
  searchWalmartMock.mockResolvedValue({ results: [] });
  render(<SearchForm />, { wrapper: Wrapper });

  await user.type(
    screen.getByPlaceholderText("输入商品关键词搜索Walmart"),
    "  orthopedic dog bed  "
  );
  await user.click(screen.getByRole("button", { name: "搜索" }));

  expect(await screen.findByText("未找到相关商品")).toBeInTheDocument();
  expect(searchWalmartMock).toHaveBeenCalledWith("orthopedic dog bed");
});

it("offers an encoded Walmart browser link when robot verification is required", async () => {
  const user = userEvent.setup();
  searchWalmartMock.mockRejectedValue(
    new ApiError(
      "WALMART_SEARCH_REQUIRES_BROWSER",
      "Walmart 要求人工验证，请在浏览器中打开搜索并复制商品链接。",
      false,
      409
    )
  );
  render(<SearchForm />, { wrapper: Wrapper });

  await user.type(
    screen.getByPlaceholderText("输入商品关键词搜索Walmart"),
    "orthopedic dog bed"
  );
  await user.click(screen.getByRole("button", { name: "搜索" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Walmart 要求人工验证");
  expect(
    screen.getByRole("link", { name: "在浏览器打开 Walmart 搜索" })
  ).toHaveAttribute(
    "href",
    "https://www.walmart.com/search?q=orthopedic%20dog%20bed"
  );
});
