import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterAll, afterEach, beforeAll, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import type { ReactNode } from "react";
import ProviderSettingsPanel from "@/components/settings/provider-settings-panel";

const providers = [
  {
    slug: "openai",
    api_protocol: "openai",
    display_name: "OpenAI",
    role: "primary",
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
    supported_models: ["gpt-4o", "gpt-4.1"],
    model_options: ["gpt-4o", "gpt-4.1"].map((model) => ({
      provider: "openai",
      provider_display_name: "OpenAI",
      api_protocol: "openai",
      model,
      is_default: model === "gpt-4o",
      is_enabled: true,
      test_status: "verified",
      tested_at: new Date().toISOString(),
      test_message: "结构化验证成功",
    })),
    is_enabled: true,
    configured: true,
    masked_api_key: "••••4F2A",
    last_test_status: "success",
    last_tested_at: null,
    last_test_message: "Connection successful",
    updated_at: null,
  },
  {
    slug: "deepseek",
    api_protocol: "openai",
    display_name: "DeepSeek",
    role: "secondary",
    base_url: "https://api.deepseek.com",
    default_model: "deepseek-chat",
    supported_models: [],
    is_enabled: false,
    configured: false,
    masked_api_key: null,
    last_test_status: "untested",
    last_tested_at: null,
    last_test_message: null,
    updated_at: null,
  },
  {
    slug: "custom",
    api_protocol: "openai",
    display_name: "自定义 API",
    role: "primary",
    base_url: "https://llm.example/v1",
    default_model: "model-x",
    supported_models: ["model-x"],
    model_options: [{
      provider: "custom",
      provider_display_name: "自定义 API",
      api_protocol: "openai",
      model: "model-x",
      is_default: true,
      is_enabled: true,
      test_status: "verified",
      tested_at: new Date().toISOString(),
      test_message: "结构化验证成功",
    }],
    is_enabled: true,
    configured: true,
    masked_api_key: "••••1234",
    last_test_status: "success",
    last_tested_at: null,
    last_test_message: "Connection successful",
    updated_at: null,
  },
  {
    slug: "cattoken",
    api_protocol: "openai",
    display_name: "CatToken OpenAI",
    role: "primary",
    base_url: "https://www.cattoken.vip/v1",
    default_model: "cattoken-gpt",
    supported_models: ["cattoken-gpt"],
    is_enabled: true,
    configured: true,
    masked_api_key: "••••CTO1",
    last_test_status: "success",
    last_tested_at: null,
    last_test_message: "CatToken OpenAI connection successful",
    updated_at: null,
  },
  {
    slug: "cattoken_claude",
    api_protocol: "anthropic",
    display_name: "CatToken Claude",
    role: "primary",
    base_url: "https://www.cattoken.vip",
    default_model: "cattoken-claude",
    supported_models: ["cattoken-claude", "cattoken-claude-fast"],
    is_enabled: true,
    configured: true,
    masked_api_key: "••••CTC1",
    last_test_status: "success",
    last_tested_at: null,
    last_test_message: "CatToken Claude connection successful",
    updated_at: null,
  },
];

const server = setupServer(
  http.get("http://localhost:8000/api/v1/settings/providers", () =>
    HttpResponse.json(providers)
  )
);

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

it("hides retired CatToken providers even if an older API still returns them", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  expect(await screen.findByRole("tab", { name: "OpenAI" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "CatToken OpenAI" })).not.toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "CatToken Claude" })).not.toBeInTheDocument();
});

function Wrapper({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      {children}
    </QueryClientProvider>
  );
}

it("keeps the stored key masked until replacement is requested", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  expect(await screen.findByText("••••4F2A")).toBeInTheDocument();
  expect(screen.queryByLabelText("新 API Key")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "替换密钥" }));

  expect(screen.getByLabelText("新 API Key")).toHaveAttribute("type", "password");
});

