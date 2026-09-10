import { apiFetch } from "./client";

export type UserRole = "admin" | "employee";
export type UserStatus = "active" | "disabled";

export interface AuthUser {
  id: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  full_name: string | null;
  api_group_id: string | null;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

export interface MeResponse {
  user: AuthUser;
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return apiFetch<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
  });
}

export function me(): Promise<MeResponse> {
  return apiFetch<MeResponse>("/auth/me");
}

export function changePassword(
  newPassword: string,
  currentPassword?: string
): Promise<MeResponse> {
  return apiFetch<MeResponse>("/auth/change-password", {
    method: "POST",
    body: {
      new_password: newPassword,
      ...(currentPassword ? { current_password: currentPassword } : {}),
    },
  });
}
