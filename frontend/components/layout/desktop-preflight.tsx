"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";

import { apiFetch } from "@/lib/api/client";

type DiagnosticCheck = {
  status: string;
  code?: string;
  summary?: string;
};

type Diagnostics = {
  status: string;
  checks: Record<string, DiagnosticCheck>;
};

export default function DesktopPreflight() {
  const [browserFailed, setBrowserFailed] = useState(false);

  useEffect(() => {
    if (!window.desktop) return;
    let active = true;
    void apiFetch<Diagnostics>("/desktop/diagnostics", { timeoutMs: 30_000 })
      .then((result) => {
        if (active) setBrowserFailed(result.checks.browser?.status === "failed");
      })
      .catch(() => {
        // Local service readiness is handled by Electron; avoid startup false alarms.
      });
    return () => {
      active = false;
    };
  }, []);

  if (!browserFailed) return null;

  return (
    <div
      role="alert"
      className="flex min-h-10 items-center gap-2 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm text-amber-950"
    >
      <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>浏览器环境未就绪，提交任务前请检查 Windows 安全中心或日志。</span>
    </div>
  );
}