it("clears a stale model verification error after the provider saves successfully", async () => {
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/openai/models/verify",
      () => HttpResponse.json(
        {
          detail: {
            code: "PROVIDER_NOT_CONFIGURED",
            message: "请先保存供应商配置和 API Key",
            retryable: false,
          },
        },
        { status: 422 }
      )
    ),
    http.put(
      "http://localhost:8000/api/v1/settings/providers/openai",
      () => HttpResponse.json(providers[0])
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click((await screen.findAllByRole("button", { name: "重新验证" }))[0]);
  expect(await screen.findByRole("alert")).toHaveTextContent("请先保存供应商配置和 API Key");

  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));

  expect(await screen.findByRole("status")).toHaveTextContent("配置已保存");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("clears the replacement key and restores its mask after a successful save", async () => {
  const savedBodies: Array<Record<string, unknown>> = [];
  server.use(
    http.put(
      "http://localhost:8000/api/v1/settings/providers/openai",
      async ({ request }) => {
        savedBodies.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({
          ...providers[0],
          masked_api_key: "••••NEW1",
        });
      }
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("button", { name: "替换密钥" }));
  await userEvent.type(screen.getByLabelText("新 API Key"), "temporary-key-value");
  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));

  expect(await screen.findByText("••••NEW1")).toBeInTheDocument();
  expect(screen.queryByLabelText("新 API Key")).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await waitFor(() => expect(savedBodies).toHaveLength(2));
  expect(savedBodies[0].api_key).toBe("temporary-key-value");
  expect(savedBodies[1].api_key).toBeUndefined();
});

it("labels DeepSeek as the secondary verification provider", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "DeepSeek" }));

  expect(screen.getByText("二次验证")).toBeInTheDocument();
});

it.skip("keeps CatToken OpenAI and CatToken Claude settings independent", async () => {
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/cattoken_claude/test",
      () =>
        HttpResponse.json({
          status: "success",
          message: "CatToken Claude tested",
          models: ["cattoken-claude", "cattoken-claude-fast"],
        })
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "CatToken OpenAI" }));
  expect(screen.getByDisplayValue("https://www.cattoken.vip/v1")).toBeInTheDocument();
  expect(screen.getByText("固定协议：OpenAI 兼容")).toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "OpenAI 兼容" })).not.toBeInTheDocument();
  expect(screen.getByText("••••CTO1")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "CatToken Claude" }));
  expect(screen.getByDisplayValue("https://www.cattoken.vip")).toBeInTheDocument();
  expect(screen.getByDisplayValue("cattoken-claude")).toBeInTheDocument();
  expect(screen.getByText("固定协议：Anthropic 兼容")).toBeInTheDocument();
  expect(screen.queryByRole("radio", { name: "Anthropic 兼容" })).not.toBeInTheDocument();
  expect(screen.getByText("••••CTC1")).toBeInTheDocument();
  expect(screen.getAllByText("CatToken Claude connection successful").length).toBeGreaterThan(0);

  await userEvent.selectOptions(
    screen.getByLabelText("默认模型"),
    "cattoken-claude-fast"
  );
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByText("CatToken Claude tested")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "CatToken OpenAI" }));
  expect(screen.getByDisplayValue("cattoken-gpt")).toBeInTheDocument();
  expect(screen.getByText("••••CTO1")).toBeInTheDocument();
  expect(screen.getAllByText("CatToken OpenAI connection successful").length).toBeGreaterThan(0);
});

it.skip("ignores a late CatToken Claude test response after switching to CatToken OpenAI", async () => {
  let releaseResponse: (() => void) | undefined;
  let markRequestStarted: (() => void) | undefined;
  const responseGate = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  const requestStarted = new Promise<void>((resolve) => {
    markRequestStarted = resolve;
  });
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/cattoken_claude/test",
      async () => {
        markRequestStarted?.();
        await responseGate;
        return HttpResponse.json({
          status: "success",
          message: "Synthetic late Claude success",
          models: ["synthetic-late-claude-model"],
        });
      }
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "CatToken Claude" }));
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  await requestStarted;
  await userEvent.click(screen.getByRole("tab", { name: "CatToken OpenAI" }));

  await act(async () => {
    releaseResponse?.();
    await responseGate;
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(screen.getByDisplayValue("https://www.cattoken.vip/v1")).toBeInTheDocument();
  expect(screen.getByDisplayValue("cattoken-gpt")).toBeInTheDocument();
  expect(screen.getByText("••••CTO1")).toBeInTheDocument();
  expect(screen.queryByText(/synthetic-late-claude-model$/)).not.toBeInTheDocument();
  expect(screen.queryByText("Synthetic late Claude success")).not.toBeInTheDocument();
  expect(screen.getAllByText("CatToken OpenAI connection successful").length).toBeGreaterThan(0);
});

