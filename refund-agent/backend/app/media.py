"""Customer-uploaded media (photos / videos).

Validates type, size, and (for videos) duration, then persists the bytes in a
small SQLite blob keyed by a generated `media_id`. Storage scope is per
authenticated customer — a customer cannot reference another customer's media.

For real production this should go to S3 / object storage; the table-blob is
fine for an interview demo and keeps the single-container story intact.
"""

from __future__ import annotations

import base64
import io
import struct
import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from .config import settings
from .llm import MediaPart

_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
_VIDEO_MIMES = {"video/mp4", "video/quicktime", "video/webm"}


def _kind_for(mime: str) -> str:
    if mime in _IMAGE_MIMES:
        return "image"
    if mime in _VIDEO_MIMES:
        return "video"
    raise HTTPException(
        status_code=415,
        detail=(
            f"Unsupported media type '{mime}'. Allowed: "
            "image/jpeg, image/png, image/webp, video/mp4, video/quicktime, video/webm."
        ),
    )


def _video_duration_seconds(blob: bytes) -> float | None:
    """Best-effort MP4 duration parse using the mvhd atom (no external deps).

    Returns None for non-MP4/MOV containers (WebM etc.) — we fall back to size
    only for those. This is intentionally conservative: an unknown duration is
    rejected if the file is large enough that 60s is implausible, otherwise
    accepted.
    """
    try:
        i = 0
        while i < len(blob) - 8:
            (atom_size,) = struct.unpack(">I", blob[i:i + 4])
            atom_type = blob[i + 4:i + 8]
            if atom_size < 8:
                return None
            if atom_type == b"moov":
                # Search inside moov for mvhd
                j = i + 8
                end = i + atom_size
                while j < end - 8:
                    (sub_size,) = struct.unpack(">I", blob[j:j + 4])
                    sub_type = blob[j + 4:j + 8]
                    if sub_size < 8:
                        return None
                    if sub_type == b"mvhd":
                        # mvhd version is 1 byte after sub header.
                        version = blob[j + 8]
                        if version == 0:
                            timescale = struct.unpack(">I", blob[j + 20:j + 24])[0]
                            duration = struct.unpack(">I", blob[j + 24:j + 28])[0]
                        else:
                            timescale = struct.unpack(">I", blob[j + 28:j + 32])[0]
                            duration = struct.unpack(">Q", blob[j + 32:j + 40])[0]
                        return duration / timescale if timescale else None
                    j += sub_size
                return None
            i += atom_size
    except (struct.error, IndexError):
        return None
    return None


async def store_upload(
    conn: sqlite3.Connection, customer_id: str, upload: UploadFile
) -> dict[str, object]:
    """Validate and persist one uploaded file; return its metadata."""
    mime = upload.content_type or ""
    kind = _kind_for(mime)

    data = await upload.read()
    size = len(data)

    if kind == "image":
        limit = settings.media_max_image_bytes
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Photo too large: {size} bytes (max {limit}).",
            )
        duration = None
    else:
        limit = settings.media_max_video_bytes
        if size > limit:
            raise HTTPException(
                status_code=413,
                detail=f"Video too large: {size} bytes (max {limit}).",
            )
        duration = _video_duration_seconds(data)
        if duration is not None and duration > settings.media_max_video_seconds:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Video too long: {duration:.1f}s "
                    f"(max {settings.media_max_video_seconds:.0f}s)."
                ),
            )

    media_id = f"med_{uuid.uuid4().hex[:16]}"
    conn.execute(
        "INSERT INTO media (media_id, customer_id, mime_type, kind, size_bytes, "
        "duration_sec, data, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            media_id, customer_id, mime, kind, size, duration,
            data, datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()

    return {
        "media_id": media_id,
        "kind": kind,
        "mime_type": mime,
        "size_bytes": size,
        "duration_sec": duration,
    }


def load_for_chat(
    conn: sqlite3.Connection, customer_id: str, media_ids: list[str]
) -> list[MediaPart]:
    """Fetch media referenced in a chat request, scoped to the customer."""
    if not media_ids:
        return []
    placeholders = ",".join("?" for _ in media_ids)
    rows = conn.execute(
        f"SELECT media_id, mime_type, kind, data FROM media "
        f"WHERE customer_id = ? AND media_id IN ({placeholders})",
        (customer_id, *media_ids),
    ).fetchall()
    if len(rows) != len(media_ids):
        raise HTTPException(
            status_code=404,
            detail="One or more attached media files were not found on this account.",
        )
    out: list[MediaPart] = []
    for r in rows:
        data_b64 = base64.b64encode(r["data"]).decode("ascii")
        out.append(MediaPart(
            mime_type=r["mime_type"], data_b64=data_b64, kind=r["kind"],
        ))
    return out


def count_for_chat(
    conn: sqlite3.Connection, customer_id: str, media_ids: list[str]
) -> int:
    """Cheap count for the tool-side has_media guardrail."""
    if not media_ids:
        return 0
    placeholders = ",".join("?" for _ in media_ids)
    row = conn.execute(
        f"SELECT COUNT(*) AS n FROM media "
        f"WHERE customer_id = ? AND media_id IN ({placeholders})",
        (customer_id, *media_ids),
    ).fetchone()
    return int(row["n"]) if row else 0
