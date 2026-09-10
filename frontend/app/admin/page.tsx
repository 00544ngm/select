"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/components/auth/auth-context";
import {
  createApiGroup,
  createUser,
  deleteUser,
  disableApiGroup,
  listApiGroups,
  listUsers,
  resetUserPassword,
  updateApiGroup,
  updateUser,
  type ApiGroup,
} from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";
import ProviderSettingsPanel from "@/components/settings/provider-settings-panel";

const inputClass =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring";
const selectClass =
  "h-9 rounded-md border border-input bg-background px-2 text-sm outline-none focus:ring-2 focus:ring-ring";

function GroupForm({
  groups,
  initial,
  onSaved,
}: {
  groups: ApiGroup[];
  initial?: ApiGroup | null;
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState(initial?.name ?? "");
  const [note, setNote] = useState(initial?.note ?? "");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () => {
      const payload = { name, note: note || undefined };
      return initial
        ? updateApiGroup(initial.id, payload)
        : createApiGroup(payload);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["api-groups"] });
      onSaved();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "保存失败"),
  });

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="grid gap-2 md:grid-cols-2">
        <input
          className={inputClass}
          placeholder="分组名称（必填）"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className={inputClass}
          placeholder="备注（可选）"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <p className="text-xs text-muted-foreground">
        分组建好后点列表里的「配置 API」给该分组配置专属的服务地址、Key 与模型（员工只能使用，无法修改）。
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={!name.trim() || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          {mutation.isPending ? "保存中…" : initial ? "保存修改" : "新建分组"}
        </Button>
        {initial && (
          <Button size="sm" variant="outline" onClick={onSaved}>
            取消
          </Button>
        )}
      </div>
    </div>
  );
}

function UserForm({
  groups,
  onSaved,
}: {
  groups: ApiGroup[];
  onSaved: () => void;
}) {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<"admin" | "employee">("employee");
  const [status, setStatus] = useState<"active" | "disabled">("active");
  const [apiGroupId, setApiGroupId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      createUser({
        username: username.trim(),
        password,
        full_name: fullName || undefined,
        role,
        status,
        api_group_id: apiGroupId || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      qc.invalidateQueries({ queryKey: ["api-groups"] });
      onSaved();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "创建失败"),
  });

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="grid gap-2 md:grid-cols-3">
        <input
          className={inputClass}
          placeholder="用户名（小写字母/数字/_-）"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className={inputClass}
          type="password"
          placeholder="初始密码（至少 6 位）"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <input
          className={inputClass}
          placeholder="姓名（可选）"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <select
          className={selectClass}
          value={role}
          onChange={(e) => setRole(e.target.value as "admin" | "employee")}
        >
          <option value="employee">员工</option>
          <option value="admin">管理员</option>
        </select>
        <select
          className={selectClass}
          value={status}
          onChange={(e) => setStatus(e.target.value as "active" | "disabled")}
        >
          <option value="active">启用</option>
          <option value="disabled">禁用</option>
        </select>
        <select
          className={selectClass}
          value={apiGroupId}
          onChange={(e) => setApiGroupId(e.target.value)}
        >
          <option value="">未分配接口组</option>
          {groups
            .filter((g) => g.status === "active")
            .map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
        </select>
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button
        size="sm"
        disabled={!username.trim() || password.length < 6 || mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? "创建中…" : "新建成员"}
      </Button>
    </div>
  );
}