it.skip("clears a synthetic CatToken Claude key draft when switching to CatToken OpenAI", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "CatToken Claude" }));
  await userEvent.click(screen.getByRole("button", { name: "替换密钥" }));
  await userEvent.type(
    screen.getByLabelText("新 API Key"),
    "synthetic-cattoken-claude-draft"
  );

  await userEvent.click(screen.getByRole("tab", { name: "CatToken OpenAI" }));

  expect(screen.queryByDisplayValue("synthetic-cattoken-claude-draft")).not.toBeInTheDocument();
  expect(screen.getByText("••••CTO1")).toBeInTheDocument();
  expect(screen.getByDisplayValue("cattoken-gpt")).toBeInTheDocument();
  expect(screen.getAllByText("CatToken OpenAI connection successful").length).toBeGreaterThan(0);
});

it.skip("keeps the current OpenAI draft when a CatToken Claude save finishes late", async () => {
  let providerListRequestCount = 0;
  let releaseResponse: (() => void) | undefined;
  let markRequestStarted: (() => void) | undefined;
  const responseGate = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  const requestStarted = new Promise<void>((resolve) => {
    markRequestStarted = resolve;
  });
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () => {
      providerListRequestCount += 1;
      return HttpResponse.json(providers);
    }),
    http.put(
      "http://localhost:8000/api/v1/settings/providers/cattoken_claude",
      async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        markRequestStarted?.();
        await responseGate;
        return HttpResponse.json({
          ...providers[4],
          base_url: body.base_url,
          default_model: body.default_model,
          masked_api_key: "••••SYN1",
        });
      }
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "CatToken Claude" }));
  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await requestStarted;
  await userEvent.click(screen.getByRole("tab", { name: "CatToken OpenAI" }));

  fireEvent.change(screen.getByDisplayValue("https://www.cattoken.vip/v1"), {
    target: { value: "https://synthetic-openai-draft.invalid/v1" },
  });
  await userEvent.click(screen.getByRole("button", { name: "替换密钥" }));
  await userEvent.type(
    screen.getByLabelText("新 API Key"),
    "synthetic-openai-save-draft"
  );

  await act(async () => {
    releaseResponse?.();
    await responseGate;
    await new Promise((resolve) => setTimeout(resolve, 25));
  });

  expect(
    screen.getByDisplayValue("https://synthetic-openai-draft.invalid/v1")
  ).toBeInTheDocument();
  expect(screen.getByDisplayValue("cattoken-gpt")).toBeInTheDocument();
  expect(screen.getByDisplayValue("synthetic-openai-save-draft")).toBeInTheDocument();
  expect(screen.queryByText("••••SYN1")).not.toBeInTheDocument();
  expect(screen.queryByText("配置已保存")).not.toBeInTheDocument();
  expect(screen.getAllByText("CatToken OpenAI connection successful").length).toBeGreaterThan(0);
  expect(providerListRequestCount).toBe(1);
});

it("retains form values after a failed connection test", async () => {
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/openai/test",
      () =>
        HttpResponse.json(
          {
            detail: {
              code: "PROVIDER_AUTH_FAILED",
              message: "认证失败",
              retryable: false,
            },
          },
          { status: 422 }
        )
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });
  const endpoint = await screen.findByDisplayValue("https://api.openai.com/v1");
  fireEvent.change(endpoint, { target: { value: "https://api.openai.com/custom-v1" } });

  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("认证失败");
  await waitFor(() => expect(endpoint).toHaveValue("https://api.openai.com/custom-v1"));
});

