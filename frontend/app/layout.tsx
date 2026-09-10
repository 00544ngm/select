import type { Metadata } from "next";
import AppShell from "@/components/layout/app-shell";
import Providers from "@/components/providers";
import { AuthProvider } from "@/components/auth/auth-context";

import "./globals.css";

export const metadata: Metadata = {
  title: "组合选品控制台",
  description: "A+B 组合选品平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <Providers>
          <AuthProvider>
            <AppShell>{children}</AppShell>
          </AuthProvider>
        </Providers>
      </body>
    </html>
  );
}
