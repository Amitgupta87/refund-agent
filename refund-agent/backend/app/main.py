"""FastAPI application entrypoint for the Customer Support Agent.

Exposes:
  - Customer auth + their own orders + chat (with optional media attachments).
  - Admin auth + audit log + per-order override / unlock.
  - Media upload endpoint (auth-scoped, validated for type/size/duration).
  - /health for the docker healthcheck.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import asynccontextmanager

from collections import defaultdict
from time import time as _now

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import agent, auth, media, repository
from .config import settings
from .database import get_db, init_db
from .llm import LLMError
from .models import (
    AdminLogEntry,
    AdminLoginRequest,
    AdminLoginResponse,
    AdminOrder,
    ChatRequest,
    ChatResponse,
    CustomerProfile,
    LoginRequest,
    LoginResponse,
    MediaUploadResponse,
    OrderSummary,
    OverrideRequest,
    UnlockResponse,
)


class HealthResponse(BaseModel):
    status: str
    service: str
    llm_provider: str
    model: str
    llm_key_configured: bool


# ---- Rate limiting (in-memory, per IP, sliding window) ----

def _parse_rate(spec: str) -> tuple[int, float]:
    """'5/minute' -> (5, 60.0). Supports 'second' | 'minute' | 'hour'."""
    count_str, _, unit = spec.partition("/")
    seconds = {"second": 1.0, "minute": 60.0, "hour": 3600.0}.get(unit.strip(), 60.0)
    try:
        count = max(1, int(count_str.strip()))
    except ValueError:
        count = 5
    return count, seconds


_LOGIN_LIMIT, _LOGIN_WINDOW = _parse_rate(settings.login_rate_limit)
_login_buckets: dict[str, list[float]] = defaultdict(list)


def login_rate_limit(request: Request) -> None:
    """Per-IP sliding-window limit for the two login endpoints."""
    ip = request.client.host if request.client else "unknown"
    now = _now()
    bucket = _login_buckets[ip]
    cutoff = now - _LOGIN_WINDOW
    while bucket and bucket[0] < cutoff:
        bucket.pop(0)
    if len(bucket) >= _LOGIN_LIMIT:
        retry_in = int(bucket[0] + _LOGIN_WINDOW - now) + 1
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many login attempts. Limit is {_LOGIN_LIMIT} per "
                f"{int(_LOGIN_WINDOW)}s. Try again in ~{retry_in}s."
            ),
        )
    bucket.append(now)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _warn_if_weak_defaults()
    yield


def _warn_if_weak_defaults() -> None:
    log = logging.getLogger("customer-support-agent")
    weak: list[str] = []
    if settings.auth_secret == "dev-only-change-me-in-production":
        weak.append("AUTH_SECRET")
    if settings.admin_password == "admin123":
        weak.append("ADMIN_PASSWORD")
    if not settings.active_llm_key_configured:
        weak.append(
            f"{settings.llm_provider.upper()}_API_KEY (unset; /chat will 503)"
        )
    if weak:
        log.warning(
            "Sensitive settings using dev defaults / unset: %s. Override via .env "
            "before any non-local use.",
            ", ".join(weak),
        )


app = FastAPI(
    title="Customer Support Agent API",
    version="2.0.0",
    description=(
        "AI customer-support agent for e-commerce refunds, replacements, and "
        "damage handling — provider-agnostic (Gemini / Anthropic / OpenAI)."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- System ----


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="customer-support-agent-backend",
        llm_provider=settings.llm_provider,
        model=settings.active_llm_model,
        llm_key_configured=settings.active_llm_key_configured,
    )


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"message": "Customer Support Agent API. See /docs for the OpenAPI UI."}


# ---- Customer auth ----


@app.post("/auth/login", response_model=LoginResponse, tags=["auth"])
def login(
    req: LoginRequest,
    conn: sqlite3.Connection = Depends(get_db),
    _rl: None = Depends(login_rate_limit),
) -> LoginResponse:
    row = repository.get_customer_by_username(conn, req.username)
    if row is None or not auth.verify_password(
        req.password, row["password_hash"], row["password_salt"]
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return LoginResponse(
        token=auth.create_token(row["customer_id"]),
        customer=CustomerProfile(
            customer_id=row["customer_id"],
            name=row["name"],
            email=row["email"],
            username=row["username"],
        ),
    )


# ---- Customer-scoped endpoints ----


@app.get("/me/orders", response_model=list[OrderSummary], tags=["customer"])
def my_orders(
    customer_id: str = Depends(auth.get_current_customer_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[OrderSummary]:
    return [
        OrderSummary(**row)
        for row in repository.list_orders_for_customer(conn, customer_id)
    ]


@app.post("/media", response_model=MediaUploadResponse, tags=["customer"])
async def upload_media(
    file: UploadFile,
    customer_id: str = Depends(auth.get_current_customer_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> MediaUploadResponse:
    """Validate and store one photo or video; returns a media_id."""
    metadata = await media.store_upload(conn, customer_id, file)
    return MediaUploadResponse(**metadata)


@app.post("/chat", response_model=ChatResponse, tags=["agent"])
def chat(
    req: ChatRequest,
    customer_id: str = Depends(auth.get_current_customer_id),
    conn: sqlite3.Connection = Depends(get_db),
) -> ChatResponse:
    """Run one agent turn for the authenticated customer."""
    if not repository.customer_owns_order(conn, customer_id, req.order_id):
        raise HTTPException(
            status_code=404,
            detail=f"Order '{req.order_id}' not found on this account.",
        )

    media_parts = media.load_for_chat(conn, customer_id, req.media_ids)
    media_count = len(media_parts)

    try:
        log = agent.run_turn(
            conn,
            customer_id=customer_id,
            order_id=req.order_id,
            message=req.message,
            conversation_id=req.conversation_id,
            media=media_parts,
            media_count=media_count,
            media_ids=req.media_ids,
        )
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return ChatResponse(
        turn_id=log.turn_id,
        conversation_id=log.conversation_id,
        decision=log.decision,
        final_response=log.final_response,
        timestamp=log.timestamp,
    )


# ---- Admin ----


@app.post("/admin/login", response_model=AdminLoginResponse, tags=["admin"])
def admin_login(
    req: AdminLoginRequest,
    _rl: None = Depends(login_rate_limit),
) -> AdminLoginResponse:
    if not auth.verify_admin_credentials(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return AdminLoginResponse(
        token=auth.create_token(req.username, role="admin"),
        username=req.username,
    )


@app.get("/admin/logs", response_model=list[AdminLogEntry], tags=["admin"])
def admin_logs(
    decision: str | None = Query(default=None),
    flagged: bool | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    _admin: str = Depends(auth.get_current_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[AdminLogEntry]:
    rows = repository.list_logs(conn, decision=decision, flagged=flagged, limit=limit)
    return [AdminLogEntry(**row) for row in rows]


@app.get("/admin/orders", response_model=list[AdminOrder], tags=["admin"])
def admin_orders(
    _admin: str = Depends(auth.get_current_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[AdminOrder]:
    return [AdminOrder(**row) for row in repository.list_orders(conn)]


@app.post(
    "/admin/orders/{order_id}/override",
    response_model=AdminOrder,
    tags=["admin"],
)
def admin_override(
    order_id: str,
    req: OverrideRequest,
    admin_user: str = Depends(auth.get_current_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> AdminOrder:
    updated = repository.apply_admin_override(
        conn, order_id, req.decision, req.reason, admin_user
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    return AdminOrder(**updated)


@app.post(
    "/admin/orders/{order_id}/unlock",
    response_model=UnlockResponse,
    tags=["admin"],
)
def admin_unlock(
    order_id: str,
    admin_user: str = Depends(auth.get_current_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> UnlockResponse:
    updated = repository.unlock_order(conn, order_id, admin_user)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found.")
    return UnlockResponse(order_id=order_id, admin_locked=bool(updated["admin_locked"]))


@app.get("/admin/media/{media_id}", tags=["admin"])
def admin_get_media(
    media_id: str,
    _admin: str = Depends(auth.get_current_admin),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Retrieve any customer-uploaded media by ID (admin auth required)."""
    row = conn.execute(
        "SELECT mime_type, data FROM media WHERE media_id = ?", (media_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Media not found.")
    return Response(content=bytes(row["data"]), media_type=row["mime_type"])
