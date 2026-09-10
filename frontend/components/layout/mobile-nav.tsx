"use client";

import { useState } from "react";
import {
  FileText,
  History,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  UsersRound,
  X,
} from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/components/auth/auth-context";

const baseNavItems = [
  { href: "/", label: "工作台", icon: LayoutDashboard },
  { href: "/history", label: "历史记录", icon: History },
  { href: "/results", label: "结果展示", icon: FileText },
];

const adminNavItems = [
  { href: "/admin", label: "账户管理", icon: UsersRound },
  { href: "/settings/api", label: "API 设置", icon: KeyRound },
];

export default function MobileNav() {
  const [open, setOpen] = useState(false);
  const { isAdmin, logout } = useAuth();
  const navItems = isAdmin ? [...baseNavItems, ...adminNavItems] : baseNavItems;

  return (
    <>
      <button
        type="button"
        className="flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-muted md:hidden"
        onClick={() => setOpen(true)}
        aria-label="打开菜单"
      >
        <Menu className="h-5 w-5" />
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 md:hidden"
          role="dialog"
          aria-modal="true"
        >
          <div
            className="fixed inset-0 bg-black/50"
            onClick={() => setOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 flex w-64 flex-col bg-navigation text-navigation-foreground shadow-lg">
            <div className="flex h-14 items-center justify-between border-b border-white/10 px-4">
              <span className="text-sm font-semibold">组合选品控制台</span>
              <button
                type="button"
                className="rounded-md p-1 text-navigation-foreground/70 hover:bg-white/10 hover:text-navigation-foreground"
                onClick={() => setOpen(false)}
                aria-label="关闭菜单"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <nav className="flex-1 space-y-1 p-3">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-navigation-foreground/70 transition-colors hover:bg-white/10 hover:text-navigation-foreground"
                  onClick={() => setOpen(false)}
                >
                  <item.icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </Link>
              ))}
            </nav>
            <div className="border-t border-white/10 p-3">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  logout();
                }}
                className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-navigation-foreground/70 transition-colors hover:bg-white/10 hover:text-navigation-foreground"
              >
                <LogOut className="h-4 w-4 shrink-0" />
                <span>退出登录</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
