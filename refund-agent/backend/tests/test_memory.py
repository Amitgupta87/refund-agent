"""Conversation memory: agent loads prior turns scoped to customer + order + conv."""

from __future__ import annotations

import json
import uuid

from app import repository
from app.models import ReasoningLog


def _make_log(
    conn,
    *,
    conversation_id: str,
    customer_id: str,
    order_id: str,
    user_message: str,
    final_response: str,
    media_ids: list[str] | None = None,
) -> None:
    repository.save_log(
        conn,
        ReasoningLog(
            turn_id=uuid.uuid4().hex,
            conversation_id=conversation_id,
            customer_id=customer_id,
            order_id=order_id,
            user_message=user_message,
            final_response=final_response,
            decision="none",
            security_flag=False,
            timestamp="2026-01-01T00:00:00Z",
            media_ids=list(media_ids or []),
        ),
    )


def test_history_returns_prior_turns_in_order(conn):
    conv = uuid.uuid4().hex
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="i want a refund", final_response="what's the reason?")
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="it's broken", final_response="please attach a photo",
              media_ids=[])
    history = repository.get_conversation_history(conn, conv, "C001", "ORD-1001")
    assert len(history) == 2
    assert history[0]["user_message"] == "i want a refund"
    assert history[1]["user_message"] == "it's broken"
    assert history[0]["media_count"] == 0


def test_history_counts_attached_media(conn):
    conv = uuid.uuid4().hex
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="here's the photo", final_response="thanks!",
              media_ids=["m-1", "m-2"])
    history = repository.get_conversation_history(conn, conv, "C001", "ORD-1001")
    assert history[0]["media_count"] == 2


def test_history_isolated_by_conversation(conn):
    conv_a = uuid.uuid4().hex
    conv_b = uuid.uuid4().hex
    _make_log(conn, conversation_id=conv_a, customer_id="C001", order_id="ORD-1001",
              user_message="A turn", final_response="A reply")
    _make_log(conn, conversation_id=conv_b, customer_id="C001", order_id="ORD-1001",
              user_message="B turn", final_response="B reply")
    assert len(repository.get_conversation_history(conn, conv_a, "C001", "ORD-1001")) == 1
    assert len(repository.get_conversation_history(conn, conv_b, "C001", "ORD-1001")) == 1


def test_history_isolated_by_customer(conn):
    """A token holder MUST NOT see another customer's chat, even with the same
    conversation_id (defense in depth — UUIDs already collision-resistant)."""
    conv = uuid.uuid4().hex
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="alice's secret", final_response="ok")
    # Bob asking the same conversation_id sees nothing.
    assert repository.get_conversation_history(conn, conv, "C002", "ORD-1001") == []


def test_history_isolated_by_order(conn):
    """Chats on different orders never bleed into each other."""
    conv = uuid.uuid4().hex
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="about 1001", final_response="ok")
    assert repository.get_conversation_history(conn, conv, "C001", "ORD-1004") == []


def test_history_excludes_admin_override_audit_entries(conn):
    """Admin-override audit logs share the orders' customer_id but should never
    appear as customer-side chat turns."""
    conv = uuid.uuid4().hex
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="i want a refund", final_response="checking")
    _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
              user_message="[ADMIN OVERRIDE by admin]", final_response="locked")
    history = repository.get_conversation_history(conn, conv, "C001", "ORD-1001")
    assert len(history) == 1
    assert history[0]["user_message"] == "i want a refund"


def test_history_respects_limit(conn):
    conv = uuid.uuid4().hex
    for i in range(40):
        _make_log(conn, conversation_id=conv, customer_id="C001", order_id="ORD-1001",
                  user_message=f"turn {i}", final_response="ok")
    history = repository.get_conversation_history(
        conn, conv, "C001", "ORD-1001", limit=10
    )
    assert len(history) == 10
    # Oldest-first ordering preserved.
    assert history[0]["user_message"] == "turn 0"
