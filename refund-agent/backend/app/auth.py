"""Lightweight customer authentication.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user salt. Sessions
use a compact HMAC-signed token (header-less JWT-style) so no external auth
dependency is needed. This is intentionally simple for the interview scope but
avoids the obvious sins (no plaintext passwords, signed + expiring tokens).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Header, HTTPException

from .config import settings

_PBKDF2_ROUNDS = 100_000


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    """Return (hash_hex, salt) for a password, generating a salt if absent."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ROUNDS
    )
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    calculated, _ = hash_password(password, salt)
    return hmac.compare_digest(calculated, password_hash)


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _sign(body: str) -> str:
    mac = hmac.new(
        settings.auth_secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256
    ).digest()
    return _b64url_encode(mac)


def create_token(sub: str, role: str = "customer") -> str:
    """Create a signed, expiring token for a subject with a role claim."""
    payload = {
        "sub": sub,
        "role": role,
        "exp": int(time.time()) + settings.token_ttl_seconds,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify_token(token: str) -> dict | None:
    """Return the decoded payload if the token is valid and unexpired, else None."""
    parts = token.split(".")
    if len(parts) != 2:
        return None
    body, signature = parts
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        payload = json.loads(_b64url_decode(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def verify_admin_credentials(username: str, password: str) -> bool:
    """Constant-time check of admin credentials from configuration."""
    user_ok = hmac.compare_digest(username, settings.admin_username)
    pass_ok = hmac.compare_digest(password, settings.admin_password)
    return user_ok and pass_ok


def _bearer_payload(authorization: str | None) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header.")
    payload = verify_token(authorization[7:].strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")
    return payload


def get_current_customer_id(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: require a valid customer token, return its customer_id."""
    payload = _bearer_payload(authorization)
    if payload.get("role") != "customer" or not isinstance(payload.get("sub"), str):
        raise HTTPException(status_code=401, detail="Customer session required.")
    return payload["sub"]


def get_current_admin(authorization: str | None = Header(default=None)) -> str:
    """FastAPI dependency: require a valid admin token, return the admin username."""
    payload = _bearer_payload(authorization)
    if payload.get("role") != "admin" or not isinstance(payload.get("sub"), str):
        raise HTTPException(status_code=403, detail="Admin session required.")
    return payload["sub"]
