"use client";

import type { OrderSummary } from "@/lib/types";
import { LockedBadge, RefundStatusBadge } from "@/components/StatusBadge";

function formatAmount(amount: number): string {
  return `$${amount.toFixed(2)}`;
}

function orderStatusChip(status: string): string {
  switch (status) {
    case "delivered":
      return "bg-gray-100 text-gray-600";
    case "processing":
      return "bg-blue-50 text-blue-600";
    case "cancelled":
      return "bg-gray-200 text-gray-500";
    default:
      return "bg-gray-100 text-gray-600";
  }
}

function deliveryLabel(status: string, days: number | null): string | null {
  if (status === "cancelled") return "Cancelled";
  if (status === "processing") return "Not yet delivered";
  if (days === null || days === undefined) return null;
  if (days === 0) return "Delivered today";
  if (days === 1) return "Delivered 1 day ago";
  return `Delivered ${days} days ago`;
}

function deliveryToneClass(status: string, days: number | null): string {
  if (status !== "delivered" || days === null || days === undefined) {
    return "text-gray-500";
  }
  if (days <= 7) return "text-emerald-600";
  if (days <= 10) return "text-amber-600";
  return "text-rose-600";
}

export function OrderList({
  orders,
  selectedId,
  onSelect,
}: {
  orders: OrderSummary[];
  selectedId: string | null;
  onSelect: (order: OrderSummary) => void;
}) {
  if (orders.length === 0) {
    return (
      <p className="px-1 text-sm text-gray-400">No orders on this account.</p>
    );
  }
  return (
    <ul className="space-y-2">
      {orders.map((order) => {
        const active = order.order_id === selectedId;
        return (
          <li key={order.order_id}>
            <button
              type="button"
              onClick={() => onSelect(order)}
              className={`w-full rounded-xl border p-3 text-left shadow-sm transition duration-200 hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-300 ${
                active
                  ? "border-sky-400 bg-sky-50 ring-1 ring-sky-400"
                  : "border-slate-200 bg-white hover:border-sky-300"
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-sm font-semibold text-gray-900">
                  {order.product_name}
                </span>
                <span className="text-sm font-medium text-gray-700">
                  {formatAmount(order.order_amount)}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <span className="font-mono text-xs text-gray-400">
                  {order.order_id}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${orderStatusChip(
                    order.order_status,
                  )}`}
                >
                  {order.order_status}
                </span>
                {order.is_final_sale && (
                  <span className="rounded bg-purple-50 px-1.5 py-0.5 text-[10px] font-medium text-purple-700">
                    final sale
                  </span>
                )}
                <RefundStatusBadge decision={order.refund_status} />
                {order.admin_locked && <LockedBadge />}
              </div>
              {deliveryLabel(order.order_status, order.days_since_delivery) && (
                <div
                  className={`mt-1 text-xs ${deliveryToneClass(
                    order.order_status,
                    order.days_since_delivery,
                  )}`}
                >
                  {deliveryLabel(order.order_status, order.days_since_delivery)}
                </div>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
