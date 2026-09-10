import { z } from "zod";

export const providerSettingsSchema = z.object({
  apiProtocol: z.enum(["openai", "anthropic"]),
  displayName: z.string().max(80, "服务名称最多 80 个字符").optional(),
  baseUrl: z
    .string()
    .url("请输入有效的服务地址")
    .refine((value) => {
      const parsed = new URL(value);
      return parsed.protocol === "https:" || ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname);
    }, "服务地址必须使用 HTTPS"),
  defaultModel: z.string().min(1, "请输入默认模型").max(120, "模型名称最多 120 个字符"),
  apiKey: z.string().optional(),
  isEnabled: z.boolean(),
});

export type ProviderSettingsFormData = z.infer<typeof providerSettingsSchema>;
