"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getLogs, getAdminMediaObjectUrl, type LogFilters } from "@/lib/api";
import type { AdminLogEntry } from "@/lib/types";
import { FlaggedBadge, StatusBadge } from "@/components/StatusBadge";

type FilterKey =
  | "all"
  | "refund_initiated"
  | "replacement_initiated"
  | "denied"
  | "escalated"
  | "flagged";

const FILTERS: { key: FilterKey; label: string }[] = [
  { key: "all", label: "All" },
  { key: "refund_initiated", label: "Refund" },
  { key: "replacement_initiated", label: "Replacement" },
  { key: "denied", label: "Denied" },
  { key: "escalated", label: "Escalated" },
  { key: "flagged", label: "Flagged" },
];

const POLL_MS = 3000;

function toFilters(key: FilterKey): LogFilters {
  switch (key) {
    case "refund_initiated":
    case "replacement_initiated":
    case "denied":
    case "escalated":
      return { decision: key };
    case "flagged":
      return { flagged: true };
    default:
      return {};
  }
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function ReasoningLogTable({
  token,
  onAuthError,
}: {
  token: string;
  onAuthError: () => void;
}) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [logs, setLogs] = useState<AdminLogEntry[]>([]);
  const [expanded, setExpanded] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);

  const load = useCallback(
    async (key: FilterKey) => {
      try {
        const data = await getLogs(token, toFilters(key));
        setLogs(data);
        setError(null);
      } catch (err) {
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          onAuthError();
          return;
        }
        setError("Could not load reasoning logs.");
      } finally {
        setLoadedOnce(true);
      }
    },
    [token, onAuthError],
  );

  useEffect(() => {
    void load(filter);
    const id = setInterval(() => void load(filter), POLL_MS);
    return () => clearInterval(id);
  }, [filter, load]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-gray-500">
          Agent reasoning &amp; decisions — auto-refreshing every {POLL_MS / 1000}s.
        </p>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
                filter === f.key
                  ? "bg-sky-600 text-white"
                  : "bg-white text-gray-700 ring-1 ring-gray-200 hover:bg-gray-50"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-md bg-red-50 px-4 py-2 text-sm text-red-700 ring-1 ring-red-200">
          {error}
        </div>
      )}

      <div className="card overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50/80 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2 font-medium">Time</th>
              <th className="px-4 py-2 font-medium">Customer</th>
              <th className="px-4 py-2 font-medium">Order</th>
              <th className="px-4 py-2 font-medium">Decision</th>
              <th className="px-4 py-2 font-medium">Flag</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {logs.map((log) => (
              <RowGroup
                key={log.id}
                log={log}
                token={token}
                open={expanded === log.id}
                onToggle={() => setExpanded((cur) => (cur === log.id ? null : log.id))}
                formatTime={formatTime}
              />
            ))}
            {loadedOnce && logs.length === 0 && !error && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                  No decisions yet. Process a refund in the chat to see logs here.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function MediaThumbnail({ mediaId, token }: { mediaId: string; token: string }) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAdminMediaObjectUrl(token, mediaId)
      .then((url) => {
        if (!cancelled) { urlRef.current = url; setObjectUrl(url); }
      })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => {
      cancelled = true;
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, [token, mediaId]);

  if (failed) return (
    <span className="inline-flex h-16 w-16 items-center justify-center rounded border border-gray-200 bg-gray-50 text-[10px] text-gray-400">
      err
    </span>
  );
  if (!objectUrl) return (
    <span className="inline-block h-16 w-16 animate-pulse rounded border border-gray-200 bg-gray-100" />
  );
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={objectUrl}
      alt={`Attached media ${mediaId}`}
      className="h-16 w-16 rounded border border-gray-200 object-cover"
      onError={() => setFailed(true)}
    />
  );
}

function RowGroup({
  log,
  token,
  open,
  onToggle,
  formatTime,
}: {
  log: AdminLogEntry;
  token: string;
  open: boolean;
  onToggle: () => void;
  formatTime: (iso: string) => string;
}) {
  return (
    <>
      <tr onClick={onToggle} className="cursor-pointer hover:bg-gray-50" aria-expanded={open}>
        <td className="whitespace-nowrap px-4 py-2 text-gray-500">{formatTime(log.timestamp)}</td>
        <td className="px-4 py-2">
          <div className="font-medium text-gray-900">{log.customer_name ?? "—"}</div>
          <div className="font-mono text-xs text-gray-400">{log.customer_id ?? ""}</div>
        </td>
        <td className="px-4 py-2 font-mono text-xs text-gray-700">{log.order_id ?? "—"}</td>
        <td className="px-4 py-2"><StatusBadge decision={log.decision} /></td>
        <td className="px-4 py-2">{log.security_flag && <FlaggedBadge />}</td>
      </tr>
      {open && (
        <tr className="bg-gray-50">
          <td colSpan={5} className="px-4 py-3">
            <div className="space-y-3 text-xs">
              {log.media_ids?.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-600">
                    Attached media ({log.media_ids.length})
                  </div>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {log.media_ids.map((id) => (
                      <MediaThumbnail key={id} mediaId={id} token={token} />
                    ))}
                  </div>
                </div>
              )}
              <div>
                <span className="font-semibold text-gray-600">Customer message:</span>{" "}
                <span className="text-gray-800">{log.user_message}</span>
              </div>
              <div>
                <span className="font-semibold text-gray-600">Final response:</span>{" "}
                <span className="text-gray-800">{log.final_response}</span>
              </div>
              {log.reasoning_steps.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-600">Reasoning steps</div>
                  <ol className="mt-1 list-decimal space-y-1 pl-5 text-gray-700">
                    {log.reasoning_steps.map((s, i) => (
                      <li key={i} className="whitespace-pre-wrap">{s}</li>
                    ))}
                  </ol>
                </div>
              )}
              {log.tools_called.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-600">Tool calls</div>
                  <div className="mt-1 space-y-2">
                    {log.tools_called.map((call, i) => (
                      <div key={i} className="rounded border border-gray-200 bg-white p-2">
                        <div className="font-mono font-semibold text-sky-700">{call.tool}</div>
                        <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-gray-600">
                          {JSON.stringify({ input: call.input, output: call.output }, null, 2)}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
