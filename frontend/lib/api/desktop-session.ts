declare global {
  interface Window {
    desktop?: {
      getSession(): Promise<{ token: string }>;
      getDesktopStatus(): Promise<{ apiBase?: string }>;
      requestQuit(): Promise<void>;
      openLogDirectory(): Promise<void>;
      openWindowsSecurity(): Promise<void>;
    };
  }
}

let cachedToken: string | null = null;

export async function getDesktopSessionToken(): Promise<string | null> {
  if (typeof window === "undefined" || !window.desktop) return null;
  if (cachedToken) return cachedToken;
  const session = await window.desktop.getSession();
  cachedToken = session.token;
  return cachedToken;
}

export async function getDesktopApiBase(): Promise<string | null> {
  if (typeof window === "undefined" || !window.desktop) return null;
  const status = await window.desktop.getDesktopStatus();
  return status.apiBase ?? null;
}

export function resetDesktopSessionForTests(): void {
  cachedToken = null;
}

export {};