it("tests and saves without a visible default-model selector", async () => {
  let requestBody: Record<string, unknown> | undefined;
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/openai/test",
      () =>
        HttpResponse.json({
          status: "success",
          message: "Connection successful",
          models: ["gpt-4o", "gpt-4.1", "gpt-5.4"],
        })
    ),
    http.put(
      "http://localhost:8000/api/v1/settings/providers/openai",
      async ({ request }) => {
        requestBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...providers[0],
          default_model: requestBody.default_model,
          supported_models: ["gpt-4o", "gpt-4.1", "gpt-5.4"],
        });
      }
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("button", { name: "测试连接" }));
  expect(await screen.findByText("连接成功")).toBeInTheDocument();
  expect(await screen.findByText("OpenAI · OpenAI 兼容 · gpt-5.4")).toBeInTheDocument();
  expect(screen.queryByLabelText("默认模型")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));

  await waitFor(() => expect(requestBody?.default_model).toBe("gpt-4o"));
});

it("shows model identities and cross-review readiness", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  expect(await screen.findByText("OpenAI · OpenAI 兼容 · gpt-4o")).toBeInTheDocument();
  expect(screen.getAllByText("历史验证通过").length).toBeGreaterThan(0);
});

it("explains custom OpenAI compatibility and shows the verified request mode", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([
        ...providers.slice(0, 2),
        {
          ...providers[2],
          model_options: [{
            ...providers[2].model_options![0],
            transport_mode: "chat_completions",
            structured_output_mode: "json_schema",
          }],
        },
      ])
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "自定义 API" }));

  expect(screen.getByText(/POST \/v1\/chat\/completions 或 POST \/v1\/responses/)).toBeInTheDocument();
  expect(screen.getByText(/可填写基础地址、\/v1 或完整接口地址/)).toBeInTheDocument();
  expect(screen.getByText(/连接检测和模型验证会消耗少量 Token/)).toBeInTheDocument();
  expect(screen.getByText(/配置不变时不会定时重复验证/)).toBeInTheDocument();
  expect(screen.getByText("Chat Completions · JSON Schema")).toBeInTheDocument();
});

it("tests and saves a custom provider with the selected Anthropic protocol", async () => {
  let testedBody: Record<string, unknown> | undefined;
  let savedBody: Record<string, unknown> | undefined;
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/custom/test",
      async ({ request }) => {
        testedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "success",
          message: "Connection successful",
          models: ["claude-sonnet"],
        });
      }
    ),
    http.put(
      "http://localhost:8000/api/v1/settings/providers/custom",
      async ({ request }) => {
        savedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...providers[2],
          api_protocol: savedBody.api_protocol,
          default_model: savedBody.default_model,
          supported_models: ["claude-sonnet"],
        });
      }
    ),
    http.post(
      "http://localhost:8000/api/v1/settings/providers/custom/models/verify",
      async ({ request }) => {
        const body = await request.json() as { model: string };
        return HttpResponse.json({
          provider: "custom",
          model: body.model,
          is_default: false,
          test_status: "verified",
          tested_at: new Date().toISOString(),
          test_message: "Automatic verification succeeded",
          error_code: null,
        });
      }
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "自定义 API" }));
  await userEvent.click(screen.getByRole("radio", { name: "Anthropic 兼容" }));
  expect(screen.getByText(/POST \/v1\/messages/)).toBeInTheDocument();
  expect(screen.getByText(/可填写基础地址、\/v1 或完整的 \/v1\/messages 地址/)).toBeInTheDocument();
  expect(screen.getByText(/自动验证.*消耗少量 Token/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));

  await waitFor(() => expect(testedBody?.api_protocol).toBe("anthropic"));
  expect(await screen.findByText("连接成功")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));
  await waitFor(() => expect(savedBody?.api_protocol).toBe("anthropic"));
});

it("invalidates a successful custom connection test when the protocol changes", async () => {
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/custom/test",
      () =>
        HttpResponse.json({
          status: "success",
          message: "Connection successful",
          models: ["model-x"],
        })
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "自定义 API" }));
  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));
  expect(await screen.findByText("连接成功")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("radio", { name: "Anthropic 兼容" }));

  expect(screen.queryByText("连接成功")).not.toBeInTheDocument();
  expect(screen.queryByText(/发现 .* 个可用模型/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "保存配置" })).not.toBeDisabled();
});

