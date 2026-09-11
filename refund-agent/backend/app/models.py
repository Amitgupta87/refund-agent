"""Pydantic v2 models for API I/O, tool results, and the reasoning log."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Decision = Literal[
    "none",
    "refund_initiated",
    "replacement_initiated",
    "denied",
    "escalated",
]
OverrideDecision = Literal["refund_initiated", "replacement_initiated", "denied", "escalated"]


class OrderDetails(BaseModel):
    """Normalized order record returned by get_customer_order."""

    found: bool = True
    order_id: str
    customer_id: str
    customer_name: str
    email: str
    product_name: str
    order_date: str
    order_amount: float
    order_status: str
    is_final_sale: bool
    days_since_delivery: int | None
    is_damaged: bool
    has_photo_proof: bool
    refund_status: Decision
    refund_reason: str | None = None
    escalation_ticket: str | None = None
    admin_locked: bool = False


class EligibilityResult(BaseModel):
    outcome: Literal["eligible", "deny", "escalate", "needs_media", "locked"]
    eligible: bool
    reason: str
    requires_escalation: bool
    needs_media: bool
    locked: bool


class ToolCall(BaseModel):
    """One tool invocation captured in the reasoning log."""

    tool: str
    input: dict[str, Any]
    output: dict[str, Any]


class ReasoningLog(BaseModel):
    """Full record of a single agent turn (persisted server-side, admin-only)."""

    turn_id: str
    conversation_id: str
    customer_id: str | None = None
    order_id: str | None = None
    user_message: str
    reasoning_steps: list[str] = Field(default_factory=list)
    tools_called: list[ToolCall] = Field(default_factory=list)
    final_response: str = ""
    decision: Decision = "none"
    security_flag: bool = False
    timestamp: str
    media_ids: list[str] = Field(default_factory=list)


# ---- Customer-facing API models ----


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class CustomerProfile(BaseModel):
    customer_id: str
    name: str
    email: str
    username: str


class LoginResponse(BaseModel):
    token: str
    customer: CustomerProfile


class OrderSummary(BaseModel):
    order_id: str
    product_name: str
    order_date: str
    order_amount: float
    order_status: str
    is_final_sale: bool
    days_since_delivery: int | None
    is_damaged: bool
    has_photo_proof: bool
    refund_status: Decision
    refund_reason: str | None = None
    escalation_ticket: str | None = None
    admin_locked: bool = False


class ChatRequest(BaseModel):
    order_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=64)
    media_ids: list[str] = Field(default_factory=list, max_length=6)


class ChatResponse(BaseModel):
    """Customer-facing response. Deliberately omits internal reasoning, tool
    calls, and security flags — those are admin-only (see /admin/logs)."""

    turn_id: str
    conversation_id: str
    decision: Decision
    final_response: str
    timestamp: str


class MediaUploadResponse(BaseModel):
    media_id: str
    kind: Literal["image", "video"]
    mime_type: str
    size_bytes: int
    duration_sec: float | None = None


# ---- Admin API models ----


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class AdminLoginResponse(BaseModel):
    token: str
    username: str


class OverrideRequest(BaseModel):
    decision: OverrideDecision
    reason: str | None = Field(default=None, max_length=500)


class UnlockResponse(BaseModel):
    order_id: str
    admin_locked: bool


class AdminLogEntry(ReasoningLog):
    id: int
    customer_name: str | None = None


class AdminOrder(BaseModel):
    customer_id: str
    customer_name: str
    order_id: str
    product_name: str
    order_amount: float
    order_status: str
    is_final_sale: bool
    days_since_delivery: int | None
    refund_status: Decision
    refund_reason: str | None = None
    escalation_ticket: str | None = None
    admin_locked: bool = False
    updated_at: str | None = None
