"""End-to-end HTTP behavior via FastAPI TestClient."""

from __future__ import annotations


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["llm_key_configured"] is False  # no key in tests


def test_customer_login_bad_creds(client):
    assert client.post("/auth/login", json={"username": "alice", "password": "x"}).status_code == 401


def test_customer_login_good_returns_profile(client):
    r = client.post("/auth/login", json={"username": "alice", "password": "alice123"})
    assert r.status_code == 200
    body = r.json()
    assert body["customer"]["username"] == "alice"
    assert body["customer"]["customer_id"] == "C001"


def test_me_orders_requires_auth(client):
    assert client.get("/me/orders").status_code == 401


def test_me_orders_scoped_to_customer(client, alice_token, bob_token):
    a_orders = client.get(
        "/me/orders", headers={"Authorization": f"Bearer {alice_token}"}
    ).json()
    b_orders = client.get(
        "/me/orders", headers={"Authorization": f"Bearer {bob_token}"}
    ).json()
    assert len(a_orders) == 4 and len(b_orders) == 4
    assert {o["order_id"] for o in a_orders}.isdisjoint(
        {o["order_id"] for o in b_orders}
    )


def test_chat_requires_auth(client):
    assert client.post(
        "/chat", json={"order_id": "ORD-1001", "message": "hi"}
    ).status_code == 401


def test_chat_cross_account_404(client, alice_token):
    r = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={"order_id": "ORD-1005", "message": "refund please"},  # bob's
    )
    assert r.status_code == 404
    assert "this account" in r.json()["detail"]


def test_chat_validation(client, alice_token):
    r = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={"message": "x"},
    )
    assert r.status_code == 422


def test_chat_503_when_llm_unconfigured(client, alice_token):
    r = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {alice_token}"},
        json={"order_id": "ORD-1001", "message": "refund"},
    )
    assert r.status_code == 503


# ---- Admin ----

def test_admin_endpoints_reject_customer_token(client, alice_token):
    h = {"Authorization": f"Bearer {alice_token}"}
    assert client.get("/admin/logs", headers=h).status_code == 403
    assert client.get("/admin/orders", headers=h).status_code == 403


def test_admin_endpoints_reject_no_token(client):
    assert client.get("/admin/orders").status_code == 401


def test_admin_login_bad(client):
    assert client.post(
        "/admin/login", json={"username": "admin", "password": "nope"}
    ).status_code == 401


def test_admin_override_locks_and_audits(client, admin_token, conn):
    r = client.post(
        "/admin/orders/ORD-1001/override",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "escalated", "reason": "VIP"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["refund_status"] == "escalated"
    assert body["admin_locked"] is True
    assert body["escalation_ticket"]

    logs = client.get(
        "/admin/logs?limit=5",
        headers={"Authorization": f"Bearer {admin_token}"},
    ).json()
    assert any(
        l["order_id"] == "ORD-1001" and l["user_message"].startswith("[ADMIN OVERRIDE")
        for l in logs
    )


def test_admin_unlock_restores_agent_access(client, admin_token, conn):
    # Lock
    client.post(
        "/admin/orders/ORD-1001/override",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "denied", "reason": "manual"},
    )
    # Confirm locked at DB level
    assert conn.execute(
        "SELECT admin_locked FROM orders WHERE order_id='ORD-1001'"
    ).fetchone()["admin_locked"] == 1

    # Unlock
    r = client.post(
        "/admin/orders/ORD-1001/unlock",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    assert r.json()["admin_locked"] is False


def test_admin_override_unknown_order_404(client, admin_token):
    r = client.post(
        "/admin/orders/NOPE-9999/override",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "denied"},
    )
    assert r.status_code == 404


def test_admin_override_bad_decision_422(client, admin_token):
    r = client.post(
        "/admin/orders/ORD-1001/override",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "refunded"},  # not one of the allowed literals
    )
    assert r.status_code == 422


# ---- Rate limit ----

def test_login_rate_limit_fires(client):
    codes = [
        client.post(
            "/auth/login", json={"username": "alice", "password": "wrong"}
        ).status_code
        for _ in range(8)
    ]
    assert 429 in codes
    # First few should be 401 (auth failures) before the limit kicks in.
    assert codes[0] == 401
