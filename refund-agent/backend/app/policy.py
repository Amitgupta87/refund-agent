"""Customer-support policy logic — deterministic, code-level source of truth.

`load_policy_text()` provides the human-readable policy injected into the LLM
system prompt. The evaluator functions encode the SAME rules as `policy.txt §10`
so a tool decision can never contradict the written policy regardless of what
the model produces.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import settings

REFUND_WINDOW_DAYS = 7
REPLACEMENT_WINDOW_DAYS = 10
ESCALATION_THRESHOLD = 500.0


@lru_cache(maxsize=1)
def load_policy_text() -> str:
    """Read and cache the policy document once."""
    return settings.policy_file.read_text(encoding="utf-8")


def _deny(reason: str) -> dict[str, Any]:
    return {
        "outcome": "deny",
        "eligible": False,
        "reason": reason,
        "requires_escalation": False,
        "needs_media": False,
        "locked": False,
    }


def _needs_media(reason: str) -> dict[str, Any]:
    return {
        "outcome": "needs_media",
        "eligible": False,
        "reason": reason,
        "requires_escalation": False,
        "needs_media": True,
        "locked": False,
    }


def _escalate(reason: str) -> dict[str, Any]:
    return {
        "outcome": "escalate",
        "eligible": True,
        "reason": reason,
        "requires_escalation": True,
        "needs_media": False,
        "locked": False,
    }


def _ok(reason: str) -> dict[str, Any]:
    return {
        "outcome": "eligible",
        "eligible": True,
        "reason": reason,
        "requires_escalation": False,
        "needs_media": False,
        "locked": False,
    }


def _locked() -> dict[str, Any]:
    return {
        "outcome": "locked",
        "eligible": False,
        "reason": (
            "This order has been finalized by a human teammate and is locked. "
            "An admin will follow up with the customer."
        ),
        "requires_escalation": False,
        "needs_media": False,
        "locked": True,
    }


def _common_pre_checks(order: dict[str, Any]) -> dict[str, Any] | None:
    """Apply the checks shared by both refund and replacement paths."""
    if order.get("admin_locked"):
        return _locked()
    status = order["order_status"]
    if status == "cancelled":
        return _deny(
            "Order is cancelled; cancellations are handled by billing (Policy §8.1)."
        )
    if status == "processing":
        return _deny(
            "Order has not been delivered yet; refunds and replacements apply "
            "only after delivery (Policy §8.2)."
        )
    if order["is_final_sale"]:
        return _deny(
            "Item is marked FINAL SALE and is non-refundable and non-replaceable "
            "under any circumstance (Policy §6)."
        )
    return None


def evaluate_refund_eligibility(
    order: dict[str, Any], has_media: bool
) -> dict[str, Any]:
    """Apply Policy §10 REFUND order (first matching rule wins)."""
    blocked = _common_pre_checks(order)
    if blocked is not None:
        return blocked

    days = order["days_since_delivery"]
    if days is not None and days > REFUND_WINDOW_DAYS:
        return _deny(
            f"Delivered {days} days ago, beyond the {REFUND_WINDOW_DAYS}-day "
            "refund window (Policy §2.4)."
        )

    if not has_media:
        return _needs_media(
            "A refund needs at least one photo of the item before we can start "
            "the return — could you attach one? (Policy §2.3)"
        )

    amount = float(order["order_amount"])
    if amount > ESCALATION_THRESHOLD:
        return _escalate(
            f"Order total ${amount:.2f} exceeds ${ESCALATION_THRESHOLD:.0f}; "
            "must be escalated to a human reviewer (Policy §7)."
        )

    return _ok(
        "Within the 7-day refund window with acceptable proof; refund can be "
        "initiated pending warehouse quality check."
    )


def evaluate_replacement_eligibility(
    order: dict[str, Any], has_media: bool
) -> dict[str, Any]:
    """Apply Policy §10 REPLACEMENT order (first matching rule wins)."""
    blocked = _common_pre_checks(order)
    if blocked is not None:
        return blocked

    days = order["days_since_delivery"]
    if days is not None and days > REPLACEMENT_WINDOW_DAYS:
        return _deny(
            f"Delivered {days} days ago, beyond the {REPLACEMENT_WINDOW_DAYS}-day "
            "replacement window (Policy §3.1)."
        )

    if not has_media:
        return _needs_media(
            "A replacement needs at least one photo (and a short video for "
            "DOA / not-working claims) — could you attach one? (Policy §5)"
        )

    amount = float(order["order_amount"])
    if amount > ESCALATION_THRESHOLD:
        return _escalate(
            f"Order total ${amount:.2f} exceeds ${ESCALATION_THRESHOLD:.0f}; "
            "must be escalated to a human reviewer (Policy §7)."
        )

    return _ok(
        "Within the 10-day replacement window with acceptable proof; "
        "replacement can be initiated."
    )
