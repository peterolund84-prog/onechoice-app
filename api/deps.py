# -*- coding: utf-8 -*-
"""Shared FastAPI helpers (guest SQLite path)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Header, HTTPException, Query


def resolve_user_id(
    user_id: str | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    """Prefer explicit body/query user_id, then header, else mint guest id."""
    uid = (user_id or x_user_id or "").strip()
    return uid or f"guest-{uuid.uuid4().hex[:12]}"


def require_user_id(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> str:
    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required (query or X-User-Id)")
    return uid


def boot_db_guest() -> None:
    """Init SQLite and clear cloud auth so guest writes stay local."""
    import db

    try:
        db.clear_auth()
    except Exception:
        pass
    try:
        db.init_db()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"db init failed: {exc}") from exc


def ensure_guest_user(user_id: str, *, language: str = "sv") -> dict[str, Any]:
    import db

    boot_db_guest()
    return db.ensure_user(user_id, language=language)
