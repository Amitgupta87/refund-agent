import type { Decision } from "@/lib/types";

const DECISION_STYLES: Record<Decision, { label: string; className: string }> = {
  refund_initiated: {
    label: "Refund initiated",
    className: "bg-green-100 text-green-800 ring-green-600/20",
  },
  replacement_initiated: {
    label: "Replacement initiated",
    className: "bg-emerald-100 text-emerald-800 ring-emerald-600/20",
  },
  denied: {
    label: "Denied",
    className: "bg-red-100 text-red-800 ring-red-600/20",
  },
  escalated: {
    label: "Escalated",
    className: "bg-amber-100 text-amber-800 ring-amber-600/20",
  },
  none: {
    label: "No decision",
    className: "bg-gray-100 text-gray-700 ring-gray-500/20",
  },
};

export function StatusBadge({ decision }: { decision: Decision }) {
  const { label, className } = DECISION_STYLES[decision];
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${className}`}
    >
      {label}
    </span>
  );
}

/** Like StatusBadge but renders nothing for "none" — for customer-facing UI. */
export function RefundStatusBadge({ decision }: { decision: Decision }) {
  if (decision === "none") return null;
  return <StatusBadge decision={decision} />;
}

export function FlaggedBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-rose-600 px-2.5 py-0.5 text-xs font-semibold text-white">
      Security flag
    </span>
  );
}

export function LockedBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-semibold text-white">
      <svg viewBox="0 0 16 16" width="10" height="10" fill="currentColor" aria-hidden="true">
        <path d="M5 7V5a3 3 0 0 1 6 0v2h.5A1.5 1.5 0 0 1 13 8.5v4A1.5 1.5 0 0 1 11.5 14h-7A1.5 1.5 0 0 1 3 12.5v-4A1.5 1.5 0 0 1 4.5 7H5Zm1 0h4V5a2 2 0 1 0-4 0v2Z" />
      </svg>
      Locked by admin
    </span>
  );
}
