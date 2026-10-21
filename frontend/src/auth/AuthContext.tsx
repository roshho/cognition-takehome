import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken, setToken } from "../api/client";

export interface User {
  id: number;
  username: string;
  display_name: string;
  role: "reviewer" | "admin" | string;
}

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (username: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    const { data, error } = await api.GET("/api/me");
    if (error || !data) {
      setToken(null);
      setUser(null);
    } else {
      setUser(data as User);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    // SSO handoff: the OIDC callback lands here with ?sso_token=...
    const params = new URLSearchParams(window.location.search);
    const sso = params.get("sso_token");
    if (sso) {
      setToken(sso);
      params.delete("sso_token");
      const q = params.toString();
      window.history.replaceState(
        {},
        "",
        window.location.pathname + (q ? `?${q}` : "") + window.location.hash
      );
    }
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string) => {
    const { data, error } = await api.POST("/api/auth/login", {
      body: { username },
    });
    if (error || !data) throw new Error("Login failed");
    setToken(data.token);
    setUser(data.user as User);
  }, []);

  const logout = useCallback(async () => {
    await api.POST("/api/auth/logout");
    setToken(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