it("warns when a custom provider protocol differs from the saved protocol", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "自定义 API" }));
  await userEvent.click(screen.getByRole("radio", { name: "Anthropic 兼容" }));

  expect(screen.getByRole("alert")).toHaveTextContent(
    "Claude 模型名称不代表接口使用 Anthropic 协议"
  );
  expect(screen.getByRole("alert")).toHaveTextContent(
    "已保存协议：OpenAI 兼容"
  );
});

it("invalidates the saved model catalog when an OpenAI endpoint changes", async () => {
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await screen.findByDisplayValue("https://api.openai.com/v1");
  expect(screen.getByRole("button", { name: "保存配置" })).not.toBeDisabled();

  fireEvent.change(screen.getByDisplayValue("https://api.openai.com/v1"), {
    target: { value: "https://api.openai.com/v2" },
  });

  expect(screen.getByRole("button", { name: "保存配置" })).not.toBeDisabled();
  expect(screen.getByText(/尚未发现.*模型/)).toBeInTheDocument();
});

it("clears the visible model catalog when a provider test fails", async () => {
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/custom/test",
      () =>
        HttpResponse.json(
          {
            detail: {
              code: "PROVIDER_MODEL_INVALID",
              message: "The configured model was not found or is unavailable",
              retryable: false,
            },
          },
          { status: 422 }
        )
    )
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });
  await userEvent.click(await screen.findByRole("tab", { name: "自定义 API" }));
  expect(screen.getByText(/自定义 API · OpenAI 兼容 · model-x/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "测试连接" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "The configured model was not found or is unavailable"
  );
  await waitFor(() => {
    expect(screen.queryByText(/自定义 API · OpenAI 兼容 · model-x/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText("默认模型")).not.toBeInTheDocument();
  });
});

it("paginates a large model catalog ten models at a time", async () => {
  const supportedModels = Array.from({ length: 21 }, (_, index) => `catalog-model-${index + 1}`);
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([
        {
          ...providers[0],
          default_model: supportedModels[0],
          supported_models: supportedModels,
          model_options: supportedModels.map((model) => ({
            provider: "openai",
            provider_display_name: "OpenAI",
            api_protocol: "openai",
            model,
            is_default: model === supportedModels[0],
            is_enabled: true,
            test_status: "discovered",
            tested_at: null,
            test_message: "目录发现，尚未真实验证",
          })),
        },
        ...providers.slice(1),
      ])
    )
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  const catalog = await screen.findByRole("region", { name: "模型目录" });
  expect(within(catalog).getByText(/catalog-model-1$/)).toBeInTheDocument();
  expect(within(catalog).getByText(/catalog-model-10$/)).toBeInTheDocument();
  expect(within(catalog).queryByText(/catalog-model-11$/)).not.toBeInTheDocument();
  expect(within(catalog).getByText("第 1 / 3 页")).toBeInTheDocument();

  await userEvent.click(within(catalog).getByRole("button", { name: "下一页" }));

  expect(within(catalog).queryByText(/catalog-model-1$/)).not.toBeInTheDocument();
  expect(within(catalog).getByText(/catalog-model-11$/)).toBeInTheDocument();
  expect(within(catalog).getByText(/catalog-model-20$/)).toBeInTheDocument();
  expect(within(catalog).queryByText(/catalog-model-21$/)).not.toBeInTheDocument();
  expect(within(catalog).getByText("第 2 / 3 页")).toBeInTheDocument();
});

