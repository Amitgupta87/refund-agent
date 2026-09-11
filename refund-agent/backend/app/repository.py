"""Persistence for reasoning logs + read queries + admin override/unlock."""

from __future__ import annotations

import json
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from .models import ReasoningLog, ToolCall


# ---- Reasoning log persistence ----

def save_log(conn: sqlite3.Connection, log: ReasoningLog) -> None:
    conn.execute(
        """
        INSERT INTO reasoning_logs (
            turn_id, conversation_id, customer_id, order_id, user_message,
            reasoning_steps, tools_called, final_response, decision,
            security_flag, timestamp, media_ids
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            log.turn_id, log.conversation_id, log.customer_id, log.order_id,
            log.user_message,
            json.dumps(log.reasoning_steps),
            json.dumps([tc.model_dump() for tc in log.tools_called]),
            log.final_response, log.decision,
            1 if log.security_flag else 0,
            log.timestamp,
            json.dumps(log.media_ids),
        ),
    )
    conn.commit()


def _row_to_log_entry(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "turn_id": row["turn_id"],
        "conversation_id": row["conversation_id"],
        "customer_id": row["customer_id"],
        "customer_name": row["customer_name"],
        "order_id": row["order_id"],
        "user_message": row["user_message"],
        "reasoning_steps": json.loads(row["reasoning_steps"] or "[]"),
        "tools_called": json.loads(row["tools_called"] or "[]"),
        "final_response": row["final_response"],
        "decision": row["decision"],
        "security_flag": bool(row["security_flag"]),
        "timestamp": row["timestamp"],
        "media_ids": json.loads(row["media_ids"] or "[]"),
    }


def list_logs(
    conn: sqlite3.Connection,
    decision: str | None = None,
    flagged: bool | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    query = (
        "SELECT r.*, c.name AS customer_name FROM reasoning_logs r "
        "LEFT JOIN customers c ON c.customer_id = r.customer_id WHERE 1=1"
    )
    params: list[Any] = []
    if decision and decision not in ("all", ""):
        query += " AND r.decision = ?"
        params.append(decision)
    if flagged:
        query += " AND r.security_flag = 1"
    query += " ORDER BY r.id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(query, params).fetchall()
    return [_row_to_log_entry(r) for r in rows]


# ---- Customer + admin queries ----

def get_customer_by_username(
    conn: sqlite3.Connection, username: str
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT customer_id, name, email, username, password_hash, password_salt "
        "FROM customers WHERE username = ?",
        (username,),
    ).fetchone()


def get_conversation_history(
    conn: sqlite3.Connection,
    conversation_id: str,
    customer_id: str,
    order_id: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Return prior (user_message, final_response, media_count) turns for this
    chat, oldest first. All three filters are server-trusted so a token holder
    cannot read another customer's or order's transcript."""
    rows = conn.execute(
        "SELECT user_message, final_response, media_ids "
        "FROM reasoning_logs "
        "WHERE conversation_id = ? AND customer_id = ? AND order_id = ? "
        "  AND user_message NOT LIKE '[ADMIN%' "
        "ORDER BY id ASC LIMIT ?",
        (conversation_id, customer_id, order_id, limit),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            media_count = len(json.loads(r["media_ids"] or "[]"))
        except (ValueError, json.JSONDecodeError):
            media_count = 0
        out.append({
            "user_message": r["user_message"],
            "final_response": r["final_response"],
            "media_count": media_count,
        })
    return out


def customer_owns_order(
    conn: sqlite3.Connection, customer_id: str, order_id: str
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM orders WHERE order_id = ? AND customer_id = ? LIMIT 1",
        (order_id, customer_id),
    ).fetchone()
    return row is not None


def list_orders_for_customer(
    conn: sqlite3.Connection, customer_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT order_id, product_name, order_date, order_amount, order_status, "
        "is_final_sale, days_since_delivery, is_damaged, has_photo_proof, "
        "refund_status, refund_reason, escalation_ticket, admin_locked "
        "FROM orders WHERE customer_id = ? ORDER BY order_id",
        (customer_id,),
    ).fetchall()
    return [
        {
            "order_id": r["order_id"],
            "product_name": r["product_name"],
            "order_date": r["order_date"],
            "order_amount": float(r["order_amount"]),
            "order_status": r["order_status"],
            "is_final_sale": bool(r["is_final_sale"]),
            "days_since_delivery": r["days_since_delivery"],
            "is_damaged": bool(r["is_damaged"]),
            "has_photo_proof": bool(r["has_photo_proof"]),
            "refund_status": r["refund_status"],
            "refund_reason": r["refund_reason"],
            "escalation_ticket": r["escalation_ticket"],
            "admin_locked": bool(r["admin_locked"]),
        }
        for r in rows
    ]


def list_orders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT o.customer_id, c.name AS customer_name, o.order_id, "
        "o.product_name, o.order_amount, o.order_status, o.is_final_sale, "
        "o.days_since_delivery, o.refund_status, o.refund_reason, "
        "o.escalation_ticket, o.admin_locked, o.updated_at "
        "FROM orders o JOIN customers c USING (customer_id) "
        "ORDER BY o.order_id"
    ).fetchall()
    return [
        {
            "customer_id": r["customer_id"],
            "customer_name": r["customer_name"],
            "order_id": r["order_id"],
            "product_name": r["product_name"],
            "order_amount": float(r["order_amount"]),
            "order_status": r["order_status"],
            "is_final_sale": bool(r["is_final_sale"]),
            "days_since_delivery": r["days_since_delivery"],
            "refund_status": r["refund_status"],
            "refund_reason": r["refund_reason"],
            "escalation_ticket": r["escalation_ticket"],
            "admin_locked": bool(r["admin_locked"]),
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


def get_admin_order(
    conn: sqlite3.Connection, order_id: str
) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT o.customer_id, c.name AS customer_name, o.order_id, "
        "o.product_name, o.order_amount, o.order_status, o.is_final_sale, "
        "o.days_since_delivery, o.refund_status, o.refund_reason, "
        "o.escalation_ticket, o.admin_locked, o.updated_at "
        "FROM orders o JOIN customers c USING (customer_id) WHERE o.order_id = ?",
        (order_id,),
    ).fetchone()
    if r is None:
        return None
    return {
        "customer_id": r["customer_id"],
        "customer_name": r["customer_name"],
        "order_id": r["order_id"],
        "product_name": r["product_name"],
        "order_amount": float(r["order_amount"]),
        "order_status": r["order_status"],
        "is_final_sale": bool(r["is_final_sale"]),
        "days_since_delivery": r["days_since_delivery"],
        "refund_status": r["refund_status"],
        "refund_reason": r["refund_reason"],
        "escalation_ticket": r["escalation_ticket"],
        "admin_locked": bool(r["admin_locked"]),
        "updated_at": r["updated_at"],
    }


# ---- Admin override + lock ----

def apply_admin_override(
    conn: sqlite3.Connection,
    order_id: str,
    decision: str,
    reason: str | None,
    admin_user: str,
) -> dict[str, Any] | None:
    """Manually set an order's decision, LOCK the order so the agent cannot
    touch it, and write an audited reasoning_log entry."""
    row = conn.execute(
        "SELECT customer_id FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    if row is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    new_ticket = (
        f"ESC-{order_id}-{secrets.token_hex(3).upper()}"
        if decision == "escalated"
        else None
    )
    final_reason = reason or f"Manually set to '{decision}' by admin."

    conn.execute(
        "UPDATE orders SET refund_status = ?, refund_reason = ?, "
        "escalation_ticket = COALESCE(escalation_ticket, ?), "
        "admin_locked = 1, updated_at = ? WHERE order_id = ?",
        (decision, final_reason, new_ticket, now, order_id),
    )

    audit = ReasoningLog(
        turn_id=uuid.uuid4().hex,
        conversation_id=uuid.uuid4().hex,
        customer_id=row["customer_id"],
        order_id=order_id,
        user_message=f"[ADMIN OVERRIDE by {admin_user}]",
        reasoning_steps=[
            f"Admin '{admin_user}' manually set the decision to '{decision}' "
            f"and locked the order. Reason: {final_reason}"
        ],
        tools_called=[
            ToolCall(
                tool="admin_override",
                input={"decision": decision, "reason": final_reason},
                output={
                    "refund_status": decision,
                    "ticket_id": new_ticket,
                    "admin_locked": True,
                },
            )
        ],
        final_response=(
            f"Decision for {order_id} overridden to '{decision}' by "
            f"{admin_user}. Order is now locked."
        ),
        decision=decision,  # type: ignore[arg-type]
        security_flag=False,
        timestamp=now,
    )
    save_log(conn, audit)
    return get_admin_order(conn, order_id)


def unlock_order(
    conn: sqlite3.Connection, order_id: str, admin_user: str
) -> dict[str, Any] | None:
    """Clear the admin lock so the agent can resume action on this order."""
    row = conn.execute(
        "SELECT customer_id FROM orders WHERE order_id = ?", (order_id,)
    ).fetchone()
    if row is None:
        return None

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE orders SET admin_locked = 0, updated_at = ? WHERE order_id = ?",
        (now, order_id),
    )

    audit = ReasoningLog(
        turn_id=uuid.uuid4().hex,
        conversation_id=uuid.uuid4().hex,
        customer_id=row["customer_id"],
        order_id=order_id,
        user_message=f"[ADMIN UNLOCK by {admin_user}]",
        reasoning_steps=[
            f"Admin '{admin_user}' unlocked {order_id}; agent may act on it again."
        ],
        tools_called=[
            ToolCall(
                tool="admin_unlock",
                input={},
                output={"admin_locked": False},
            )
        ],
        final_response=f"{order_id} unlocked by {admin_user}.",
        decision="none",
        security_flag=False,
        timestamp=now,
    )
    save_log(conn, audit)
    return get_admin_order(conn, order_id)
