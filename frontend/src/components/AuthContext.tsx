/**
 * AuthContext.tsx
 *
 * Provides authentication state to the whole app.
 * - Stores JWT in sessionStorage (cleared when tab closes)
 * - Re-validates token on page load by calling /auth/me
 * - Exposes: user, login(), logout(), loading, error
 *
 * Usage:
 *   Wrap your app in <AuthProvider> in main.tsx.
 *   Use useAuth() in any component.
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AuthUser {
  email: string;
  role: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

// ─── Storage ──────────────────────────────────────────────────────────────────

const TOKEN_KEY = "vassure_token";

export function getStoredToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY);
}

function setStoredToken(token: string) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

function clearStoredToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

// ─── API helpers ──────────────────────────────────────────────────────────────

const API_BASE = ""; // proxied via Vite → http://127.0.0.1:8000

async function apiLogin(email: string, password: string) {
  const body = new URLSearchParams();
  body.set("username", email); // OAuth2 spec field name
  body.set("password", password);

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Invalid email or password");
  }

  return res.json() as Promise<{ access_token: string; email: string; role: string }>;
}

async function apiMe(token: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Token invalid or expired");
  return res.json();
}

// ─── Context ──────────────────────────────────────────────────────────────────

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser]       = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState<string | null>(null);

  // On mount: validate any stored token
  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setLoading(false);
      return;
    }
    apiMe(token)
      .then(setUser)
      .catch(() => clearStoredToken())
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setError(null);
    const data = await apiLogin(email, password);
    setStoredToken(data.access_token);
    setUser({ email: data.email, role: data.role });
    // ↑ Setting user here causes App.tsx to re-render and navigate to /dashboard
  }, []);

  const logout = useCallback(() => {
    clearStoredToken();
    setUser(null);
    setError(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, error, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
