"use client";

import { useState } from "react";
import { ApiError, login } from "@/lib/api";
import type { Session } from "@/lib/auth";
import { PennyMascot } from "@/components/Mascot";

const DEMO_ACCOUNTS = [
  { username: "alice", password: "alice123" },
  { username: "bob", password: "bob123" },
  { username: "carol", password: "carol123" },
  { username: "dave", password: "dave123" },
  { username: "eve", password: "eve123" },
  { username: "frank", password: "frank123" },
];

export function LoginForm({ onLogin }: { onLogin: (session: Session) => void }) {
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
      const res = await login(username.trim(), password);
      onLogin({ token: res.token, customer: res.customer });
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
    <div className="mx-auto mt-8 max-w-md">
      <div className="mb-5 text-center">
        <PennyMascot size={84} />
        <h1 className="mt-3 text-xl font-bold text-gray-900">
          Hi, I&apos;m Penny
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Sign in and I&apos;ll help you with a refund on your orders.
        </p>
      </div>

      <div className="card p-6">
        <form onSubmit={handleSubmit} className="space-y-4">
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

      <div className="mt-4 rounded-xl bg-sky-50 p-4 text-xs text-sky-900 ring-1 ring-sky-100">
        <div className="mb-2 font-semibold">Demo accounts</div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {DEMO_ACCOUNTS.map((acc) => (
            <button
              key={acc.username}
              type="button"
              onClick={() => {
                setUsername(acc.username);
                setPassword(acc.password);
              }}
              className="rounded-md bg-white/70 px-2 py-1 text-left font-mono hover:bg-white"
            >
              {acc.username} / {acc.password}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
