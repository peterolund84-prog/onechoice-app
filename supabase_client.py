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


def _secret(name: str, default: str = "") -> str:
    env = os.environ.get(name, "")
    if env:
        return env
    try:
        import streamlit as st

        return str(st.secrets.get(name, default) or default)
    except Exception:
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
    if not is_configured():
        raise RuntimeError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY "
            "in .streamlit/secrets.toml"
        )
    url, key = get_creds()
    return create_client(url, key)


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
    client = get_client()
    client.auth.set_session(access_token, refresh_token)
    return client


def sign_out(access_token: str | None = None, refresh_token: str | None = None) -> None:
    try:
        client = get_client()
        if access_token and refresh_token:
            client.auth.set_session(access_token, refresh_token)
        client.auth.sign_out()
    except Exception:
        pass


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