it("moves a successfully verified model to the first catalog page", async () => {
  const supportedModels = Array.from({ length: 21 }, (_, index) => `catalog-model-${index + 1}`);
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([
        {
          ...providers[0],
          default_model: supportedModels[0],
          supported_models: supportedModels,
          model_options: supportedModels.map((model) => ({
            provider: "openai",
            provider_display_name: "OpenAI",
            api_protocol: "openai",
            model,
            is_default: model === supportedModels[0],
            is_enabled: true,
            test_status: "discovered",
            tested_at: null,
            test_message: "目录发现，尚未真实验证",
          })),
        },
        ...providers.slice(1),
      ])
    ),
    http.post("http://localhost:8000/api/v1/settings/providers/openai/models/verify", async ({ request }) => {
      const body = await request.json() as { model: string };
      return HttpResponse.json({
        provider: "openai",
        model: body.model,
        is_default: false,
        test_status: "verified",
        tested_at: new Date().toISOString(),
        test_message: "结构化验证成功",
        error_code: null,
      });
    })
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  const catalog = await screen.findByRole("region", { name: "模型目录" });
  await userEvent.click(within(catalog).getByRole("button", { name: "下一页" }));
  const modelElevenCard = within(catalog).getByText(/catalog-model-11$/).closest("div.rounded-md");
  expect(modelElevenCard).not.toBeNull();
  await userEvent.click(within(modelElevenCard as HTMLElement).getByRole("button", { name: "验证此模型" }));

  await waitFor(() => {
    expect(within(catalog).getByText("第 1 / 3 页")).toBeInTheDocument();
  });
  const firstCard = within(catalog).getByText(/catalog-model-11$/).closest("div.rounded-md");
  expect(firstCard).not.toBeNull();
  expect(within(firstCard as HTMLElement).getByText("历史验证通过")).toBeInTheDocument();
  expect(within(catalog).queryByText(/catalog-model-10$/)).not.toBeInTheDocument();
});

it("removes the default-model control and lets verified models be selected", async () => {
  let selectionBody: unknown;
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([{
        ...providers[0],
        model_options: [{
          provider: "openai",
          provider_display_name: "OpenAI",
          api_protocol: "openai",
          model: "gpt-4o",
          is_default: true,
          is_selected: false,
          is_enabled: true,
          test_status: "verified",
          tested_at: new Date().toISOString(),
          test_message: "结构化验证成功",
        }],
      }, ...providers.slice(1)])
    ),
    http.patch("http://localhost:8000/api/v1/settings/providers/openai/models/gpt-4o/selection", async ({ request }) => {
      selectionBody = await request.json();
      return HttpResponse.json({ provider: "openai", model: "gpt-4o", is_selected: true });
    })
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  expect(await screen.findByRole("region", { name: "模型目录" })).toBeInTheDocument();
  expect(screen.queryByLabelText("默认模型")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: "使用 gpt-4o" }));
  await waitFor(() => expect(selectionBody).toEqual({ is_selected: true }));
  expect(await screen.findByRole("status")).toHaveTextContent("模型选择已自动保存");
});

it("searches the whole model catalog without making the user flip pages", async () => {
  const supportedModels = [
    ...Array.from({ length: 20 }, (_, index) => `catalog-model-${index + 1}`),
    "gpt-5.6-sol",
  ];
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([{
        ...providers[0],
        supported_models: supportedModels,
        model_options: supportedModels.map((model) => ({
          provider: "openai",
          provider_display_name: "OpenAI",
          api_protocol: "openai",
          model,
          is_default: false,
          is_enabled: true,
          test_status: "discovered",
          tested_at: null,
          test_message: null,
        })),
      }, ...providers.slice(1)])
    )
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });
  const catalog = await screen.findByRole("region", { name: "模型目录" });
  await userEvent.type(within(catalog).getByRole("searchbox", { name: "搜索模型" }), "GPT-5.6");

  expect(within(catalog).getByText(/gpt-5.6-sol$/i)).toBeInTheDocument();
  expect(within(catalog).queryByText(/catalog-model-1$/)).not.toBeInTheDocument();
  expect(within(catalog).queryByRole("navigation", { name: "模型目录分页" })).not.toBeInTheDocument();
});

