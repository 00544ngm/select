import { beforeEach, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ModelSelect, { availableModelsFor } from "@/components/workbench/model-select";
import type { ProviderConfiguration } from "@/lib/api/types";

const provider: ProviderConfiguration = {
  slug: "openai",
  api_protocol: "openai",
  display_name: "OpenAI",
  role: "primary",
  base_url: "https://api.openai.com/v1",
  default_model: "gpt-5.5",
  supported_models: ["gpt-5.5", "gpt-4o"],
  model_options: ["gpt-5.5", "gpt-4o"].map((model) => ({
    provider: "openai" as const,
    provider_display_name: "OpenAI",
    api_protocol: "openai" as const,
    model,
    is_default: model === "gpt-5.5",
    is_selected: true,
    is_enabled: true,
    test_status: "verified" as const,
    tested_at: new Date().toISOString(),
    test_message: "结构化验证成功",
  })),
  is_enabled: true,
  configured: true,
  masked_api_key: "********test",
  last_test_status: "success",
  last_tested_at: null,
  last_test_message: "Connection successful",
  updated_at: null,
};

const customProvider: ProviderConfiguration = {
  ...provider,
  slug: "custom",
  display_name: "自定义 API",
  base_url: "https://llm.example/v1",
  default_model: "custom-model",
  supported_models: ["custom-model"],
  model_options: [{
    provider: "custom",
    provider_display_name: "自定义 API",
    api_protocol: "openai",
    model: "custom-model",
    is_default: true,
    is_selected: true,
    is_enabled: true,
    test_status: "verified",
    tested_at: new Date().toISOString(),
    test_message: "结构化验证成功",
  }],
};

const registration = (name: string) => ({
  name,
  onChange: vi.fn(),
  onBlur: vi.fn(),
  ref: vi.fn(),
});

beforeEach(() => {
  localStorage.clear();
});

function renderSelect(entry: "hypothesis" | "judgment" | "batch" = "hypothesis") {
  return render(
    <ModelSelect
      preferenceEntry={entry}
      providers={[provider, customProvider]}
      providerRegistration={registration("provider")}
      modelRegistration={registration("model")}
    />
  );
}

it("offers only active primary provider identities", async () => {
  const user = userEvent.setup();
  renderSelect();

  expect(screen.getByRole("option", { name: "OpenAI" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "自定义 API" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "CatToken OpenAI" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "CatToken Claude" })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("供应商"), "custom");
  expect(screen.getByRole("option", { name: "custom-model" })).toBeInTheDocument();
});

it("lists only models discovered for the selected provider", () => {
  renderSelect();
  expect(screen.getByRole("option", { name: "gpt-5.5" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "gpt-4o" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /gpt-5.6-terra/i })).not.toBeInTheDocument();
});

it("exposes only fresh verified models selected for use", () => {
  const withUnselected = {
    ...provider,
    model_options: provider.model_options?.map((option) => ({
      ...option,
      is_selected: option.model === "gpt-4o",
    })),
  };

  expect(availableModelsFor(withUnselected)).toEqual(["gpt-4o"]);
});

it("persists a changed selection only after the save button is clicked", async () => {
  const user = userEvent.setup();
  const view = renderSelect("hypothesis");
  await user.selectOptions(screen.getByLabelText("供应商"), "custom");
  expect(screen.getByText("尚未保存")).toBeInTheDocument();
  expect(localStorage.getItem("workbench-model-preference:hypothesis")).toBeNull();

  await user.click(screen.getByRole("button", { name: "保存为此入口默认选择" }));
  expect(screen.getByText("已保存默认")).toBeInTheDocument();
  view.unmount();
  renderSelect("hypothesis");

  expect(screen.getByLabelText("供应商")).toHaveValue("custom");
  expect(screen.getByLabelText("模型")).toHaveValue("custom-model");
});

it("does not persist a temporary provider switch", async () => {
  localStorage.setItem(
    "workbench-model-preference:hypothesis",
    JSON.stringify({ version: 1, provider: "openai", model: "gpt-4o" })
  );
  const user = userEvent.setup();
  const view = renderSelect("hypothesis");
  expect(screen.getByLabelText("模型")).toHaveValue("gpt-4o");
  await user.selectOptions(screen.getByLabelText("供应商"), "custom");
  view.unmount();
  renderSelect("hypothesis");
  expect(screen.getByLabelText("供应商")).toHaveValue("openai");
  expect(screen.getByLabelText("模型")).toHaveValue("gpt-4o");
});

it("falls back safely when the saved model is no longer available", () => {
  localStorage.setItem(
    "workbench-model-preference:judgment",
    JSON.stringify({ version: 1, provider: "custom", model: "removed-model" })
  );
  renderSelect("judgment");
  expect(screen.getByLabelText("供应商")).toHaveValue("openai");
  expect(screen.getByText("原默认模型已不可用，请重新保存")).toBeInTheDocument();
});
