"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, getMyOrders } from "@/lib/api";
import {
  clearSession,
  loadSession,
  saveSession,
  type Session,
} from "@/lib/auth";
import type { OrderSummary } from "@/lib/types";
import { LoginForm } from "@/components/LoginForm";
import { OrderList } from "@/components/OrderList";
import { ChatPanel } from "@/components/ChatPanel";
import { PennyAvatar } from "@/components/Mascot";

export default function HomePage() {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [selected, setSelected] = useState<OrderSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Restore any saved session on first load.
  useEffect(() => {
    setSession(loadSession());
    setReady(true);
  }, []);

  const refreshOrders = useCallback(async (token: string) => {
    try {
      const data = await getMyOrders(token);
      setOrders(data);
      setError(null);
      // Keep the selected order's data fresh (e.g. updated refund_status).
      setSelected((cur) =>
        cur ? data.find((o) => o.order_id === cur.order_id) ?? cur : cur,
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        handleLogout();
        return;
      }
      setError("Could not load your orders. Is the backend running?");
    }
  }, []);

  useEffect(() => {
    if (session) void refreshOrders(session.token);
  }, [session, refreshOrders]);

  function handleLogin(s: Session) {
    saveSession(s);
    setSession(s);
  }

  function handleLogout() {
    clearSession();
    setSession(null);
    setOrders([]);
    setSelected(null);
  }

  if (!ready) return null;

  if (!session) {
    return <LoginForm onLogin={handleLogin} />;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">
            Welcome, {session.customer.name.split(" ")[0]}
          </h1>
          <p className="text-xs text-gray-500">
            Select an order to ask about a refund.
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50"
        >
          Log out
        </button>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 px-4 py-2 text-sm text-red-700 ring-1 ring-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <section>
          <h2 className="mb-2 text-sm font-semibold text-gray-700">Your orders</h2>
          <OrderList
            orders={orders}
            selectedId={selected?.order_id ?? null}
            onSelect={setSelected}
          />
        </section>

        <section>
          {selected ? (
            <ChatPanel
              token={session.token}
              order={selected}
              onDecision={() => void refreshOrders(session.token)}
            />
          ) : (
            <div className="flex h-[70vh] flex-col items-center justify-center gap-3 rounded-2xl bg-white/60 text-sm text-gray-400 ring-1 ring-black/5">
              <PennyAvatar size={56} />
              <p>Select an order on the left and I&apos;ll help you with a refund.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
