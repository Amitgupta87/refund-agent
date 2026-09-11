"""Auth: password hashing, token signing, role enforcement."""

from __future__ import annotations

import base64
import json
import time

from app import auth


def test_hash_verify_roundtrip():
    h, salt = auth.hash_password("alice123")
    assert auth.verify_password("alice123", h, salt) is True
    assert auth.verify_password("nope", h, salt) is False


def test_token_roundtrip_customer():
    tok = auth.create_token("C001")
    payload = auth.verify_token(tok)
    assert payload is not None and payload["sub"] == "C001"
    assert payload["role"] == "customer"


def test_token_roundtrip_admin():
    tok = auth.create_token("admin", role="admin")
    payload = auth.verify_token(tok)
    assert payload is not None and payload["role"] == "admin"


def test_tampered_token_rejected():
    tok = auth.create_token("C001")
    assert auth.verify_token(tok[:-2] + "xx") is None
    # Flipping a character mid-body invalidates the signature.
    head, sig = tok.split(".")
    bad = head[:-2] + "AA" + "." + sig
    assert auth.verify_token(bad) is None


def test_expired_token_rejected(monkeypatch):
    """An admin token with a past expiry must fail."""
    body = base64.urlsafe_b64encode(
        json.dumps({"sub": "admin", "role": "admin", "exp": int(time.time()) - 10})
        .encode()
    ).decode().rstrip("=")
    # We need a valid signature for this body. Use the same secret-aware signer.
    sig = auth._sign(body)
    expired_tok = f"{body}.{sig}"
    assert auth.verify_token(expired_tok) is None


def test_verify_admin_credentials_constant_time():
    assert auth.verify_admin_credentials("admin", "admin123") is True
    assert auth.verify_admin_credentials("admin", "nope") is False
    assert auth.verify_admin_credentials("not-admin", "admin123") is False
