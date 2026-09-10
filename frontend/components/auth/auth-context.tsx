"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { AuthUser } from "@/lib/api/auth";
import {
  clearStoredAuth,
  getStoredToken,
  getStoredUser,
  setStoredAuth,
} from "@/lib/auth-storage";

interface AuthContextValue {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isAdmin: boolean;
  loading: boolean;
  login: (token: string, user: AuthUser) => void;
  logout: () => void;
  refreshUser: (user: AuthUser) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setUser(getStoredUser());
    setLoading(false);
    const handleExpired = () => setUser(null);
    window.addEventListener("bundling-auth-expired", handleExpired);
    return () => window.removeEventListener("bundling-auth-expired", handleExpired);
  }, []);

  const login = useCallback((token: string, user: AuthUser) => {
    setStoredAuth(token, user);
    setUser(user);
  }, []);

  const refreshUser = useCallback((user: AuthUser) => {
    const token = getStoredToken();
    if (token) setStoredAuth(token, user);
    setUser(user);
  }, []);

  const logout = useCallback(() => {
    clearStoredAuth();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: user !== null,
        isAdmin: user?.role === "admin",
        loading,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
