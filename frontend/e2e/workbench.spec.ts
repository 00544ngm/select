import { test, expect } from "@playwright/test";

test.describe("Workbench", () => {
  test("loads the page with workbench tabs", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "工作台" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "假设分析" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "对比审判" })).toBeVisible();
  });

  test("switches between hypothesis and judgment tabs", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: "对比审判" }).click();
    await expect(page.getByPlaceholder("请输入 A 商品链接")).toBeVisible();
    await expect(page.getByPlaceholder("B 商品链接 1")).toBeVisible();
  });

  test("adds B URLs in judgment form", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("tab", { name: "对比审判" }).click();
    await page.getByRole("button", { name: /添加/ }).click();
    await expect(page.getByPlaceholder("B 商品链接 2")).toBeVisible();
  });

  test("rejects invalid URLs with error message", async ({ page }) => {
    await page.route("**/api/v1/settings/providers", async (route) => {
      await route.fulfill({
        json: [{
          slug: "openai",
          api_protocol: "openai",
          display_name: "OpenAI",
          role: "primary",
          base_url: "https://api.openai.com/v1",
          default_model: "gpt-4o",
          is_enabled: true,
          configured: true,
          masked_api_key: "sk-••••••••",
          last_test_status: "success",
          last_tested_at: null,
          last_test_message: null,
          updated_at: null,
        }],
      });
    });
    await page.goto("/");
    const input = page.getByLabel("主品商品链接");
    const submitButton = page.getByRole("button", { name: /^分析$/ });
    await expect(submitButton).toBeEnabled();
    await input.fill("https://walmart.com.evil.example/ip/123");
    await submitButton.click();
    await expect(page.getByText(/域名不合法/)).toBeVisible();
  });

  test("saves API settings and exposes the provider in the workbench", async ({ page }) => {
    let configured = false;
    const provider = (isConfigured: boolean) => ({
      slug: "openai",
      api_protocol: "openai",
      display_name: "OpenAI",
      role: "primary",
      base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o",
      is_enabled: isConfigured,
      configured: isConfigured,
      masked_api_key: isConfigured ? "sk-••••••••" : null,
      last_test_status: "untested",
      last_tested_at: null,
      last_test_message: null,
      updated_at: null,
    });

    await page.route("**/api/v1/settings/providers**", async (route) => {
      if (route.request().method() === "PUT") {
        configured = true;
        await route.fulfill({ json: provider(true) });
        return;
      }
      await route.fulfill({ json: [provider(configured)] });
    });

    await page.goto("/settings/api");
    await page.getByLabel("启用").check();
    await page.getByLabel("新 API Key").fill("sk-test-browser-key");
    await page.getByRole("button", { name: "保存配置" }).click();
    await expect(page.getByRole("status")).toContainText("配置已保存");

    await page.goto("/");
    await page.getByRole("button", { name: /高级选项/ }).click();
    await expect(page.getByLabel("供应商")).toHaveValue("openai");
  });
});
