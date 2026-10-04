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
      setError(err?.message || "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <div className="w-full max-w-sm bg-card text-card-foreground border rounded-xl shadow-lg overflow-hidden">

        {/* Top bar */}
        <div className="h-[5px] bg-gradient-to-r from-[#F5A623] to-[#e8950f]" />

        <div className="p-8">
          {/* Logo */}
          <div className="text-center mb-8">
            <div className="flex justify-center mb-4">
              <VAssureLogo size={72} />
            </div>

            <div className="flex justify-center items-center gap-2 mb-1">
              <h1 className="text-xl font-bold">V-Assure</h1>
              <span className="text-[10px] px-2 py-[2px] rounded-full border bg-primary/10 text-primary border-primary/30">
                Internal
              </span>
            </div>

            <p className="text-xs text-muted-foreground">
              Validation & Comparison Platform
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">

            {/* Username */}
            <div>
              <label className="text-xs font-semibold">Username</label>
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && passwordRef.current?.focus()}
                placeholder="Enter username"
                className="w-full mt-1 p-2 rounded-md border bg-input text-foreground focus:ring-2 focus:ring-primary outline-none"
              />
            </div>

            {/* Password */}
            <div>
              <label className="text-xs font-semibold">Password</label>
              <div className="relative">
                <input
                  ref={passwordRef}
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  className="w-full mt-1 p-2 pr-10 rounded-md border bg-input text-foreground focus:ring-2 focus:ring-primary outline-none"
                />
                <button
                  type="button"
                  onClick={() => setShowPass(!showPass)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
                >
                  {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Error */}
            {error && (
              <div className="text-xs p-2 rounded bg-red-100 text-red-600 border border-red-300">
                {error}
              </div>
            )}

            {/* Button */}
            <button
              type="submit"
              disabled={loading}
              className="bg-primary text-primary-foreground py-2 rounded-md font-semibold flex justify-center items-center gap-2 hover:opacity-90 transition"
            >
              {loading ? (
                <>
                  <Loader2 className="animate-spin" size={16} />
                  Signing in...
                </>
              ) : (
                "Sign In"
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <div className="text-center text-xs p-3 border-t bg-muted text-muted-foreground">
          © Spotline · V-Assure
        </div>
      </div>
    </div>
  );
}