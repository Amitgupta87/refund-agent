-- ────────────────────────────────────────────────────────────────────────
-- Customer Support Agent — SQLite schema
-- customers ⟶ orders (1:N); reasoning_logs persists agent turns; media stores
-- user-uploaded photos/videos referenced by chat requests.
-- ────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    customer_id   TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id            TEXT PRIMARY KEY,
    customer_id         TEXT NOT NULL REFERENCES customers(customer_id),
    product_name        TEXT NOT NULL,
    order_date          TEXT NOT NULL,
    order_amount        REAL NOT NULL,
    order_status        TEXT NOT NULL CHECK (order_status IN ('delivered', 'processing', 'cancelled')),
    is_final_sale       INTEGER NOT NULL DEFAULT 0,
    days_since_delivery INTEGER,
    is_damaged          INTEGER NOT NULL DEFAULT 0,
    has_photo_proof     INTEGER NOT NULL DEFAULT 0,

    -- Mutated by the terminal tools and by admin overrides.
    refund_status       TEXT NOT NULL DEFAULT 'none'
                        CHECK (refund_status IN ('none', 'refund_initiated',
                                                  'replacement_initiated',
                                                  'denied', 'escalated')),
    refund_reason       TEXT,
    escalation_ticket   TEXT,
    -- 1 once a human admin has overridden the decision; the agent cannot act
    -- on the order until an admin unlocks it.
    admin_locked        INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);

CREATE TABLE IF NOT EXISTS reasoning_logs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id          TEXT NOT NULL UNIQUE,
    conversation_id  TEXT,
    customer_id      TEXT,
    order_id         TEXT,
    user_message     TEXT NOT NULL,
    reasoning_steps  TEXT NOT NULL DEFAULT '[]',
    tools_called     TEXT NOT NULL DEFAULT '[]',
    final_response   TEXT NOT NULL DEFAULT '',
    decision         TEXT NOT NULL DEFAULT 'none',
    security_flag    INTEGER NOT NULL DEFAULT 0,
    timestamp        TEXT NOT NULL,
    media_ids        TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON reasoning_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_decision ON reasoning_logs(decision);

CREATE TABLE IF NOT EXISTS media (
    media_id     TEXT PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customers(customer_id),
    mime_type    TEXT NOT NULL,
    kind         TEXT NOT NULL CHECK (kind IN ('image', 'video')),
    size_bytes   INTEGER NOT NULL,
    duration_sec REAL,                          -- video only
    data         BLOB NOT NULL,                 -- raw bytes (file-backed in a real system)
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_media_customer ON media(customer_id);
