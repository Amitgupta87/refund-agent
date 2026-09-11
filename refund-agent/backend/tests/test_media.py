"""Media upload validation: size, type, scoped retrieval."""

from __future__ import annotations

import io

import pytest
from fastapi import HTTPException, UploadFile

from app import media


def _upload(name: str, content_type: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data), headers={"content-type": content_type})  # type: ignore[arg-type]


def _customer_id(conn) -> str:
    return conn.execute("SELECT customer_id FROM customers LIMIT 1").fetchone()["customer_id"]


@pytest.mark.anyio("asyncio")
async def test_unsupported_mime_rejected(conn):
    cid = _customer_id(conn)
    with pytest.raises(HTTPException) as exc:
        await media.store_upload(conn, cid, _upload("a.bmp", "image/bmp", b"\0\0\0"))
    assert exc.value.status_code == 415


@pytest.mark.anyio("asyncio")
async def test_oversized_image_rejected(conn):
    cid = _customer_id(conn)
    big = b"\xff" * (2 * 1024 * 1024 + 1)  # 2 MB + 1
    with pytest.raises(HTTPException) as exc:
        await media.store_upload(conn, cid, _upload("a.jpg", "image/jpeg", big))
    assert exc.value.status_code == 413


@pytest.mark.anyio("asyncio")
async def test_valid_image_stored_and_loadable(conn):
    cid = _customer_id(conn)
    meta = await media.store_upload(
        conn, cid, _upload("a.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 100),
    )
    mid = meta["media_id"]
    parts = media.load_for_chat(conn, cid, [mid])
    assert len(parts) == 1
    assert parts[0].kind == "image"
    assert parts[0].mime_type == "image/png"


@pytest.mark.anyio("asyncio")
async def test_media_scoped_to_owner(conn):
    """Customer A cannot reference customer B's media."""
    cid_a = conn.execute(
        "SELECT customer_id FROM customers WHERE username='alice'"
    ).fetchone()["customer_id"]
    cid_b = conn.execute(
        "SELECT customer_id FROM customers WHERE username='bob'"
    ).fetchone()["customer_id"]

    meta = await media.store_upload(
        conn, cid_a, _upload("a.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"x" * 50),
    )
    with pytest.raises(HTTPException) as exc:
        media.load_for_chat(conn, cid_b, [meta["media_id"]])
    assert exc.value.status_code == 404


def test_count_for_chat_zero(conn):
    cid = _customer_id(conn)
    assert media.count_for_chat(conn, cid, []) == 0
    assert media.count_for_chat(conn, cid, ["med_nonexistent"]) == 0
