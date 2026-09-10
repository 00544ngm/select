import { afterAll, beforeAll, expect, it } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { listProviders, testProvider, updateProvider, verifyProviderModel } from "@/lib/api/providers";
import { providerModelOptions, formatModelIdentity } from "@/lib/model-identity";

const provider = {
  slug: "openai" as const,
  api_protocol: "openai" as const,
  display_name: "OpenAI",
  role: "primary" as const,
  base_url: "https://api.openai.com/v1",
  default_model: "gpt-4o",
  supported_models: ["gpt-4o", "gpt-4.1"],
  is_enabled: true,
  configured: true,
  masked_api_key: "••••4F2A",
  last_test_status: "success" as const,
  last_tested_at: null,
  last_test_message: "Connection successful",
  updated_at: null,
};

const server = setupServer();

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterAll(() => server.close());

it("lists masked provider configurations", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([provider])
    )
  );

  const result = await listProviders();

  expect(result[0].masked_api_key).toBe("••••4F2A");
});

it("updates a provider without sending the masked key", async () => {
  let requestBody: unknown;
  server.use(
    http.put(
      "http://localhost:8000/api/v1/settings/providers/openai",
      async ({ request }) => {
        requestBody = await request.json();
        return HttpResponse.json(provider);
      }
    )
  );

  await updateProvider("openai", {
    api_protocol: "openai",
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
    is_enabled: true,
  });

  expect(requestBody).toEqual({
    api_protocol: "openai",
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
    is_enabled: true,
  });
  expect(JSON.stringify(requestBody)).not.toContain("••••4F2A");
});

it("tests a provider draft without saving it", async () => {
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/openai/test",
      () => HttpResponse.json({
        status: "success",
        message: "Connection successful",
        models: ["gpt-4o", "gpt-4.1"],
      })
    )
  );

  const result = await testProvider("openai", {
    api_protocol: "openai",
    base_url: "https://api.openai.com/v1",
    default_model: "gpt-4o",
  });

  expect(result.status).toBe("success");
  expect(result.models).toEqual(["gpt-4o", "gpt-4.1"]);
});

it("verifies one model through the structured task path", async () => {
  const requestBodies: unknown[] = [];
  server.use(
    http.post(
      "http://localhost:8000/api/v1/settings/providers/openai/models/verify",
      async ({ request }) => {
        requestBodies.push(await request.json());
        return HttpResponse.json({
          provider: "openai",
          model: "gpt-4o",
          test_status: "verified",
          tested_at: new Date().toISOString(),
          test_message: "结构化验证成功",
          error_code: null,
          is_default: true,
        });
      }
    )
  );

  const result = await verifyProviderModel("openai", "gpt-4o");
  await verifyProviderModel("openai", "gpt-4o", false, true);

  expect(requestBodies).toEqual([
    { model: "gpt-4o", set_default: false },
    { model: "gpt-4o", set_default: false, is_automatic: true },
  ]);
  expect(result.test_status).toBe("verified");
});

it("formats tested provider models as a reusable catalog", async () => {
  server.use(
    http.get("http://localhost:8000/api/v1/settings/providers", () =>
      HttpResponse.json([provider])
    )
  );

  const options = providerModelOptions(await listProviders());
  expect(options).toHaveLength(2);
  expect(options[0]).toMatchObject({ provider: "openai", model: "gpt-4o", test_status: "discovered" });
  expect(formatModelIdentity(options[0])).toBe("OpenAI · OpenAI 兼容 · gpt-4o");
});
