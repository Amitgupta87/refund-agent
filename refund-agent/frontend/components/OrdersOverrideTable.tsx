"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  getOrders,
  overrideDecision,
  unlockOrder,
  type OverrideDecision,
} from "@/lib/api";
import type { AdminOrder } from "@/lib/types";
import { LockedBadge, StatusBadge } from "@/components/StatusBadge";

const OPTIONS: OverrideDecision[] = [
  "refund_initiated",
  "replacement_initiated",
  "denied",
  "escalated",
];

export function OrdersOverrideTable({
  token,
  onAuthError,
}: {
  token: string;
  onAuthError: () => void;
}) {
  const [orders, setOrders] = useState<AdminOrder[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrders(await getOrders(token));
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        onAuthError();
        return;
      }
      setError("Could not load orders.");
    } finally {
      setLoadedOnce(true);
    }
  }, [token, onAuthError]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500">
        Review Penny&apos;s decisions and override them when needed. Overrides are
        recorded in the reasoning log.
      </p>
      {error && (
        <div className="rounded-md bg-red-50 px-4 py-2 text-sm text-red-700 ring-1 ring-red-200">
          {error}
        </div>
      )}
      <div className="card overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50/80 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">Order</th>
              <th className="px-4 py-2 font-medium">Decision</th>
              <th className="px-4 py-2 font-medium">Override</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {orders.map((order) => (
              <OrderRow
                key={order.order_id}
                order={order}
                token={token}
                onApplied={load}
              />
            ))}
            {loadedOnce && orders.length === 0 && !error && (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-400">
                  No orders found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OrderRow({
  order,
  token,
  onApplied,
}: {
  order: AdminOrder;
  token: string;
  onApplied: () => void;
}) {
  const [decision, setDecision] = useState<OverrideDecision>(
    order.refund_status === "none" ? "refund_initiated" : order.refund_status,
  );
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function apply() {
    setBusy(true);
    setErr(null);
    try {
      await overrideDecision(token, order.order_id, decision, reason.trim() || null);
      setReason("");
      onApplied();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Override failed.");
    } finally {
      setBusy(false);
    }
  }

  async function unlock() {
    setBusy(true);
    setErr(null);
    try {
      await unlockOrder(token, order.order_id);
      onApplied();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Unlock failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="align-top">
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{order.customer_name}</div>
        <div className="font-mono text-xs text-gray-400">{order.customer_id}</div>
      </td>
      <td className="px-4 py-3">
        <div className="font-medium text-gray-800">{order.product_name}</div>
        <div className="font-mono text-xs text-gray-400">
          {order.order_id} · ${order.order_amount.toFixed(2)} · {order.order_status}
          {order.is_final_sale ? " · final sale" : ""}
        </div>
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-1">
          <StatusBadge decision={order.refund_status} />
          {order.admin_locked && <LockedBadge />}
        </div>
        {order.refund_reason && (
          <div className="mt-1 max-w-[16rem] text-xs text-gray-500">
            {order.refund_reason}
          </div>
        )}
        {order.escalation_ticket && (
          <div className="mt-0.5 font-mono text-[11px] text-amber-700">
            {order.escalation_ticket}
          </div>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={decision}
            onChange={(e) => setDecision(e.target.value as OverrideDecision)}
            className="rounded-md border border-gray-300 px-2 py-1 text-xs"
          >
            {OPTIONS.map((o) => (
              <option key={o} value={o}>
                {o.replace("_", " ")}
              </option>
            ))}
          </select>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="reason (optional)"
            className="w-40 rounded-md border border-gray-300 px-2 py-1 text-xs"
          />
          <button
            type="button"
            onClick={() => void apply()}
            disabled={busy}
            className="rounded-md bg-gradient-to-r from-sky-600 to-blue-600 px-3 py-1 text-xs font-semibold text-white disabled:opacity-50"
          >
            {busy ? "…" : "Override"}
          </button>
          {order.admin_locked && (
            <button
              type="button"
              onClick={() => void unlock()}
              disabled={busy}
              className="rounded-md border border-slate-200 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
            >
              Unlock
            </button>
          )}
        </div>
        {err && <div className="mt-1 text-xs text-red-600">{err}</div>}
      </td>
    </tr>
  );
}
