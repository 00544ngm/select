"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/components/auth/auth-context";
import { changePassword, login, type AuthUser } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";

const inputClass =
  "h-9 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring";

export default function LoginPage() {
  const { user, login: persist, refreshUser } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // change-password phase
  const [pendingUser, setPendingUser] = useState<AuthUser | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [changedOk, setChangedOk] = useState(false);

  // An already-logged-in account that still has to set a new password (e.g.
  // after a page refresh while pinned to /login) must land directly on the
  // change-password phase rather than the sign-in form. A logout clears it.
  // Note: do NOT reset pendingUser as soon as must_change_password flips to
  // false — that would flash the sign-in form mid-transition. The AppShell
  // guard navigates away right after the change lands, so keep showing the
  // change card (as a success state) until the page unmounts.
  useEffect(() => {
    if (!user) setPendingUser(null);
    else if (user.must_change_password) setPendingUser(user);
  }, [user]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await login(username.trim(), password);
      persist(res.access_token, res.user);
      if (res.user.must_change_password) {
        setPendingUser(res.user);
      }
      // Otherwise the AppShell session guard redirects /login -> "/" once the
      // session lands. This page must not navigate itself: a second replace()
      // races the guard and can abort the navigation, leaving the user staring
      // at a stale sign-in form.
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "登录失败，请稍后重试");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (newPassword.length < 6) {
      setError("新密码至少 6 位");
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("两次输入的新密码不一致");
      return;
    }
    setSubmitting(true);
    try {
      const res = await changePassword(newPassword);
      refreshUser(res.user);
      setChangedOk(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "修改密码失败");
    } finally {
      setSubmitting(false);
    }
  }

  if (pendingUser) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas p-4">
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>设置新密码</CardTitle>
            <CardDescription>
              首次登录需要设置新密码（账号：{pendingUser.username}）
            </CardDescription>
          </CardHeader>
          <CardContent>
            {changedOk ? (
              <p role="status" className="text-sm font-medium text-success">
                密码已更新，正在进入控制台…
              </p>
            ) : (
              <form onSubmit={handleChangePassword} className="space-y-3">
                <input
                  type="password"
                  placeholder="新密码（至少 6 位）"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className={inputClass}
                  required
                />
                <input
                  type="password"
                  placeholder="确认新密码"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className={inputClass}
                  required
                />
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button type="submit" className="w-full" disabled={submitting}>
                  {submitting ? "提交中…" : "保存并进入"}
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>组合选品控制台</CardTitle>
          <CardDescription>请使用管理员分配的账号登录</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-3">
            <input
              type="text"
              placeholder="用户名"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className={inputClass}
              autoComplete="username"
              required
            />
            <input
              type="password"
              placeholder="密码"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              autoComplete="current-password"
              required
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "登录中…" : "登录"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
