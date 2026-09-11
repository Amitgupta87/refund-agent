"""Agent tools: SQLite queries + policy enforcement.

Eight tools back the customer-support agent. Reads load orders scoped to the
authenticated customer. The four terminal tools (initiate_refund,
initiate_replacement, deny_request, escalate_to_human) mutate
`orders.refund_status`. Every terminal tool re-runs the deterministic policy
engine server-side and refuses to act against the policy (or against an
admin-locked order) — this is the guardrail that makes the system resistant to
prompt injection and IDOR.

`request_media` is a non-terminal helper that lets the model formally signal
that the customer must attach a photo/video before progressing. It does not
mutate state.

Each tool returns a JSON-serializable dict that is handed back to the model as
a tool result and captured in the reasoning log.
"""

from __future__ import annotations

import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .policy import (
    evaluate_refund_eligibility,
    evaluate_replacement_eligibility,
)

# ---- Provider-neutral tool declarations (JSON Schema) ----
# Each provider serializes these to its own format (functionDeclarations for
# Gemini, tools[].input_schema for Anthropic, tools[].function for OpenAI).

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "name": "get_customer_order",
        "description": (
            "Look up the currently signed-in customer's order. Always call this "
            "first to load order details before doing anything else."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID, e.g. ORD-1001."},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "check_refund_eligibility",
        "description": (
            "Evaluate an order against the REFUND policy (7-day window). "
            "Returns one of: eligible / deny / escalate / needs_media / locked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID to evaluate."},
                "has_acceptable_media": {
                    "type": "boolean",
                    "description": (
                        "True if the customer has attached at least one photo "
                        "or video that you visually confirm shows the item in "
                        "the claimed condition. False if no media yet."
                    ),
                },
            },
            "required": ["order_id", "has_acceptable_media"],
        },
    },
    {
        "name": "check_replacement_eligibility",
        "description": (
            "Evaluate an order against the REPLACEMENT policy (10-day window). "
            "Returns one of: eligible / deny / escalate / needs_media / locked."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "Order ID to evaluate."},
                "has_acceptable_media": {
                    "type": "boolean",
                    "description": (
                        "True if a photo (and a video for DOA / non-working "
                        "claims) is attached and shows the issue. False if not."
                    ),
                },
            },
            "required": ["order_id", "has_acceptable_media"],
        },
    },
    {
        "name": "request_media",
        "description": (
            "Tell the customer that a photo (or short video, for DOA claims) is "
            "needed before progressing. Use this when eligibility returned "
            "needs_media."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["photo", "video", "either"],
                    "description": "Type of evidence required.",
                },
            },
            "required": ["order_id", "kind"],
        },
    },
    {
        "name": "initiate_refund",
        "description": (
            "Initiate a refund. Only valid when check_refund_eligibility "
            "returned outcome=eligible. The actual money-back step happens "
            "after warehouse quality check on the returned item."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "has_acceptable_media": {"type": "boolean"},
            },
            "required": ["order_id", "has_acceptable_media"],
        },
    },
    {
        "name": "initiate_replacement",
        "description": (
            "Initiate a replacement. Only valid when "
            "check_replacement_eligibility returned outcome=eligible."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "reason": {
                    "type": "string",
                    "description": (
                        "Brief reason category, e.g. 'wrong item', 'damaged', "
                        "'DOA', 'wrong size', 'change of mind'."
                    ),
                },
                "has_acceptable_media": {"type": "boolean"},
            },
            "required": ["order_id", "reason", "has_acceptable_media"],
        },
    },
    {
        "name": "deny_request",
        "description": "Deny the request and record the policy-based reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["order_id", "reason"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Flag the order for human review (e.g. orders over $500, ambiguous "
            "or out-of-scope requests). Returns a ticket ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["order_id", "reason"],
        },
    },
]


# ---- DB helpers ----

_ORDER_SELECT = (
    "SELECT o.order_id, o.customer_id, c.name AS customer_name, c.email, "
    "o.product_name, o.order_date, o.order_amount, o.order_status, "
    "o.is_final_sale, o.days_since_delivery, o.is_damaged, o.has_photo_proof, "
    "o.refund_status, o.refund_reason, o.escalation_ticket, o.admin_locked "
    "FROM orders o JOIN customers c USING (customer_id) "
)