export default function AdminPage() {
  const router = useRouter();
  const { isAdmin, loading } = useAuth();
  const qc = useQueryClient();

  const groupsQuery = useQuery({ queryKey: ["api-groups"], queryFn: listApiGroups });
  const usersQuery = useQuery({ queryKey: ["admin-users"], queryFn: listUsers });

  const [editingGroup, setEditingGroup] = useState<ApiGroup | null>(null);
  const [configuringGroup, setConfiguringGroup] = useState<ApiGroup | null>(null);
  const [showGroupForm, setShowGroupForm] = useState(false);
  const [showUserForm, setShowUserForm] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !isAdmin) router.replace("/");
  }, [loading, isAdmin, router]);

  if (loading || !isAdmin) return null;

  const groups = groupsQuery.data ?? [];
  const users = usersQuery.data ?? [];
  const groupName = (id: string | null) =>
    groups.find((g) => g.id === id)?.name ?? "未分配";

  const disableGroup = useMutation({
    mutationFn: disableApiGroup,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["api-groups"] }),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "操作失败"),
  });

  const toggleUserStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "active" | "disabled" }) =>
      updateUser(id, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "操作失败"),
  });

  const assignGroup = useMutation({
    mutationFn: ({ id, apiGroupId }: { id: string; apiGroupId: string | null }) =>
      updateUser(id, { api_group_id: apiGroupId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "分配失败"),
  });

  const resetPassword = useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) => {
      const pwd = password.trim();
      return resetUserPassword(id, pwd);
    },
    onSuccess: () => setActionError(null),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "重置失败"),
  });

  const removeUser = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-users"] }),
    onError: (err) =>
      setActionError(err instanceof ApiError ? err.message : "删除失败"),
  });

  return (
    <div className="mx-auto w-full max-w-5xl p-4 md:p-6">
      <div className="mb-4">
        <h1 className="text-lg font-semibold">账户管理</h1>
        <p className="text-sm text-muted-foreground">
          管理接口分组与员工账号，为员工分配 API 凭据。
        </p>
      </div>

      {actionError && (
        <p className="mb-3 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {actionError}
        </p>
      )}

      <Tabs defaultValue="groups">
        <TabsList>
          <TabsTrigger value="groups">接口分组</TabsTrigger>
          <TabsTrigger value="users">员工账号</TabsTrigger>
        </TabsList>

        <TabsContent value="groups" className="mt-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              共 {groups.length} 个分组
            </span>
            <Button size="sm" onClick={() => setShowGroupForm((v) => !v)}>
              {showGroupForm ? "收起" : "新建分组"}
            </Button>
          </div>

          {showGroupForm && (
            <GroupForm
              groups={groups}
              onSaved={() => setShowGroupForm(false)}
            />
          )}

          {editingGroup && (
            <GroupForm
              groups={groups}
              initial={editingGroup}
              onSaved={() => setEditingGroup(null)}
            />
          )}

          {configuringGroup && (
            <div className="space-y-3 rounded-md border border-border p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold">
                  配置 API：{configuringGroup.name}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setConfiguringGroup(null)}
                >
                  收起
                </Button>
              </div>
              <ProviderSettingsPanel
                key={configuringGroup.id}
                scope={{
                  kind: "group",
                  groupId: configuringGroup.id,
                  groupName: configuringGroup.name,
                }}
              />
            </div>
          )}

          {groupsQuery.isLoading && <p className="text-sm">加载中…</p>}

          <div className="space-y-2">
            {groups.map((group) => (
              <Card key={group.id}>
                <CardContent className="flex flex-wrap items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{group.name}</span>
                      <Badge variant={group.status === "active" ? "default" : "secondary"}>
                        {group.status === "active" ? "启用" : "已禁用"}
                      </Badge>
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {group.note || "（无备注）"} · 点「配置 API」设置该分组的专属服务地址/Key/模型
                    </p>
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {group.member_count} 人使用
                  </span>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setConfiguringGroup(configuringGroup?.id === group.id ? null : group);
                      setEditingGroup(null);
                      setShowGroupForm(false);
                    }}
                  >
                    {configuringGroup?.id === group.id ? "收起配置" : "配置 API"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEditingGroup(group);
                      setConfiguringGroup(null);
                      setShowGroupForm(false);
                    }}
                  >
                    编辑
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => disableGroup.mutate(group.id)}
                  >
                    {group.status === "active" ? "禁用" : "启用"}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="users" className="mt-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              共 {users.length} 个账号
            </span>
            <Button size="sm" onClick={() => setShowUserForm((v) => !v)}>
              {showUserForm ? "收起" : "新建成员"}
            </Button>
          </div>

          {showUserForm && <UserForm groups={groups} onSaved={() => setShowUserForm(false)} />}

          {usersQuery.isLoading && <p className="text-sm">加载中…</p>}

          <div className="space-y-2">
            {users.map((user) => (
              <Card key={user.id}>
                <CardContent className="flex flex-wrap items-center gap-3 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{user.username}</span>
                      <Badge variant={user.role === "admin" ? "default" : "secondary"}>
                        {user.role === "admin" ? "管理员" : "员工"}
                      </Badge>
                      <Badge variant={user.status === "active" ? "outline" : "secondary"}>
                        {user.status === "active" ? "启用" : "禁用"}
                      </Badge>
                      {user.full_name && (
                        <span className="text-xs text-muted-foreground">
                          {user.full_name}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      接口组：{groupName(user.api_group_id)}
                    </p>
                  </div>

                  <select
                    className={selectClass}
                    value={user.api_group_id ?? ""}
                    onChange={(e) =>
                      assignGroup.mutate({
                        id: user.id,
                        apiGroupId: e.target.value || null,
                      })
                    }
                  >
                    <option value="">未分配</option>
                    {groups
                      .filter((g) => g.status === "active")
                      .map((g) => (
                        <option key={g.id} value={g.id}>
                          {g.name}
                        </option>
                      ))}
                  </select>

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      toggleUserStatus.mutate({
                        id: user.id,
                        status: user.status === "active" ? "disabled" : "active",
                      })
                    }
                  >
                    {user.status === "active" ? "禁用" : "启用"}
                  </Button>

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      const pwd = window.prompt("输入新密码（至少 6 位）");
                      if (pwd) resetPassword.mutate({ id: user.id, password: pwd });
                    }}
                  >
                    重置密码
                  </Button>

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      if (window.confirm(`确认删除成员 ${user.username}？`)) {
                        removeUser.mutate(user.id);
                      }
                    }}
                  >
                    删除
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
