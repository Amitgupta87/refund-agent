import type { CustomerProfile } from "./types";

const TOKEN_KEY = "refund_agent_token";
const PROFILE_KEY = "refund_agent_profile";

export interface Session {
  token: string;
  customer: CustomerProfile;
}

export function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  const token = window.localStorage.getItem(TOKEN_KEY);
  const profileRaw = window.localStorage.getItem(PROFILE_KEY);
  if (!token || !profileRaw) return null;
  try {
    return { token, customer: JSON.parse(profileRaw) as CustomerProfile };
  } catch {
    return null;
  }
}

export function saveSession(session: Session): void {
  window.localStorage.setItem(TOKEN_KEY, session.token);
  window.localStorage.setItem(PROFILE_KEY, JSON.stringify(session.customer));
}

export function clearSession(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  window.localStorage.removeItem(PROFILE_KEY);
}

// ---- Admin session (separate from customer) ----

const ADMIN_TOKEN_KEY = "refund_agent_admin_token";
const ADMIN_USER_KEY = "refund_agent_admin_user";

export interface AdminSession {
  token: string;
  username: string;
}

export function loadAdminSession(): AdminSession | null {
  if (typeof window === "undefined") return null;
  const token = window.localStorage.getItem(ADMIN_TOKEN_KEY);
  const username = window.localStorage.getItem(ADMIN_USER_KEY);
  if (!token || !username) return null;
  return { token, username };
}

export function saveAdminSession(session: AdminSession): void {
  window.localStorage.setItem(ADMIN_TOKEN_KEY, session.token);
  window.localStorage.setItem(ADMIN_USER_KEY, session.username);
}

export function clearAdminSession(): void {
  window.localStorage.removeItem(ADMIN_TOKEN_KEY);
  window.localStorage.removeItem(ADMIN_USER_KEY);
}
