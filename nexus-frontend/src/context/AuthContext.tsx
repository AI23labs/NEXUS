import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getLoginUrl } from "../lib/api";
import type { AppointmentsResponse } from "../types/api";

type AuthState = "loading" | "logged_in" | "logged_out";

interface AuthContextValue {
  authState: AuthState;
  isLoggedIn: boolean;
  login: () => void;
  logout: () => void;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [authState, setAuthState] = useState<AuthState>("loading");

  const refreshAuth = useCallback(async () => {
    try {
      await api<AppointmentsResponse>("/api/appointments");
      setAuthState("logged_in");
    } catch (e) {
      const err = e as { status?: number };
      if (err.status === 401) {
        setAuthState("logged_out");
      } else {
        setAuthState("logged_out");
      }
    }
  }, []);

  useEffect(() => {
    refreshAuth();
  }, [refreshAuth]);

  const login = useCallback(() => {
    window.location.href = getLoginUrl();
  }, []);

  const logout = useCallback(() => {
    setAuthState("logged_out");
    window.location.href = getLoginUrl();
  }, []);

  const value: AuthContextValue = {
    authState,
    isLoggedIn: authState === "logged_in",
    login,
    logout,
    refreshAuth,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
