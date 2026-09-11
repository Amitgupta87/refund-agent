"""Tool guardrails: ownership scoping, admin lock, has_media truth check."""

from __future__ import annotations

import pytest

from app import tools


# A handful of orders we'll reuse. Customers from seed.
ALICE = "C001"
BOB = "C002"
ALICE_OK = "ORD-1001"            # delivered 3d, normal
ALICE_FINAL = "ORD-1002"         # final sale
ALICE_HIGH_VAL = "ORD-1003"      # $750
BOB_OK = "ORD-1005"              # delivered 6d, bob's


def test_get_customer_order_scoped(conn):
    assert tools.get_customer_order(conn, ALICE, ALICE_OK)["found"] is True
    # Foreign order -> not found, no info leak.
    out = tools.get_customer_order(conn, ALICE, BOB_OK)
    assert out["found"] is False
    assert "this account" in out["error"]


def test_check_eligibility_scoped(conn):
    r = tools.check_refund_eligibility(conn, ALICE, BOB_OK, has_acceptable_media=True)
    assert r.get("found") is False
    r = tools.check_replacement_eligibility(conn, ALICE, BOB_OK, has_acceptable_media=True)
    assert r.get("found") is False


def test_initiate_refund_lying_about_media_is_caught(conn):
    """LLM claims has_acceptable_media=True but no media actually uploaded."""
    out = tools.initiate_refund(conn, ALICE, ALICE_OK, has_acceptable_media=True, actual_media_count=0)
    assert out["success"] is False
    # The eligibility engine reports needs_media → tool surfaces a "photo"/"media" hint.
    err = out["error"].lower()
    assert "photo" in err or "media" in err or "evidence" in err


def test_initiate_refund_happy_path(conn):
    out = tools.initiate_refund(conn, ALICE, ALICE_OK, True, 1)
    assert out["success"] is True
    assert out["refund_status"] == "refund_initiated"
    row = conn.execute(
        "SELECT refund_status FROM orders WHERE order_id=?", (ALICE_OK,)
    ).fetchone()
    assert row["refund_status"] == "refund_initiated"


def test_initiate_refund_final_sale_refused(conn):
    out = tools.initiate_refund(conn, ALICE, ALICE_FINAL, True, 1)
    assert out["success"] is False
    assert out["suggested_action"] == "deny_request"


def test_initiate_refund_high_value_escalates(conn):
    out = tools.initiate_refund(conn, ALICE, ALICE_HIGH_VAL, True, 1)
    assert out["success"] is False
    assert out["suggested_action"] == "escalate_to_human"


def test_initiate_replacement_happy_path(conn):
    out = tools.initiate_replacement(conn, ALICE, ALICE_OK, "wrong item", True, 1)
    assert out["success"] is True
    assert out["refund_status"] == "replacement_initiated"


def test_admin_locked_blocks_every_terminal_tool(conn):
    conn.execute("UPDATE orders SET admin_locked=1 WHERE order_id=?", (ALICE_OK,))
    conn.commit()

    for call in [
        lambda: tools.initiate_refund(conn, ALICE, ALICE_OK, True, 1),
        lambda: tools.initiate_replacement(conn, ALICE, ALICE_OK, "wrong", True, 1),
        lambda: tools.deny_request(conn, ALICE, ALICE_OK, "x"),
        lambda: tools.escalate_to_human(conn, ALICE, ALICE_OK, "x"),
    ]:
        out = call()
        assert out["success"] is False
        assert out.get("locked") is True


def test_foreign_terminal_calls_do_not_mutate_target_row(conn):
    """The defence-in-depth check: even if dispatch is bypassed, tools refuse."""
    # Bob's order before
    before = conn.execute(
        "SELECT refund_status FROM orders WHERE order_id=?", (BOB_OK,)
    ).fetchone()["refund_status"]

    for call in [
        lambda: tools.initiate_refund(conn, ALICE, BOB_OK, True, 1),
        lambda: tools.initiate_replacement(conn, ALICE, BOB_OK, "wrong", True, 1),
        lambda: tools.deny_request(conn, ALICE, BOB_OK, "x"),
        lambda: tools.escalate_to_human(conn, ALICE, BOB_OK, "x"),
    ]:
        assert call()["success"] is False

    after = conn.execute(
        "SELECT refund_status FROM orders WHERE order_id=?", (BOB_OK,)
    ).fetchone()["refund_status"]
    assert before == after, "Foreign tool calls must not mutate target row"


def test_dispatch_routes_correctly(conn):
    out = tools.dispatch_tool(
        conn, ALICE, 1, "check_refund_eligibility",
        {"order_id": ALICE_OK, "has_acceptable_media": True},
    )
    assert out["outcome"] == "eligible"


def test_dispatch_unknown_tool(conn):
    out = tools.dispatch_tool(conn, ALICE, 0, "definitely_not_a_tool", {})
    assert "Unknown tool" in out["error"]


def test_request_media_does_not_touch_db():
    out = tools.request_media("ORD-1001", "either")
    assert out["needs_media"] is True
    assert "photo" in out["message"].lower()


@pytest.mark.parametrize(
    "order_id, expected",
    [
        ("ORD-1006", "deny"),       # cancelled
        ("ORD-1012", "deny"),       # processing
        ("ORD-1004", "deny"),       # outside refund window
        ("ORD-1009", "eligible"),   # ok
    ],
)
def test_check_refund_eligibility_parametric(conn, order_id, expected):
    cid = conn.execute(
        "SELECT customer_id FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()["customer_id"]
    out = tools.check_refund_eligibility(conn, cid, order_id, has_acceptable_media=True)
    assert out["outcome"] == expected
