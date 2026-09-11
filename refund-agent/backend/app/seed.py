"""Seed the SQLite database with login users and their order histories.

Run as a module:        python -m app.seed
Or directly:            python app/seed.py
Force reseed:           python -m app.seed --force

6 customers, 24 orders total. The first five logins exercise live policy
branches (within window, outside window, final sale, escalation, etc.).
Frank's four orders start in PRE-EXISTING decision states so QA can verify
admin-lock / already-actioned / already-escalated behavior without first
having to run the agent through the chat UI.

Demo credentials (username / password):
  alice / alice123   bob / bob123   carol / carol123
  dave  / dave123    eve / eve123   frank / frank123
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

try:
    from app.auth import hash_password
    from app.database import get_connection, init_db
except ModuleNotFoundError:  # pragma: no cover - path shim for direct execution
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from app.auth import hash_password
    from app.database import get_connection, init_db

TODAY = date.today()


def _order_date(days_since_delivery: int | None, fallback_days_ago: int) -> str:
    if days_since_delivery is None:
        return (TODAY - timedelta(days=fallback_days_ago)).isoformat()
    return (TODAY - timedelta(days=days_since_delivery + 3)).isoformat()


# Order tuple:
# (order_id, product_name, amount, status, is_final_sale, days_since_delivery,
#  is_damaged, has_photo_proof, fallback_days_ago, expected_outcome[doc only])
#
# Optional 6th key "preset" (dict) on a user's order sets pre-existing state:
#   {"refund_status": "...", "refund_reason": "...",
#    "escalation_ticket": "...", "admin_locked": 0|1}
USERS = [
    {
        "customer_id": "C001", "name": "Alice Nguyen",
        "email": "alice.nguyen@example.com", "username": "alice", "password": "alice123",
        "orders": [
            ("ORD-1001", "Wireless Earbuds", 89.99, "delivered", 0, 3, 0, 0, 6, "BOTH-OK"),
            ("ORD-1002", "Clearance Sneakers", 129.50, "delivered", 1, 2, 0, 0, 5, "DENY-FINAL"),
            ("ORD-1003", "4K OLED Monitor", 750.00, "delivered", 0, 5, 0, 0, 8, "ESCALATE"),
            ("ORD-1004", "Yoga Mat", 99.99, "delivered", 0, 12, 0, 0, 15, "DENY-WINDOW"),
        ],
    },
    {
        "customer_id": "C002", "name": "Bob Martinez",
        "email": "bob.martinez@example.com", "username": "bob", "password": "bob123",
        "orders": [
            ("ORD-1005", "Cotton T-Shirt", 45.00, "delivered", 0, 6, 0, 0, 9, "BOTH-OK"),
            ("ORD-1006", "Desk Lamp", 60.00, "cancelled", 0, None, 0, 0, 9, "DENY-CANCEL"),
            ("ORD-1007", "Gaming Laptop", 1200.00, "delivered", 0, 4, 0, 0, 7, "ESCALATE"),
            ("ORD-1008", "Glass Blender", 200.00, "delivered", 0, 8, 1, 1, 11, "REPL-ONLY"),
        ],
    },
    {
        "customer_id": "C003", "name": "Carol Davies",
        "email": "carol.davies@example.com", "username": "carol", "password": "carol123",
        "orders": [
            ("ORD-1009", "Ceramic Mug Set", 35.00, "delivered", 0, 1, 0, 0, 4, "BOTH-OK"),
            ("ORD-1010", "Outlet Winter Coat", 250.00, "delivered", 1, 1, 0, 0, 4, "DENY-FINAL"),
            ("ORD-1011", "Dinner Plate Set", 150.00, "delivered", 0, 9, 1, 0, 12, "REPL-ONLY"),
            ("ORD-1012", "Running Shoes", 80.00, "processing", 0, None, 0, 0, 2, "DENY-PROCESSING"),
        ],
    },
    {
        "customer_id": "C004", "name": "Dave Okafor",
        "email": "dave.okafor@example.com", "username": "dave", "password": "dave123",
        "orders": [
            ("ORD-1013", "Espresso Machine", 499.99, "delivered", 0, 7, 0, 0, 10, "BOTH-OK-BOUNDARY"),
            ("ORD-1014", "Bluetooth Speaker", 299.00, "delivered", 0, 15, 0, 0, 18, "DENY-WINDOW"),
            ("ORD-1015", "Standing Desk", 520.00, "cancelled", 0, None, 0, 0, 14, "DENY-CANCEL"),
            ("ORD-1016", "Office Chair", 310.00, "delivered", 0, 2, 1, 0, 5, "REPL-DOA"),
        ],
    },
    {
        "customer_id": "C005", "name": "Eve Thompson",
        "email": "eve.thompson@example.com", "username": "eve", "password": "eve123",
        "orders": [
            ("ORD-1017", "Smartphone", 600.00, "delivered", 0, 4, 0, 0, 7, "ESCALATE"),
            ("ORD-1018", "Phone Case", 75.00, "delivered", 0, 10, 0, 0, 13, "REPL-BOUNDARY"),
            ("ORD-1019", "Tablet", 180.00, "delivered", 0, 25, 0, 0, 28, "DENY-WINDOW"),
            ("ORD-1020", "Designer Sunglasses", 220.00, "delivered", 1, 3, 0, 0, 6, "DENY-FINAL"),
        ],
    },
    # Frank — every order starts in a pre-existing decision state so QA can
    # verify admin-lock / already-actioned UX without first running the agent.
    {
        "customer_id": "C006", "name": "Frank Becker",
        "email": "frank.becker@example.com", "username": "frank", "password": "frank123",
        "orders": [
            ("ORD-1021", "Mechanical Keyboard", 140.00, "delivered", 0, 2, 0, 0, 5, "PRESET-LOCKED"),
            ("ORD-1022", "USB-C Hub", 55.00, "delivered", 0, 4, 0, 0, 7, "PRESET-REFUNDED"),
            ("ORD-1023", "Drone", 899.00, "delivered", 0, 3, 0, 0, 6, "PRESET-ESCALATED"),
            ("ORD-1024", "Hair Dryer", 70.00, "delivered", 0, 5, 0, 0, 8, "PRESET-DENIED"),
        ],
        "presets": {
            "ORD-1021": {
                "refund_status": "denied",
                "refund_reason": "Admin reviewed: outside policy after manual review.",
                "admin_locked": 1,
            },
            "ORD-1022": {
                "refund_status": "refund_initiated",
                "refund_reason": "Refund initiated; pending warehouse quality check on return.",
            },
            "ORD-1023": {
                "refund_status": "escalated",
                "refund_reason": "Order total $899.00 exceeds $500; escalated to a human reviewer.",
                "escalation_ticket": "ESC-ORD-1023-SEED01",
            },
            "ORD-1024": {
                "refund_status": "denied",
                "refund_reason": "Subjective 'bad quality' complaint without DOA evidence (Policy §4).",
            },
        },
    },
]


def _count_customers(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM customers").fetchone()["n"]


def _wipe(conn) -> None:
    conn.executescript(
        "DELETE FROM reasoning_logs; "
        "DELETE FROM media; "
        "DELETE FROM orders; "
        "DELETE FROM customers;"
    )
    conn.commit()


def _existing_ids(conn) -> set[str]:
    rows = conn.execute("SELECT customer_id FROM customers").fetchall()
    return {r["customer_id"] for r in rows}


def seed(force: bool = False) -> None:
    init_db()
    conn = get_connection()
    try:
        if force:
            _wipe(conn)

        existing = _existing_ids(conn)
        new_users = [u for u in USERS if u["customer_id"] not in existing]

        if not new_users:
            print(
                f"Database already has all {len(USERS)} users; skipping. "
                "Use --force to reseed from scratch."
            )
            return

        if existing:
            print(
                f"Topping up: {len(existing)} user(s) already present, "
                f"adding {len(new_users)} missing user(s)."
            )

        order_count = 0
        for user in new_users:
            pw_hash, salt = hash_password(user["password"])
            conn.execute(
                "INSERT INTO customers (customer_id, name, email, username, "
                "password_hash, password_salt) VALUES (?, ?, ?, ?, ?, ?)",
                (user["customer_id"], user["name"], user["email"],
                 user["username"], pw_hash, salt),
            )
            presets = user.get("presets", {})
            for (
                order_id, product_name, amount, status, is_final_sale,
                days_since_delivery, is_damaged, has_photo_proof,
                fallback_days_ago, _expected,
            ) in user["orders"]:
                preset = presets.get(order_id, {})
                conn.execute(
                    """
                    INSERT INTO orders (
                        order_id, customer_id, product_name, order_date, order_amount,
                        order_status, is_final_sale, days_since_delivery,
                        is_damaged, has_photo_proof,
                        refund_status, refund_reason, escalation_ticket, admin_locked
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id, user["customer_id"], product_name,
                        _order_date(days_since_delivery, fallback_days_ago),
                        amount, status, is_final_sale, days_since_delivery,
                        is_damaged, has_photo_proof,
                        preset.get("refund_status", "none"),
                        preset.get("refund_reason"),
                        preset.get("escalation_ticket"),
                        int(preset.get("admin_locked", 0)),
                    ),
                )
                order_count += 1
        conn.commit()
        _print_summary(conn, order_count)
    finally:
        conn.close()


