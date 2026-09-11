"use client";

import { useState } from "react";
import { ApiError, adminLogin } from "@/lib/api";
import type { AdminSession } from "@/lib/auth";

export function AdminLogin({
  onLogin,
}: {
  onLogin: (session: AdminSession) => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await adminLogin(username.trim(), password);
      onLogin({ token: res.token, username: res.username });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the server. Is the backend running?",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto mt-10 max-w-md">
      <div className="card p-6">
        <h1 className="text-xl font-semibold text-gray-900">Admin sign in</h1>
        <p className="mt-1 text-sm text-gray-500">
          Restricted area — review and override agent decisions.
        </p>
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <label className="block text-sm font-medium text-gray-700">
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              className="field-input"
            />
          </label>
          <label className="block text-sm font-medium text-gray-700">
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              className="field-input"
            />
          </label>
          {error && (
            <div className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 ring-1 ring-red-200">
              {error}
            </div>
          )}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
      <div className="mt-4 rounded-xl bg-sky-50 p-3 text-center text-xs text-sky-900 ring-1 ring-sky-100">
        Demo admin: <span className="font-mono font-semibold">admin / admin123</span>
      </div>
    </div>
  );
}
