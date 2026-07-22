# -*- coding: utf-8 -*-
"""Browser cookie persistence for Supabase auth (survives full page reloads)."""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

COOKIE_NAME = "oc_auth"
COOKIE_MAX_AGE_DAYS = 30
COOKIE_COMPONENT_KEY = "oc_auth_cm"

# One CookieManager per Streamlit worker process — never store in session_state
# (object may not round-trip) and never instantiate twice (duplicate widget key).
_COOKIE_MANAGER: Any = None


def _cookie_secure() -> bool:
    """Secure flag — off for local http dev, on for Cloud HTTPS."""
    env = (os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT") or "").lower()
    if env in ("development", "local"):
        return False
    return True


def get_cookie_manager():
    """Return the singleton CookieManager (mounts the component once per process)."""
    global _COOKIE_MANAGER
    if _COOKIE_MANAGER is not None:
        return _COOKIE_MANAGER
    import extra_streamlit_components as stx

    _COOKIE_MANAGER = stx.CookieManager(key=COOKIE_COMPONENT_KEY)
    return _COOKIE_MANAGER


def _encode(tokens: dict[str, str]) -> str:
    payload = json.dumps(tokens, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode(raw: str) -> dict[str, str] | None:
    try:
        data = json.loads(base64.urlsafe_b64decode(raw.encode("ascii")))
        if not isinstance(data, dict):
            return None
        return {str(k): str(v) for k, v in data.items() if v}
    except Exception:
        return None


def set_auth_cookie(access_token: str, refresh_token: str) -> None:
    """Persist tokens in a browser cookie (30 days, SameSite=Lax)."""
    if not access_token or not refresh_token:
        return
    manager = get_cookie_manager()
    expires = datetime.now(timezone.utc) + timedelta(days=COOKIE_MAX_AGE_DAYS)
    manager.set(
        COOKIE_NAME,
        _encode({"at": access_token, "rt": refresh_token}),
        key="oc_auth_set",
        expires_at=expires,
        max_age=COOKIE_MAX_AGE_DAYS * 86400,
        path="/",
        secure=_cookie_secure(),
        same_site="Lax",
    )


def clear_auth_cookie() -> None:
    manager = get_cookie_manager()
    try:
        manager.delete(COOKIE_NAME, key="oc_auth_del")
    except Exception:
        pass


def read_auth_cookie() -> dict[str, str] | None:
    """
    Read stored tokens from cookie.

    Returns:
        None — cookie component still loading (caller should wait/rerun)
        {} — no auth cookie
        dict with at/rt — stored tokens
    """
    manager = get_cookie_manager()
    # Use cookies from the single getAll mount in CookieManager.__init__.
    # manager.get_all() registers a second widget and can cause duplicate keys.
    cookies = manager.cookies
    if cookies is None:
        return None
    raw = cookies.get(COOKIE_NAME)
    if not raw:
        return {}
    parsed = _decode(str(raw))
    return parsed if parsed else {}
