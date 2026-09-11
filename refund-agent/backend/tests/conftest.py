"""Pytest fixtures: tempdir DB, seeded data, fresh per-test state, tokens."""

from __future__ import annotations

import os
import tempfile

# MUST happen before any app.* import — pydantic-settings reads env once.
_TMP_DIR = tempfile.mkdtemp(prefix="csa-tests-")
os.environ.setdefault("DB_PATH", os.path.join(_TMP_DIR, "test.db"))
os.environ.setdefault("AUTH_SECRET", "test-secret")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")
# Tighten the test rate limit so the rate-limit test is fast.
os.environ.setdefault("LOGIN_RATE_LIMIT", "5/minute")
# Ensure no LLM key is configured: /chat returns 503 deterministically.
os.environ.setdefault("GEMINI_API_KEY", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("OPENAI_API_KEY", "")

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.database import get_connection, init_db
from app.seed import seed


@pytest.fixture(autouse=True)
def _reset_db_and_buckets():
    """Re-seed and clear in-memory state before EACH test."""
    init_db()
    seed(force=True)
    main_mod._login_buckets.clear()  # type: ignore[attr-defined]
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(main_mod.app)


@pytest.fixture
def conn():
    c = get_connection()
    try:
        yield c
    finally:
        c.close()


def _login_customer(client: TestClient, username: str, password: str) -> str:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _login_admin(client: TestClient, username: str = "admin", password: str = "admin123") -> str:
    r = client.post("/admin/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture
def alice_token(client) -> str:
    return _login_customer(client, "alice", "alice123")


@pytest.fixture
def bob_token(client) -> str:
    return _login_customer(client, "bob", "bob123")


@pytest.fixture
def admin_token(client) -> str:
    return _login_admin(client)