def _row_to_order(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "order_id": row["order_id"],
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"],
        "email": row["email"],
        "product_name": row["product_name"],
        "order_date": row["order_date"],
        "order_amount": float(row["order_amount"]),
        "order_status": row["order_status"],
        "is_final_sale": bool(row["is_final_sale"]),
        "days_since_delivery": row["days_since_delivery"],
        "is_damaged": bool(row["is_damaged"]),
        "has_photo_proof": bool(row["has_photo_proof"]),
        "refund_status": row["refund_status"],
        "refund_reason": row["refund_reason"],
        "escalation_ticket": row["escalation_ticket"],
        "admin_locked": bool(row["admin_locked"]),
    }


def _fetch_owned_order(
    conn: sqlite3.Connection, customer_id: str, order_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        _ORDER_SELECT + "WHERE o.order_id = ? AND o.customer_id = ?",
        (order_id, customer_id),
    ).fetchone()
    return _row_to_order(row)


def _record_decision(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str,
    status: str,
    reason: str | None = None,
    ticket: str | None = None,
) -> None:
    # Scope on customer_id too; refuse to touch admin-locked orders.
    conn.execute(
        "UPDATE orders SET refund_status = ?, refund_reason = ?, "
        "escalation_ticket = COALESCE(escalation_ticket, ?), updated_at = ? "
        "WHERE order_id = ? AND customer_id = ? AND admin_locked = 0",
        (
            status,
            reason,
            ticket,
            datetime.now(timezone.utc).isoformat(),
            order_id,
            customer_id,
        ),
    )
    conn.commit()


def _not_found(order_id: str) -> dict[str, Any]:
    return {
        "success": False,
        "found": False,
        "error": (
            f"No order '{order_id}' found on this account. Please pick an "
            "order from your account."
        ),
    }


def _locked_response(order_id: str) -> dict[str, Any]:
    return {
        "success": False,
        "locked": True,
        "error": (
            f"Order {order_id} has been finalized by a human teammate and is "
            "locked. Tell the customer an admin will follow up via email."
        ),
    }


# ---- Tools ----


def get_customer_order(
    conn: sqlite3.Connection, customer_id: str, order_id: str
) -> dict[str, Any]:
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    order["found"] = True
    return order


def check_refund_eligibility(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str,
    has_acceptable_media: bool,
) -> dict[str, Any]:
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    return evaluate_refund_eligibility(order, has_acceptable_media)


def check_replacement_eligibility(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str,
    has_acceptable_media: bool,
) -> dict[str, Any]:
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    return evaluate_replacement_eligibility(order, has_acceptable_media)


def request_media(order_id: str, kind: str) -> dict[str, Any]:
    label = {"photo": "photo", "video": "video", "either": "photo or short video"}.get(
        kind, "photo"
    )
    return {
        "success": True,
        "order_id": order_id,
        "needs_media": True,
        "message": (
            f"Please attach a clear {label} so I can move forward with your "
            "request. Photos should be under 2 MB; videos under 100 MB and 60 "
            "seconds."
        ),
    }


def initiate_refund(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str,
    has_acceptable_media: bool,
    actual_media_count: int,
) -> dict[str, Any]:
    """Server-side guardrail: re-runs the deterministic policy."""
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    if order["admin_locked"]:
        return _locked_response(order_id)

    # Defense against an LLM lying about media: if it claims has_media=True but
    # no media was actually uploaded in this turn, treat as no media.
    truly_has_media = bool(has_acceptable_media and actual_media_count > 0)
    result = evaluate_refund_eligibility(order, truly_has_media)
    if result["outcome"] != "eligible":
        return {
            "success": False,
            "error": f"Refund cannot be initiated: {result['reason']}",
            "suggested_action": _suggested_for(result["outcome"]),
        }

    _record_decision(
        conn, customer_id, order_id, "refund_initiated",
        reason="Refund initiated; pending warehouse quality check on return.",
    )
    return {
        "success": True,
        "order_id": order_id,
        "refund_status": "refund_initiated",
        "message": (
            f"Refund for '{order['product_name']}' (${order['order_amount']:.2f}) "
            "has been initiated. The money-back step completes once we receive "
            "the item and pass the quality check."
        ),
    }


