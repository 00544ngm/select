import { z } from "zod";

const PLATFORM_PATTERNS = [
  /^https:\/\/(?:www\.)?walmart\.com\//i,
  /^https:\/\/(?:www\.)?amazon\.com\//i,
];

export function isKnownPlatform(url: string): boolean {
  return PLATFORM_PATTERNS.some((p) => p.test(url));
}

export function isLookalikeHost(url: string): boolean {
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.replace(/^www\./, "");
    return (
      hostname.includes("walmart.com.") ||
      hostname.includes("amazon.com.") ||
      (hostname.includes("walmart") && !hostname.endsWith("walmart.com")) ||
      (hostname.includes("amazon") && !hostname.endsWith("amazon.com"))
    );
  } catch {
    return false;
  }
}

export const urlField = z
  .string()
  .min(1, "请输入商品链接")
  .url("请输入有效的 URL")
  .refine((u) => u.startsWith("https://"), { message: "仅支持 HTTPS 链接" })
  .refine((u) => !isLookalikeHost(u), { message: "域名不合法，请检查链接" })
  .refine((u) => isKnownPlatform(u), { message: "不支持的平台，仅支持 Walmart 和 Amazon" });

export const nameField = z.string().max(100, "名称最多 100 个字符").optional();

export const hypothesisSchema = z.object({
  name: nameField,
  url: urlField,
  model: z.string().optional(),
  provider: z.string().optional(),
  rotation_enabled: z.boolean().optional(),
  rotation_candidates: z.array(z.object({
    provider: z.string(), model: z.string(), api_protocol: z.string(), connection_revision: z.number(),
  })).optional(),
});

export const judgmentSchema = z.object({
  name: nameField,
  aUrl: urlField,
  bUrls: z.array(urlField).min(1, "至少需要 1 个 B 商品链接").max(50, "最多 50 个 B 商品链接"),
  model: z.string().optional(),
  provider: z.string().optional(),
  rotation_enabled: z.boolean().optional(),
  rotation_candidates: z.array(z.object({
    provider: z.string(), model: z.string(), api_protocol: z.string(), connection_revision: z.number(),
  })).optional(),
});

export type HypothesisFormData = z.infer<typeof hypothesisSchema>;
export type JudgmentFormData = z.infer<typeof judgmentSchema>;
