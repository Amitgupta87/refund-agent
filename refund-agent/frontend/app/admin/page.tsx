"use client";

import { useEffect, useState } from "react";
import {
  clearAdminSession,
  loadAdminSession,
  saveAdminSession,
  type AdminSession,
} from "@/lib/auth";
import { AdminLogin } from "@/components/AdminLogin";
import { ReasoningLogTable } from "@/components/ReasoningLogTable";
import { OrdersOverrideTable } from "@/components/OrdersOverrideTable";

type Tab = "logs" | "orders";

export default function AdminPage() {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>("logs");

  useEffect(() => {
    setSession(loadAdminSession());
    setReady(true);
  }, []);

  function handleLogin(s: AdminSession) {
    saveAdminSession(s);
    setSession(s);
  }
  function handleLogout() {
    clearAdminSession();
    setSession(null);
  }

  if (!ready) return null;
  if (!session) return <AdminLogin onLogin={handleLogin} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">Admin dashboard</h1>
          <p className="text-xs text-gray-500">
            Signed in as <span className="font-medium">{session.username}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          Log out
        </button>
      </div>

      <div className="flex gap-1 rounded-lg bg-white/70 p-1 ring-1 ring-gray-200">
        <TabButton active={tab === "logs"} onClick={() => setTab("logs")}>
          Reasoning log
        </TabButton>
        <TabButton active={tab === "orders"} onClick={() => setTab("orders")}>
          Orders &amp; overrides
        </TabButton>
      </div>

      {tab === "logs" ? (
        <ReasoningLogTable token={session.token} onAuthError={handleLogout} />
      ) : (
        <OrdersOverrideTable token={session.token} onAuthError={handleLogout} />
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition ${
        active ? "bg-sky-600 text-white" : "text-gray-600 hover:bg-gray-100"
      }`}
    >
      {children}
    </button>
  );
}
