"""Deterministic policy engine — every branch of refund + replacement."""

from __future__ import annotations

import pytest

from app.policy import (
    ESCALATION_THRESHOLD,
    REFUND_WINDOW_DAYS,
    REPLACEMENT_WINDOW_DAYS,
    evaluate_refund_eligibility,
    evaluate_replacement_eligibility,
)


def _order(**over):
    base = {
        "order_status": "delivered",
        "order_amount": 100.0,
        "is_final_sale": False,
        "days_since_delivery": 1,
        "is_damaged": False,
        "has_photo_proof": False,
        "admin_locked": False,
    }
    base.update(over)
    return base


# ---- Refund ----

def test_refund_admin_locked_returns_locked():
    r = evaluate_refund_eligibility(_order(admin_locked=True), has_media=True)
    assert r["outcome"] == "locked"
    assert r["locked"] is True
    assert r["eligible"] is False


def test_refund_cancelled_denies():
    r = evaluate_refund_eligibility(_order(order_status="cancelled"), has_media=True)
    assert r["outcome"] == "deny"
    assert "cancelled" in r["reason"].lower()


def test_refund_processing_denies():
    r = evaluate_refund_eligibility(_order(order_status="processing"), has_media=True)
    assert r["outcome"] == "deny"


def test_refund_final_sale_denies():
    r = evaluate_refund_eligibility(_order(is_final_sale=True), has_media=True)
    assert r["outcome"] == "deny"
    assert "final sale" in r["reason"].lower()


def test_refund_outside_window_denies():
    r = evaluate_refund_eligibility(
        _order(days_since_delivery=REFUND_WINDOW_DAYS + 1), has_media=True
    )
    assert r["outcome"] == "deny"


def test_refund_boundary_inclusive():
    """Day-7 must STILL be inside the refund window (policy says 'more than 7')."""
    r = evaluate_refund_eligibility(
        _order(days_since_delivery=REFUND_WINDOW_DAYS), has_media=True
    )
    assert r["outcome"] == "eligible"


def test_refund_needs_media_when_no_media():
    r = evaluate_refund_eligibility(_order(), has_media=False)
    assert r["outcome"] == "needs_media"
    assert r["needs_media"] is True


def test_refund_high_value_escalates():
    r = evaluate_refund_eligibility(
        _order(order_amount=ESCALATION_THRESHOLD + 0.01), has_media=True
    )
    assert r["outcome"] == "escalate"
    assert r["requires_escalation"] is True
    assert r["eligible"] is True


def test_refund_boundary_amount_not_escalated():
    r = evaluate_refund_eligibility(
        _order(order_amount=ESCALATION_THRESHOLD), has_media=True
    )
    assert r["outcome"] == "eligible"


def test_refund_eligible_happy_path():
    r = evaluate_refund_eligibility(_order(), has_media=True)
    assert r["outcome"] == "eligible"
    assert r["eligible"] is True


def test_refund_precedence_locked_beats_everything():
    """Locked must win over even cancelled/final-sale."""
    r = evaluate_refund_eligibility(
        _order(admin_locked=True, order_status="cancelled", is_final_sale=True),
        has_media=True,
    )
    assert r["outcome"] == "locked"


def test_refund_precedence_cancelled_beats_final_sale():
    r = evaluate_refund_eligibility(
        _order(order_status="cancelled", is_final_sale=True), has_media=True
    )
    assert "cancelled" in r["reason"].lower()


# ---- Replacement ----

def test_replacement_window_differs_from_refund():
    """Day 9 is outside refund (>7) but inside replacement (<=10)."""
    o = _order(days_since_delivery=9)
    assert evaluate_refund_eligibility(o, True)["outcome"] == "deny"
    assert evaluate_replacement_eligibility(o, True)["outcome"] == "eligible"


def test_replacement_outside_window_denies():
    r = evaluate_replacement_eligibility(
        _order(days_since_delivery=REPLACEMENT_WINDOW_DAYS + 1), has_media=True
    )
    assert r["outcome"] == "deny"


def test_replacement_boundary_inclusive():
    r = evaluate_replacement_eligibility(
        _order(days_since_delivery=REPLACEMENT_WINDOW_DAYS), has_media=True
    )
    assert r["outcome"] == "eligible"


def test_replacement_needs_media_when_no_media():
    r = evaluate_replacement_eligibility(_order(), has_media=False)
    assert r["outcome"] == "needs_media"


def test_replacement_final_sale_denies():
    r = evaluate_replacement_eligibility(_order(is_final_sale=True), has_media=True)
    assert r["outcome"] == "deny"


def test_replacement_admin_locked_locks():
    r = evaluate_replacement_eligibility(_order(admin_locked=True), has_media=True)
    assert r["outcome"] == "locked"


@pytest.mark.parametrize("days", [0, 1, 5, 10])
def test_replacement_within_window_all_eligible(days):
    r = evaluate_replacement_eligibility(
        _order(days_since_delivery=days), has_media=True
    )
    assert r["outcome"] == "eligible"
