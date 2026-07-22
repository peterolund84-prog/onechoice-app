# -*- coding: utf-8 -*-
"""
Supabase client + auth helpers for OneChoice.

Uses Streamlit secrets or environment variables:
  SUPABASE_URL / SUPABASE_KEY  (or SUPABASE_ANON_KEY)
"""

from __future__ import annotations

import os
from typing import Any

from supabase import Client, create_client

# Process-wide authed clients keyed by token pair (avoid set_session on every call).
_AUTHED: dict[tuple[str, str], Client] = {}
_BASE: Client | None = None


def _secret(name: str, default: str = "") -> str:
    env = os.environ.get(name, "")
    if env:
        return env
    try:
        import streamlit as st

        raw = st.secrets.get(name, None)
        if raw is not None and not isinstance(raw, dict):
            return str(raw)
        # Nested TOML: [supabase] url = "..." or [api] SUPABASE_URL = "..."
        for section in st.secrets.keys():  # type: ignore[attr-defined]
            try:
                block = st.secrets[section]
            except Exception:
                continue
            if not isinstance(block, dict):
                continue
            if name in block and block[name] is not None:
                val = block[name]
                if not isinstance(val, dict):
                    return str(val)
            # Common nested aliases
            aliases = {
                "SUPABASE_URL": ("url", "supabase_url"),
                "SUPABASE_KEY": ("key", "anon_key", "supabase_key", "SUPABASE_ANON_KEY"),
            }
            for alias in aliases.get(name, ()):
                if alias in block and block[alias] is not None:
                    val = block[alias]
                    if not isinstance(val, dict):
                        return str(val)
    except Exception:
        pass
    return default


def get_creds() -> tuple[str, str]:
    url = _secret("SUPABASE_URL") or _secret("supabase_url")
    key = (
        _secret("SUPABASE_KEY")
        or _secret("SUPABASE_ANON_KEY")
        or _secret("supabase_key")
    )
    return url.strip(), key.strip()


def is_configured() -> bool:
    url, key = get_creds()
    if not url or not key:
        return False
    if url.startswith("din_") or key.startswith("din_"):
        return False
    if "YOUR_" in url.upper() or "YOUR_" in key.upper():
        return False
    return url.startswith("http")


def get_client() -> Client:
    """Anon/base client — cached per process (creds rarely change)."""
    global _BASE
    if not is_configured():
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY "
            "in .streamlit/secrets.toml"
        )
    if _BASE is not None:
        return _BASE
    url, key = get_creds()

    def _create() -> Client:
        return create_client(url, key)

    try:
        import streamlit as st

        @st.cache_resource(show_spinner=False)
        def _cached(u: str, k: str) -> Client:
            return create_client(u, k)

        _BASE = _cached(url, key)
    except Exception:
        _BASE = _create()
    return _BASE


def sign_up(email: str, password: str, *, language: str = "sv") -> dict[str, Any]:
    client = get_client()
    res = client.auth.sign_up(
        {
            "email": email,
            "password": password,
            "options": {"data": {"language": language}},
        }
    )
    user = res.user
    session = res.session
    if user is None:
        raise RuntimeError("Signup failed — check email confirmation settings in Supabase.")
    return {
        "user_id": user.id,
        "email": user.email,
        "access_token": session.access_token if session else None,
        "refresh_token": session.refresh_token if session else None,
    }


def sign_in(email: str, password: str) -> dict[str, Any]:
    client = get_client()
    res = client.auth.sign_in_with_password({"email": email, "password": password})
    user = res.user
    session = res.session
    if user is None or session is None:
        raise RuntimeError("Login failed — wrong email or password.")
    return {
        "user_id": user.id,
        "email": user.email,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


def restore_session(access_token: str, refresh_token: str) -> Client:
    """Return an authed client; reuse when the token pair is unchanged."""
    key = (str(access_token or ""), str(refresh_token or ""))
    cached = _AUTHED.get(key)
    if cached is not None:
        return cached

    def _build(at: str, rt: str) -> Client:
        client = create_client(*get_creds())
        client.auth.set_session(at, rt)
        return client

    try:
        import streamlit as st

        @st.cache_resource(show_spinner=False)
        def _cached_authed(at: str, rt: str) -> Client:
            return _build(at, rt)

        client = _cached_authed(key[0], key[1])
    except Exception:
        client = _build(key[0], key[1])
    _AUTHED[key] = client
    return client


def refresh_session(refresh_token: str) -> dict[str, Any]:
    """Exchange refresh token for a new session."""
    client = get_client()
    res = client.auth.refresh_session(refresh_token)
    user = res.user
    session = res.session
    if user is None or session is None:
        raise RuntimeError("Session refresh failed — log in again.")
    # Drop stale authed clients — tokens rotated
    _AUTHED.clear()
    return {
        "user_id": user.id,
        "email": user.email,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


def sign_out(access_token: str | None = None, refresh_token: str | None = None) -> None:
    try:
        client = get_client()
        if access_token and refresh_token:
            client.auth.set_session(access_token, refresh_token)
        client.auth.sign_out()
    except Exception:
        pass
    _AUTHED.clear()


def authed_client(access_token: str, refresh_token: str) -> Client:
    return restore_session(access_token, refresh_token)


def admin_delete_user(user_id: str) -> bool:
    """
    Delete auth user via service role (optional secret SUPABASE_SERVICE_ROLE_KEY).
    Prefer RPC delete_own_account() when available — this is a fallback only.
    Never ship service_role to the browser; Streamlit secrets stay server-side.
    """
    url, _anon = get_creds()
    service = (
        _secret("SUPABASE_SERVICE_ROLE_KEY")
        or _secret("SUPABASE_SERVICE_KEY")
        or ""
    ).strip()
    if not url or not service or service.startswith(("din_", "YOUR_")):
        return False
    try:
        admin = create_client(url, service)
        admin.auth.admin.delete_user(user_id)
        return True
    except Exception:
        return False
