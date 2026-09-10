import { z } from "zod";

export const loginSchema = z.object({
  username: z
    .string()
    .min(1, "请输入用户名")
    .max(32, "用户名最多 32 个字符"),
  password: z.string().min(1, "请输入密码"),
});

export type LoginFormData = z.infer<typeof loginSchema>;

export const changePasswordSchema = z
  .object({
    currentPassword: z.string().optional(),
    newPassword: z.string().min(6, "新密码至少 6 位").max(128, "新密码最多 128 位"),
    confirmPassword: z.string(),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "两次输入的新密码不一致",
    path: ["confirmPassword"],
  });

export type ChangePasswordFormData = z.infer<typeof changePasswordSchema>;
