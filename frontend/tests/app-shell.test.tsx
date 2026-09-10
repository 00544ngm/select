import { it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AppShell from "@/components/layout/app-shell";

it("renders navigation with Chinese labels", () => {
  render(<AppShell>content</AppShell>);
  expect(screen.getByText("工作台")).toBeInTheDocument();
  expect(screen.getByText("历史记录")).toBeInTheDocument();
});

it("includes a skip-to-content link for keyboard users", () => {
  render(<AppShell>content</AppShell>);
  const skipLink = screen.getByText("跳转到内容");
  expect(skipLink).toBeInTheDocument();
  expect(skipLink).toHaveAttribute("href", "#main-content");
});

it("renders desktop sidebar with navigation landmarks", () => {
  render(<AppShell>content</AppShell>);
  expect(screen.getByRole("navigation")).toBeInTheDocument();
  expect(screen.getByRole("main")).toBeInTheDocument();
});

it("shows the app brand name", () => {
  render(<AppShell>content</AppShell>);
  const all = screen.getAllByText("组合选品控制台");
  expect(all.length).toBeGreaterThanOrEqual(1);
});

it("renders children in the main content area", () => {
  render(<AppShell><p>child content</p></AppShell>);
  expect(screen.getByText("child content")).toBeInTheDocument();
});

it("provides a mobile menu button", () => {
  render(<AppShell>content</AppShell>);
  const menuButton = screen.getByLabelText("打开菜单");
  expect(menuButton).toBeInTheDocument();
});

it("opens mobile navigation when menu button is clicked", async () => {
  const user = userEvent.setup();
  render(<AppShell>content</AppShell>);
  const menuButton = screen.getByLabelText("打开菜单");
  await user.click(menuButton);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

it("renders stable desktop API settings navigation", () => {
  render(<AppShell>content</AppShell>);

  expect(screen.getAllByRole("link", { name: "API 设置" }).length).toBeGreaterThanOrEqual(1);
  expect(screen.getByTestId("desktop-sidebar")).toHaveClass("w-56");
});

it("uses the approved low-glare shell surfaces", () => {
  render(<AppShell>content</AppShell>);

  expect(screen.getByTestId("app-shell")).toHaveClass("bg-canvas");
  expect(screen.getByTestId("desktop-sidebar")).toHaveClass("bg-navigation");
});
