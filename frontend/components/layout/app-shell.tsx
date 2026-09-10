"use client";

import { useState, useEffect, useRef, type ReactNode } from "react";
import { ImagePlus, X, Upload } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/components/auth/auth-context";
import Sidebar from "./sidebar";
import MobileNav from "./mobile-nav";
import DesktopPreflight from "./desktop-preflight";

const STORAGE_KEY_IMAGE = "global-bg-image";
const STORAGE_KEY_OPACITY = "global-bg-opacity";

export default function AppShell({ children }: { children: ReactNode }) {
  const [bgImageUrl, setBgImageUrl] = useState("");
  const [bgOpacity, setBgOpacity] = useState(0.15);
  const [showBgSettings, setShowBgSettings] = useState(false);
  const [mounted, setMounted] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { user, isAuthenticated, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/login";
  // A freshly created account (seeded admin, or an admin-reset password) must
  // set a new password before the account is usable. Keep those users pinned
  // to /login, where the login page renders the "set new password" phase.
  const mustChangePassword = user?.must_change_password === true;

  useEffect(() => {
    if (loading) return;
    if (!isAuthenticated) {
      if (!isLogin) router.replace("/login");
      return;
    }
    if (mustChangePassword) {
      if (!isLogin) router.replace("/login");
      return;
    }
    if (isLogin) router.replace("/");
  }, [loading, isAuthenticated, mustChangePassword, isLogin, router]);

  useEffect(() => {
    const savedImage = localStorage.getItem(STORAGE_KEY_IMAGE);
    const savedOpacity = localStorage.getItem(STORAGE_KEY_OPACITY);
    if (savedImage) setBgImageUrl(savedImage);
    if (savedOpacity) setBgOpacity(Number(savedOpacity));
    setMounted(true);
  }, []);

  const updateBg = (url: string) => {
    setBgImageUrl(url);
    localStorage.setItem(STORAGE_KEY_IMAGE, url);
  };

  const updateOpacity = (v: number) => {
    setBgOpacity(v);
    localStorage.setItem(STORAGE_KEY_OPACITY, String(v));
  };

  const clearBg = () => {
    if (bgImageUrl?.startsWith("blob:")) URL.revokeObjectURL(bgImageUrl);
    setBgImageUrl("");
    setBgOpacity(0.15);
    localStorage.removeItem(STORAGE_KEY_IMAGE);
    localStorage.removeItem(STORAGE_KEY_OPACITY);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    // Revoke previous blob URL if any
    if (bgImageUrl?.startsWith("blob:")) URL.revokeObjectURL(bgImageUrl);
    const objectUrl = URL.createObjectURL(file);
    setBgImageUrl(objectUrl);
    // Don't store blob URLs in localStorage — they don't survive refresh
    localStorage.removeItem(STORAGE_KEY_IMAGE);
  };

  // Auth session guard (server mode): while auth state is resolving, render
  // nothing; the login page renders standalone without the app chrome. An
  // authenticated account still awaiting its first password change must not
  // see the application until that change is made.
  if (loading) return null;
  if (isLogin) return <>{children}</>;
  if (!isAuthenticated) return null;
  if (mustChangePassword) return null;

  if (!mounted) {
    return (
      <div data-testid="app-shell" className="flex min-h-screen bg-canvas">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 items-center gap-3 border-b border-border px-4 md:hidden">
            <MobileNav />
            <span className="text-sm font-semibold">组合选品控制台</span>
          </header>
          <main id="main-content" className="min-w-0 flex-1">
            <DesktopPreflight />
            {children}
          </main>
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="app-shell"
      className="flex min-h-screen bg-canvas"
      style={
        bgImageUrl
          ? {
              backgroundImage: `url(${bgImageUrl})`,
              backgroundSize: "cover",
              backgroundPosition: "center",
              backgroundAttachment: "fixed",
              backgroundRepeat: "no-repeat",
            }
          : undefined
      }
    >
      {/* Overlay for transparency */}
      {bgImageUrl && (
        <div
          className="pointer-events-none fixed inset-0"
          style={{ backgroundColor: `hsl(140 9% 94% / ${1 - bgOpacity})` }}
        />
      )}

      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-sm focus:shadow-lg"
      >
        跳转到内容
      </a>
      <Sidebar />
      <div className="relative z-10 flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center gap-3 border-b border-border bg-card/90 px-4 md:hidden">
          <MobileNav />
          <span className="text-sm font-semibold">组合选品控制台</span>
        </header>
        <main id="main-content" className="min-w-0 flex-1">
          <DesktopPreflight />
          {children}
        </main>
      </div>

      {/* Floating background button */}
      <button
        type="button"
        onClick={() => setShowBgSettings(!showBgSettings)}
        aria-label="页面背景设置"
        className="fixed bottom-6 right-6 z-50 flex h-10 w-10 items-center justify-center rounded-md border bg-card shadow-lg transition-colors hover:bg-muted"
      >
        <ImagePlus className="h-4 w-4" />
      </button>

      {/* Background settings popover */}
      {showBgSettings && (
        <div className="fixed bottom-20 right-6 z-50 w-72 rounded-md border bg-card p-4 shadow-xl">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium">页面背景设置</span>
            <button
              type="button"
              onClick={() => setShowBgSettings(false)}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="space-y-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              onChange={handleFileUpload}
              className="hidden"
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed py-2 text-xs text-muted-foreground hover:border-foreground hover:text-foreground"
            >
              <Upload className="h-3.5 w-3.5" />
              选择本地图片
            </button>
            <div className="flex items-center gap-2">
              <div className="h-px flex-1 bg-border" />
              <span className="text-xs text-muted-foreground">或</span>
              <div className="h-px flex-1 bg-border" />
            </div>
            <input
              type="text"
              placeholder="输入图片 URL..."
              value={bgImageUrl}
              onChange={(e) => updateBg(e.target.value)}
              className="h-8 w-full rounded-md border border-input bg-transparent px-2 text-xs outline-none"
            />
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">透明度</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={bgOpacity}
                onChange={(e) => updateOpacity(Number(e.target.value))}
                className="h-1 flex-1 accent-foreground"
              />
              <span className="w-8 text-right text-xs text-muted-foreground">
                {Math.round(bgOpacity * 100)}%
              </span>
            </div>
            {bgImageUrl && (
              <button
                type="button"
                onClick={clearBg}
                className="w-full rounded-md border border-dashed py-1.5 text-xs text-destructive hover:bg-destructive/10"
              >
                清除背景
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
