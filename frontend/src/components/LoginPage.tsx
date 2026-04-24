/**
 * LoginPage.tsx
 * Full V-Assure styled login with:
 * - useAuth for JWT login
 * - useNavigate for redirect after login
 * - autoComplete off to prevent browser autofill
 */

import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import { useAuth } from "@/components/AuthContext";
import { VAssureLogo } from "@/components/VAssureLogo";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (loading) return;

    if (!username.trim() || !password.trim()) {
      setError("Please enter your username and password.");
      return;
    }

    setError(null);
    setLoading(true);

    try {
      await login(username.trim(), password);
      navigate("/dashboard", { replace: true });
    } catch (err: any) {
      setError(err?.message || "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "11px 14px",
    borderRadius: 8,
    border: "1px solid hsl(var(--border))",
    background: "hsl(var(--card))",
    color: "hsl(var(--foreground))",
    fontSize: 14,
    outline: "none",
    transition: "border-color 0.15s, box-shadow 0.15s",
    fontFamily: "inherit",
    boxSizing: "border-box",
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "hsl(var(--background))",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
      }}
    >
      {/* Hidden dummy inputs to trick browser autofill away from real fields */}
      <input type="text" style={{ display: "none" }} autoComplete="username" />
      <input type="password" style={{ display: "none" }} autoComplete="current-password" />

      {/* Card */}
      <div
        style={{
          width: "100%",
          maxWidth: 400,
          background: "hsl(var(--card))",
          border: "1px solid hsl(var(--border))",
          borderRadius: 14,
          boxShadow: "0 4px 24px rgba(0,0,0,0.08), 0 1px 4px rgba(0,0,0,0.04)",
          overflow: "hidden",
        }}
      >
        {/* Orange top bar */}
        <div
          style={{
            height: 5,
            background: "linear-gradient(90deg, #F5A623 0%, #e8950f 100%)",
          }}
        />

        <div style={{ padding: "2.5rem 2rem 2rem" }}>
          {/* Logo + title */}
          <div style={{ textAlign: "center", marginBottom: "2rem" }}>
            <div
              style={{ display: "flex", justifyContent: "center", marginBottom: "1rem" }}
            >
              <VAssureLogo size={72} />
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 6,
                marginBottom: 4,
              }}
            >
              <span
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  color: "hsl(var(--foreground))",
                  letterSpacing: "-0.01em",
                }}
              >
                V-Assure
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: "1px 7px",
                  borderRadius: 20,
                  background: "rgba(245,166,35,0.12)",
                  color: "#F5A623",
                  border: "1px solid rgba(245,166,35,0.3)",
                  letterSpacing: "0.04em",
                }}
              >
                Internal Tool
              </span>
            </div>
            <p
              style={{
                fontSize: 13,
                color: "hsl(var(--muted-foreground))",
                margin: 0,
              }}
            >
              Validation &amp; Comparison Platform
            </p>
          </div>

          {/* Form */}
          <form
            onSubmit={handleSubmit}
            autoComplete="off"
            style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
          >
            {/* Username */}
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "hsl(var(--foreground))",
                }}
              >
                Username
              </label>
              <input
                type="text"
                autoComplete="off"
                autoFocus
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) =>
                  e.key === "Enter" && passwordRef.current?.focus()
                }
                placeholder="Enter your username"
                style={inputStyle}
                onFocus={(e) => {
                  e.target.style.borderColor = "#F5A623";
                  e.target.style.boxShadow = "0 0 0 3px rgba(245,166,35,0.12)";
                }}
                onBlur={(e) => {
                  e.target.style.borderColor = "hsl(var(--border))";
                  e.target.style.boxShadow = "none";
                }}
              />
            </div>

            {/* Password */}
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <label
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "hsl(var(--foreground))",
                }}
              >
                Password
              </label>
              <div style={{ position: "relative" }}>
                <input
                  ref={passwordRef}
                  type={showPass ? "text" : "password"}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter your password"
                  style={{ ...inputStyle, paddingRight: 44 }}
                  onFocus={(e) => {
                    e.target.style.borderColor = "#F5A623";
                    e.target.style.boxShadow =
                      "0 0 0 3px rgba(245,166,35,0.12)";
                  }}
                  onBlur={(e) => {
                    e.target.style.borderColor = "hsl(var(--border))";
                    e.target.style.boxShadow = "none";
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowPass((v) => !v)}
                  tabIndex={-1}
                  style={{
                    position: "absolute",
                    right: 12,
                    top: "50%",
                    transform: "translateY(-50%)",
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 2,
                    color: "hsl(var(--muted-foreground))",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div
                style={{
                  fontSize: 12,
                  padding: "9px 12px",
                  borderRadius: 7,
                  background: "rgba(239,68,68,0.07)",
                  color: "#ef4444",
                  border: "1px solid rgba(239,68,68,0.2)",
                }}
              >
                {error}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: 4,
                width: "100%",
                padding: "11px",
                borderRadius: 8,
                border: "none",
                background: loading ? "rgba(245,166,35,0.5)" : "#F5A623",
                color: "#fff",
                fontSize: 14,
                fontWeight: 700,
                cursor: loading ? "not-allowed" : "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
                transition: "background 0.15s",
                fontFamily: "inherit",
              }}
              onMouseEnter={(e) => {
                if (!loading) e.currentTarget.style.background = "#e8950f";
              }}
              onMouseLeave={(e) => {
                if (!loading) e.currentTarget.style.background = "#F5A623";
              }}
            >
              {loading ? (
                <>
                  <Loader2
                    size={16}
                    style={{ animation: "spin 1s linear infinite" }}
                  />
                  Signing in…
                </>
              ) : (
                "Sign In"
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "12px 2rem",
            borderTop: "1px solid hsl(var(--border))",
            textAlign: "center",
            fontSize: 11,
            color: "hsl(var(--muted-foreground))",
            background: "hsl(var(--muted))",
          }}
        >
          Copyright © Spotline Inc. · V-Assure Internal Platform
        </div>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
        input::placeholder {
          color: hsl(var(--muted-foreground));
          opacity: 0.7;
        }
      `}</style>
    </div>
  );
}
