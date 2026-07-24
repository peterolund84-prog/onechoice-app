# -*- coding: utf-8 -*-
"""Shared FastAPI helpers — identity, auth tokens, guest users."""

from __future__ import annotations

import os
import re
import uuid
from typing import Any

from fastapi import HTTPException, Request, Response

GUEST_ID_RE = re.compile(r"^guest-[a-zA-Z0-9]+$")

COOKIE_ACCESS = "oc_access"
COOKIE_REFRESH = "oc_refresh"


def is_guest_id(user_id: str | None) -> bool:
    return bool(user_id and GUEST_ID_RE.match(str(user_id).strip()))


def mint_guest_id() -> str:
    return f"guest-{uuid.uuid4().hex[:12]}"


def user_id_from_access_token(access_token: str | None) -> str | None:
    """Verify access JWT via Supabase and return auth user id (sub), or None."""
    at = (access_token or "").strip()
    if not at:
        return None
    try:
        import supabase_client as sb

        if not sb.is_configured():
            return None
        return sb.user_id_from_access_token(at)
    except Exception:
        return None


def tokens_from_request(request: Request) -> tuple[str | None, str | None]:
    """Prefer httpOnly cookies; fall back to legacy headers."""
    at = (request.cookies.get(COOKIE_ACCESS) or "").strip() or None
    rt = (request.cookies.get(COOKIE_REFRESH) or "").strip() or None
    if not at:
        at = (request.headers.get("X-Access-Token") or "").strip() or None
    if not rt:
        rt = (request.headers.get("X-Refresh-Token") or "").strip() or None
    return at, rt


def apply_auth_tokens(
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> bool:
    """Apply Supabase tokens for RLS, or clear to force local SQLite guest path."""
    import db

    at = (access_token or "").strip()
    rt = (refresh_token or "").strip()
    if at and rt:
        try:
            db.set_auth(at, rt)
            return True
        except Exception:
            try:
                db.clear_auth()
            except Exception:
                pass
            return False
    try:
        db.clear_auth()
    except Exception:
        pass
    return False


def resolve_request_user(
    *,
    client_user_id: str | None,
    access_token: str | None,
    jwt_user_id: str | None = None,
    mint_guest: bool = True,
) -> str:
    """
    Derive the acting user id.

    - When an access token is present: identity comes from the verified JWT.
      Client-supplied ids are ignored unless they match; mismatch → 403.
    - Without a token: only ``guest-*`` client ids are accepted (or mint one).
    """
    client = (client_user_id or "").strip() or None
    at = (access_token or "").strip() or None

    if at:
        uid = (jwt_user_id or user_id_from_access_token(at) or "").strip() or None
        if not uid:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        if client and client != uid:
            raise HTTPException(
                status_code=403,
                detail="user_id does not match authenticated token",
            )
        return uid

    if client:
        if not is_guest_id(client):
            raise HTTPException(
                status_code=403,
                detail="non-guest user_id requires authentication",
            )
        return client

    if mint_guest:
        return mint_guest_id()
    raise HTTPException(status_code=400, detail="user_id required")


def resolve_user_from_request(
    request: Request,
    client_user_id: str | None = None,
    *,
    mint_guest: bool = True,
) -> str:
    at = getattr(request.state, "access_token", None)
    jwt_uid = getattr(request.state, "jwt_user_id", None)
    if at is None and jwt_uid is None:
        at, _rt = tokens_from_request(request)
    return resolve_request_user(
        client_user_id=client_user_id,
        access_token=at,
        jwt_user_id=jwt_uid,
        mint_guest=mint_guest,
    )


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
    """Ensure a **guest** user row only. Refuses non-guest ids."""
    import db

    uid = (user_id or "").strip()
    if not is_guest_id(uid):
        raise HTTPException(
            status_code=403,
            detail="ensure_guest_user refuses non-guest ids",
        )
    try:
        db.init_db()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"db init failed: {exc}") from exc
    return db.ensure_user(uid, language=language)


def ensure_authenticated_user(user_id: str, *, language: str = "sv") -> dict[str, Any]:
    """Ensure user row for a JWT-verified (non-guest) id."""
    import db

    uid = (user_id or "").strip()
    if not uid or is_guest_id(uid):
        raise HTTPException(status_code=400, detail="authenticated user id required")
    try:
        db.init_db()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"db init failed: {exc}") from exc
    return db.ensure_user(uid, language=language)


def ensure_request_user(user_id: str, *, language: str = "sv") -> dict[str, Any]:
    """Ensure DB row for either a guest or an already-verified auth user."""
    if is_guest_id(user_id):
        return ensure_guest_user(user_id, language=language)
    return ensure_authenticated_user(user_id, language=language)


def _cookie_secure(request: Request | None = None) -> bool:
    if os.getenv("OC_COOKIE_SECURE", "").strip() in ("1", "true", "yes"):
        return True
    if os.getenv("OC_COOKIE_SECURE", "").strip() in ("0", "false", "no"):
        return False
    if request is not None:
        return request.url.scheme == "https"
    return False


def set_auth_cookies(
    response: Response,
    *,
    access_token: str,
    refresh_token: str,
    request: Request | None = None,
) -> None:
    secure = _cookie_secure(request)
    common = {
        "httponly": True,
        "secure": secure,
        "samesite": "lax",
        "path": "/",
    }
    # Access ~1h, refresh ~30d (Supabase defaults vary; cookies outlive short JWTs).
    response.set_cookie(COOKIE_ACCESS, access_token, max_age=60 * 60, **common)
    response.set_cookie(COOKIE_REFRESH, refresh_token, max_age=60 * 60 * 24 * 30, **common)


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(COOKIE_ACCESS, path="/")
    response.delete_cookie(COOKIE_REFRESH, path="/")


# Legacy aliases used by older imports
def resolve_user_id(
    user_id: str | None = None,
    x_user_id: str | None = None,
) -> str:
    """Deprecated: guest-only resolution without JWT (tests / scripts)."""
    return resolve_request_user(
        client_user_id=user_id or x_user_id,
        access_token=None,
        mint_guest=True,
    )
