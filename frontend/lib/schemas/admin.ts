import { z } from "zod";

export const apiGroupSchema = z.object({
  name: z.string().min(1, "请输入分组名称").max(80, "名称最多 80 个字符"),
  note: z.string().max(500, "备注最多 500 个字符").optional(),
  baseUrl: z.string().max(500, "服务地址最多 500 个字符").optional(),
  apiKey: z.string().optional(),
  defaultModel: z.string().max(120, "默认模型最多 120 个字符").optional(),
  supportedModels: z.string().optional(),
});

export type ApiGroupFormData = z.infer<typeof apiGroupSchema>;

export const userSchema = z.object({
  username: z
    .string()
    .min(2, "用户名至少 2 位")
    .max(32, "用户名最多 32 位")
    .regex(/^[a-z0-9_-]+$/, "只能包含小写字母、数字、下划线或短横线"),
  password: z.string().min(6, "密码至少 6 位").max(128, "密码最多 128 位"),
  fullName: z.string().max(80, "姓名最多 80 个字符").optional(),
  role: z.enum(["admin", "employee"]),
  status: z.enum(["active", "disabled"]),
  apiGroupId: z.string().optional(),
});

export type UserFormData = z.infer<typeof userSchema>;
