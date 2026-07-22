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

# CookieManager must call getAll once per *script run* (Streamlit widget contract).
# Process-level reuse without remounting froze stale cookies and skipped the
# loading frame — then set() on restore painted home twice.
# ScriptRunContext object identity is reused across runs, so we reset the
# process cache explicitly at the start of each script via begin_script_run().
_COOKIE_MANAGER: Any = None


def begin_script_run() -> None:
    """Call once at the top of each Streamlit script run before reading cookies."""
    global _COOKIE_MANAGER
    _COOKIE_MANAGER = None


def reset_cookie_manager_for_tests() -> None:
    """Test helper — clear process-level CookieManager cache."""
    begin_script_run()


def _cookie_secure() -> bool:
    """Secure flag — off for local http dev, on for Cloud HTTPS."""
    env = (os.environ.get("STREAMLIT_RUNTIME_ENVIRONMENT") or "").lower()
    if env in ("development", "local"):
        return False
    return True


def get_cookie_manager():
    """
    Mount CookieManager getAll once per script run (stable key).

    Remounting each run is required so the component can return real browser
    cookies after the default placeholder frame. Call begin_script_run() at
    the start of init_state so the process cache does not span runs.
    """
    global _COOKIE_MANAGER
    import extra_streamlit_components as stx

    if _COOKIE_MANAGER is not None:
        return _COOKIE_MANAGER

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


def _cookie_js_snippet(payload: str, *, delete: bool = False) -> str:
    """document.cookie write — no CookieManager.set() → no extra Streamlit rerun."""
    secure = "Secure; " if _cookie_secure() else ""
    if delete:
        return (
            "<script>(function(){try{"
            f'document.cookie="{COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax; {secure}";'
            "}catch(e){}})();</script>"
        )
    max_age = COOKIE_MAX_AGE_DAYS * 86400
    # payload is urlsafe base64 — safe inside a double-quoted JS string
    return (
        "<script>(function(){try{"
        f'document.cookie="{COOKIE_NAME}={payload}; path=/; max-age={max_age}; '
        f'SameSite=Lax; {secure}";'
        "}catch(e){}})();</script>"
    )


def _paint_cookie_js(snippet: str) -> None:
    try:
        import streamlit as st

        try:
            st.html(snippet, unsafe_allow_javascript=True)
        except TypeError:
            st.html(snippet)
    except Exception:
        pass


def set_auth_cookie(
    access_token: str,
    refresh_token: str,
    *,
    quiet: bool = False,
) -> None:
    """
    Persist tokens in a browser cookie (30 days, SameSite=Lax).

    quiet=True — write via document.cookie only (reload/restore path). Avoids
    CookieManager.set() which mounts a second component and forces an extra
    full script rerun (double home flash).
    """
    if not access_token or not refresh_token:
        return
    payload = _encode({"at": access_token, "rt": refresh_token})
    manager = get_cookie_manager()
    # Keep in-memory mirror in sync for this run
    try:
        if isinstance(manager.cookies, dict):
            manager.cookies[COOKIE_NAME] = payload
    except Exception:
        pass

    if quiet:
        _paint_cookie_js(_cookie_js_snippet(payload))
        return

    expires = datetime.now(timezone.utc) + timedelta(days=COOKIE_MAX_AGE_DAYS)
    manager.set(
        COOKIE_NAME,
        payload,
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
        if isinstance(manager.cookies, dict):
            manager.cookies.pop(COOKIE_NAME, None)
    except Exception:
        pass
    try:
        manager.delete(COOKIE_NAME, key="oc_auth_del")
    except Exception:
        pass
    # Also clear via JS in case delete component is slow/ignored
    _paint_cookie_js(_cookie_js_snippet("", delete=True))


def read_auth_cookie() -> dict[str, str] | None:
    """
    Read stored tokens from cookie.

    Returns:
        None — cookie component still loading (caller should wait/stop)
        {} — no auth cookie
        dict with at/rt — stored tokens
    """
    import streamlit as st

    manager = get_cookie_manager()
    cookies = manager.cookies

    # Library default is {} while the iframe loads — indistinguishable from
    # "no cookies". Wait one script frame on a fresh session so getAll can
    # return the real browser jar before we decide auth.
    if cookies is None:
        return None
    if not st.session_state.get("_oc_cookie_component_ready"):
        st.session_state["_oc_cookie_component_ready"] = True
        # First pass after mount: always settle once (component will also
        # rerun on its own when the iframe responds).
        return None

    raw = cookies.get(COOKIE_NAME) if isinstance(cookies, dict) else None
    if not raw:
        return {}
    parsed = _decode(str(raw))
    return parsed if parsed else {}
