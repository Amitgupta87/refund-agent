// Types mirror the backend Pydantic models (backend/app/models.py).

export type Decision =
  | "none"
  | "refund_initiated"
  | "replacement_initiated"
  | "denied"
  | "escalated";

export type OverrideDecisionValue = Exclude<Decision, "none">;

export interface MediaUploadResponse {
  media_id: string;
  kind: "image" | "video";
  mime_type: string;
  size_bytes: number;
  duration_sec: number | null;
}

export interface ToolCall {
  tool: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
}

// ---- Auth / customer ----

export interface CustomerProfile {
  customer_id: string;
  name: string;
  email: string;
  username: string;
}

export interface LoginResponse {
  token: string;
  customer: CustomerProfile;
}

export interface OrderSummary {
  order_id: string;
  product_name: string;
  order_date: string;
  order_amount: number;
  order_status: string;
  is_final_sale: boolean;
  days_since_delivery: number | null;
  is_damaged: boolean;
  has_photo_proof: boolean;
  refund_status: Decision;
  refund_reason: string | null;
  escalation_ticket: string | null;
  admin_locked: boolean;
}

// ---- Chat (customer-facing: no internal reasoning) ----

export interface ChatRequest {
  order_id: string;
  message: string;
  conversation_id?: string | null;
  media_ids?: string[];
}

export interface ChatResponse {
  turn_id: string;
  conversation_id: string;
  decision: Decision;
  final_response: string;
  timestamp: string;
}

// ---- Admin ----

export interface AdminLogEntry {
  id: number;
  turn_id: string;
  conversation_id: string;
  customer_id: string | null;
  customer_name: string | null;
  order_id: string | null;
  user_message: string;
  reasoning_steps: string[];
  tools_called: ToolCall[];
  final_response: string;
  decision: Decision;
  security_flag: boolean;
  timestamp: string;
  media_ids: string[];
}

export interface AdminOrder {
  customer_id: string;
  customer_name: string;
  order_id: string;
  product_name: string;
  order_amount: number;
  order_status: string;
  is_final_sale: boolean;
  days_since_delivery: number | null;
  refund_status: Decision;
  refund_reason: string | null;
  escalation_ticket: string | null;
  admin_locked: boolean;
  updated_at: string | null;
}
