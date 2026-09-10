import { apiFetch } from "./client";
import type { UserRole, UserStatus } from "./auth";

export interface ApiGroup {
  id: string;
  name: string;
  status: UserStatus;
  note: string | null;
  base_url: string | null;
  masked_api_key: string | null;
  default_model: string | null;
  supported_models: string[];
  member_count: number;
  created_at: string;
  updated_at: string;
}

export interface AdminUser {
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

export interface ApiGroupCreatePayload {
  name: string;
  note?: string;
  base_url?: string;
  api_key?: string;
  default_model?: string;
  supported_models?: string[];
}

export interface ApiGroupUpdatePayload {
  name?: string;
  status?: UserStatus;
  note?: string;
  base_url?: string;
  api_key?: string;
  clear_api_key?: boolean;
  default_model?: string;
  supported_models?: string[];
}

export interface UserCreatePayload {
  username: string;
  password: string;
  full_name?: string;
  role: UserRole;
  status: UserStatus;
  api_group_id?: string | null;
}

export interface UserUpdatePayload {
  full_name?: string;
  role?: UserRole;
  status?: UserStatus;
  api_group_id?: string | null;
}

export function listApiGroups(): Promise<ApiGroup[]> {
  return apiFetch<ApiGroup[]>("/admin/api-groups");
}

export function createApiGroup(payload: ApiGroupCreatePayload): Promise<ApiGroup> {
  return apiFetch<ApiGroup>("/admin/api-groups", { method: "POST", body: payload });
}

export function updateApiGroup(
  id: string,
  payload: ApiGroupUpdatePayload
): Promise<ApiGroup> {
  return apiFetch<ApiGroup>(`/admin/api-groups/${id}`, {
    method: "PUT",
    body: payload,
  });
}

export function disableApiGroup(id: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/admin/api-groups/${id}`, { method: "DELETE" });
}

export function listUsers(): Promise<AdminUser[]> {
  return apiFetch<AdminUser[]>("/admin/users");
}

export function createUser(payload: UserCreatePayload): Promise<AdminUser> {
  return apiFetch<AdminUser>("/admin/users", { method: "POST", body: payload });
}

export function updateUser(
  id: string,
  payload: UserUpdatePayload
): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${id}`, { method: "PUT", body: payload });
}

export function resetUserPassword(
  id: string,
  newPassword: string
): Promise<AdminUser> {
  return apiFetch<AdminUser>(`/admin/users/${id}/reset-password`, {
    method: "POST",
    body: { new_password: newPassword },
  });
}

export function deleteUser(id: string): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>(`/admin/users/${id}`, { method: "DELETE" });
}