def _print_summary(conn, order_count: int) -> None:
    print(f"Seeded {len(USERS)} login users and {order_count} orders.\n")
    print("Demo credentials:")
    for u in USERS:
        print(f"  {u['username']:<7} / {u['password']:<10} -> {u['name']} "
              f"({len(u['orders'])} orders)")

    rows = conn.execute(
        "SELECT order_amount, order_status, is_final_sale, days_since_delivery, "
        "refund_status, admin_locked FROM orders"
    ).fetchall()
    final_sale = sum(1 for r in rows if r["is_final_sale"])
    over_500 = sum(1 for r in rows if r["order_amount"] > 500)
    outside_refund = sum(
        1 for r in rows
        if r["order_status"] == "delivered"
        and r["days_since_delivery"] is not None
        and r["days_since_delivery"] > 7
    )
    outside_replacement = sum(
        1 for r in rows
        if r["order_status"] == "delivered"
        and r["days_since_delivery"] is not None
        and r["days_since_delivery"] > 10
    )
    cancelled = sum(1 for r in rows if r["order_status"] == "cancelled")
    pre_locked = sum(1 for r in rows if r["admin_locked"])
    pre_actioned = sum(1 for r in rows if r["refund_status"] != "none")
    print("\nEdge-case coverage (under updated policy):")
    print(f"  final-sale items      : {final_sale} (need >=2)")
    print(f"  orders over $500      : {over_500} (need >=2)")
    print(f"  outside  7-day refund : {outside_refund} (need >=2)")
    print(f"  outside 10-day replace: {outside_replacement} (need >=2)")
    print(f"  cancelled orders      : {cancelled} (need >=1)")
    print(f"  admin-locked at seed  : {pre_locked} (need >=1)")
    print(f"  preset decision rows  : {pre_actioned} (need >=1)")


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
