import type {
  AdminLogEntry,
  AdminOrder,
  ChatRequest,
  ChatResponse,
  Decision,
  LoginResponse,
  MediaUploadResponse,
  OrderSummary,
} from "./types";

export type OverrideDecision =
  | "refund_initiated"
  | "replacement_initiated"
  | "denied"
  | "escalated";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") return data.detail;
    if (data.detail) return JSON.stringify(data.detail);
  } catch {
    // fall through to status text
  }
  return res.statusText || `Request failed (${res.status})`;
}

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

// ---- Auth / customer ----

export async function login(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as LoginResponse;
}

export async function getMyOrders(token: string): Promise<OrderSummary[]> {
  const res = await fetch(`${API_BASE}/me/orders`, {
    headers: authHeader(token),
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as OrderSummary[];
}

export async function sendChat(
  token: string,
  req: ChatRequest,
): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader(token) },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as ChatResponse;
}

export async function uploadMedia(
  token: string,
  file: File,
): Promise<MediaUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE}/media`, {
    method: "POST",
    headers: authHeader(token),
    body: form,
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as MediaUploadResponse;
}

// ---- Admin (token-protected internal tool) ----

export async function adminLogin(
  username: string,
  password: string,
): Promise<{ token: string; username: string }> {
  const res = await fetch(`${API_BASE}/admin/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as { token: string; username: string };
}

export interface LogFilters {
  decision?: Exclude<Decision, "none"> | null;
  flagged?: boolean;
}

export async function getLogs(
  token: string,
  filters: LogFilters = {},
): Promise<AdminLogEntry[]> {
  const params = new URLSearchParams();
  if (filters.decision) params.set("decision", filters.decision);
  if (filters.flagged) params.set("flagged", "true");
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/admin/logs${qs ? `?${qs}` : ""}`, {
    headers: authHeader(token),
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as AdminLogEntry[];
}

export async function getOrders(token: string): Promise<AdminOrder[]> {
  const res = await fetch(`${API_BASE}/admin/orders`, {
    headers: authHeader(token),
    cache: "no-store",
  });
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as AdminOrder[];
}

export async function overrideDecision(
  token: string,
  orderId: string,
  decision: OverrideDecision,
  reason: string | null,
): Promise<AdminOrder> {
  const res = await fetch(
    `${API_BASE}/admin/orders/${encodeURIComponent(orderId)}/override`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader(token) },
      body: JSON.stringify({ decision, reason }),
    },
  );
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as AdminOrder;
}

export async function unlockOrder(
  token: string,
  orderId: string,
): Promise<{ order_id: string; admin_locked: boolean }> {
  const res = await fetch(
    `${API_BASE}/admin/orders/${encodeURIComponent(orderId)}/unlock`,
    {
      method: "POST",
      headers: authHeader(token),
    },
  );
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  return (await res.json()) as { order_id: string; admin_locked: boolean };
}

export async function getAdminMediaObjectUrl(
  token: string,
  mediaId: string,
): Promise<string> {
  const res = await fetch(
    `${API_BASE}/admin/media/${encodeURIComponent(mediaId)}`,
    { headers: authHeader(token) },
  );
  if (!res.ok) throw new ApiError(await parseError(res), res.status);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