it("shows the ten latest used models from the recent-model button", async () => {
  const supportedModels = Array.from({ length: 12 }, (_, index) => `recent-model-${index + 1}`);
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([{
        ...providers[0],
        supported_models: supportedModels,
        model_options: supportedModels.map((model, index) => ({
          provider: "openai",
          provider_display_name: "OpenAI",
          api_protocol: "openai",
          model,
          is_default: false,
          is_enabled: true,
          test_status: "discovered",
          tested_at: null,
          test_message: null,
          last_used_at: `2026-08-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
          use_count: index + 1,
        })),
      }, ...providers.slice(1)])
    )
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });
  const catalog = await screen.findByRole("region", { name: "模型目录" });
  await userEvent.click(within(catalog).getByRole("button", { name: "最近使用模型" }));

  expect(within(catalog).getByText(/recent-model-12$/)).toBeInTheDocument();
  expect(within(catalog).getByText(/recent-model-3$/)).toBeInTheDocument();
  expect(within(catalog).queryByText(/recent-model-2$/)).not.toBeInTheDocument();
  expect(within(catalog).getByText("共 10 个模型")).toBeInTheDocument();
});

it("does not verify models merely because the settings page was opened", async () => {
  const options = Array.from({ length: 12 }, (_, index) => ({
    provider: "openai",
    provider_display_name: "OpenAI",
    api_protocol: "openai",
    model: `auto-model-${index + 1}`,
    is_default: false,
    is_selected: index === 0,
    is_enabled: true,
    test_status: "verified",
    tested_at: "2026-07-01T00:00:00Z",
    test_message: "历史验证成功",
    last_used_at: `2026-08-${String(index + 1).padStart(2, "0")}T00:00:00Z`,
    use_count: index + 1,
    is_current_connection: true,
    current_connection_revision: 3,
  }));
  const verified: string[] = [];
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([{
        ...providers[0],
        validation_revision: 3,
        supported_models: options.map((option) => option.model),
        model_options: options,
      }, ...providers.slice(1)])
    ),
    http.post("http://localhost:8000/api/v1/settings/providers/openai/models/verify", async ({ request }) => {
      const body = await request.json() as { model: string };
      verified.push(body.model);
      return HttpResponse.json({
        provider: "openai",
        model: body.model,
        is_default: false,
        test_status: "verified",
        tested_at: new Date().toISOString(),
        test_message: "自动验证成功",
        error_code: null,
      });
    })
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  expect(await screen.findByText(/auto-model-1$/)).toBeInTheDocument();
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(verified).toHaveLength(0);
});

it("automatically verifies the default model once after a changed connection is saved", async () => {
  const verified: string[] = [];
  server.use(
    http.put("http://localhost:8000/api/v1/settings/providers/openai", () =>
      HttpResponse.json({
        ...providers[0],
        base_url: "https://gateway.example/v1",
        last_test_status: "untested",
        supported_models: [],
        model_options: (providers[0].model_options ?? []).map((option) => ({
          ...option,
          is_current_connection: false,
          current_connection_revision: 2,
          connection_revision: 1,
        })),
      })
    ),
    http.post("http://localhost:8000/api/v1/settings/providers/openai/models/verify", async ({ request }) => {
      const body = await request.json() as { model: string; is_automatic?: boolean };
      verified.push(body.model);
      expect(body.is_automatic).toBe(true);
      return HttpResponse.json({
        provider: "openai",
        model: body.model,
        is_default: true,
        test_status: "verified",
        tested_at: new Date().toISOString(),
        test_message: "Automatic verification succeeded",
        error_code: null,
      });
    })
  );

  render(<ProviderSettingsPanel />, { wrapper: Wrapper });
  fireEvent.change(await screen.findByDisplayValue("https://api.openai.com/v1"), {
    target: { value: "https://gateway.example/v1" },
  });
  await userEvent.click(screen.getByRole("button", { name: "保存配置" }));

  await waitFor(() => expect(verified).toEqual(["gpt-4o"]));
});

it.skip("requires an unconfigured CatToken Claude provider to pass a connection test before enabling", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([
        ...providers.slice(0, 4),
        {
          ...providers[4],
          is_enabled: false,
          configured: false,
          masked_api_key: null,
          last_test_status: "untested",
        },
      ])
    )
  );
  render(<ProviderSettingsPanel />, { wrapper: Wrapper });

  await userEvent.click(await screen.findByRole("tab", { name: "CatToken Claude" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "启用" }));

  expect(screen.getByRole("button", { name: "保存配置" })).toBeDisabled();
  expect(screen.getByText("连接参数已变化，请先重新测试再保存。")).toBeInTheDocument();
});
