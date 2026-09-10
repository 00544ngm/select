import { it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import Home from "@/app/page";

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      {children}
    </QueryClientProvider>
  );
}

it("renders the page heading", () => {
  render(<Home />, { wrapper: Wrapper });
  expect(screen.getByText("工作台")).toBeInTheDocument();
});

it("renders a heading level 1", () => {
  render(<Home />, { wrapper: Wrapper });
  const heading = screen.getByRole("heading", { level: 1 });
  expect(heading).toBeInTheDocument();
});