def initiate_replacement(
    conn: sqlite3.Connection,
    customer_id: str,
    order_id: str,
    reason: str,
    has_acceptable_media: bool,
    actual_media_count: int,
) -> dict[str, Any]:
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    if order["admin_locked"]:
        return _locked_response(order_id)

    truly_has_media = bool(has_acceptable_media and actual_media_count > 0)
    result = evaluate_replacement_eligibility(order, truly_has_media)
    if result["outcome"] != "eligible":
        return {
            "success": False,
            "error": f"Replacement cannot be initiated: {result['reason']}",
            "suggested_action": _suggested_for(result["outcome"]),
        }

    _record_decision(
        conn, customer_id, order_id, "replacement_initiated",
        reason=f"Replacement initiated. Reason: {reason}",
    )
    return {
        "success": True,
        "order_id": order_id,
        "refund_status": "replacement_initiated",
        "message": (
            f"Replacement for '{order['product_name']}' has been initiated. "
            f"Reason: {reason}. We'll email shipping details shortly."
        ),
    }


def deny_request(
    conn: sqlite3.Connection, customer_id: str, order_id: str, reason: str
) -> dict[str, Any]:
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    if order["admin_locked"]:
        return _locked_response(order_id)

    _record_decision(conn, customer_id, order_id, "denied", reason=reason)
    return {
        "success": True,
        "order_id": order_id,
        "refund_status": "denied",
        "message": f"Request denied: {reason}",
    }


def escalate_to_human(
    conn: sqlite3.Connection, customer_id: str, order_id: str, reason: str
) -> dict[str, Any]:
    order = _fetch_owned_order(conn, customer_id, order_id)
    if order is None:
        return _not_found(order_id)
    if order["admin_locked"]:
        return _locked_response(order_id)

    ticket = f"ESC-{order_id}-{secrets.token_hex(3).upper()}"
    _record_decision(
        conn, customer_id, order_id, "escalated", reason=reason, ticket=ticket
    )
    return {
        "success": True,
        "order_id": order_id,
        "refund_status": "escalated",
        "ticket_id": ticket,
        "message": f"Escalated to a human reviewer. Reference ticket: {ticket}",
    }


def _suggested_for(outcome: str) -> str:
    return {
        "deny": "deny_request",
        "needs_media": "request_media",
        "escalate": "escalate_to_human",
        "locked": "stop",
    }.get(outcome, "stop")


def dispatch_tool(
    conn: sqlite3.Connection,
    customer_id: str,
    media_count: int,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Route a model function call to its implementation.

    `customer_id` comes from the authenticated session, not the model. The
    actual attached `media_count` is also injected so terminal tools can catch
    an LLM that claims has_acceptable_media=True when nothing was uploaded.
    """
    order_id = str(args.get("order_id", ""))
    has_media = bool(args.get("has_acceptable_media", False))

    if name == "get_customer_order":
        return get_customer_order(conn, customer_id, order_id)
    if name == "check_refund_eligibility":
        return check_refund_eligibility(conn, customer_id, order_id, has_media)
    if name == "check_replacement_eligibility":
        return check_replacement_eligibility(conn, customer_id, order_id, has_media)
    if name == "request_media":
        return request_media(order_id, str(args.get("kind", "either")))
    if name == "initiate_refund":
        return initiate_refund(conn, customer_id, order_id, has_media, media_count)
    if name == "initiate_replacement":
        return initiate_replacement(
            conn, customer_id, order_id,
            str(args.get("reason", "")), has_media, media_count,
        )
    if name == "deny_request":
        return deny_request(
            conn, customer_id, order_id,
            str(args.get("reason", "No reason provided.")),
        )
    if name == "escalate_to_human":
        return escalate_to_human(
            conn, customer_id, order_id,
            str(args.get("reason", "No reason provided.")),
        )
    return {"error": f"Unknown tool '{name}'."}
