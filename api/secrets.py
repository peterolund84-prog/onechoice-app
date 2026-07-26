# -*- coding: utf-8 -*-
"""Env + optional .streamlit/secrets.toml for the HTML/API stack."""

from __future__ import annotations

import os
from pathlib import Path

_ALIASES: dict[str, tuple[str, ...]] = {
    "SUPABASE_URL": ("supabase_url", "url"),
    "SUPABASE_KEY": (
        "SUPABASE_ANON_KEY",
        "supabase_key",
        "supabase_anon_key",
        "anon_key",
        "key",
    ),
    "GROK_API_KEY": ("XAI_API_KEY", "grok_api_key"),
    "TMDB_API_KEY": ("tmdb_api_key",),
}


def _load_toml_secrets() -> dict[str, str]:
    path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore

        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    for k, v in raw.items():
        if isinstance(v, str):
            out[str(k)] = v
        elif isinstance(v, dict):
            section = str(k).lower()
            for kk, vv in v.items():
                if not isinstance(vv, str):
                    continue
                key = str(kk)
                out[key] = vv
                # Nested [supabase] url/key → canonical names
                if section in ("supabase", "api", "secrets"):
                    low = key.lower()
                    if low in ("url", "supabase_url"):
                        out.setdefault("SUPABASE_URL", vv)
                    elif low in ("key", "anon_key", "supabase_key", "supabase_anon_key"):
                        out.setdefault("SUPABASE_KEY", vv)
                    elif low in ("tmdb_api_key",):
                        out.setdefault("TMDB_API_KEY", vv)
                    elif low in ("grok_api_key", "xai_api_key"):
                        out.setdefault("GROK_API_KEY", vv)
    return out


_TOML = _load_toml_secrets()


def get_secret(name: str, default: str = "") -> str:
    env = os.environ.get(name, "").strip()
    if env:
        return env
    for alt in _ALIASES.get(name, ()):
        env_alt = os.environ.get(alt, "").strip()
        if env_alt:
            return env_alt
    if name in _TOML and _TOML[name]:
        return str(_TOML[name]).strip()
    for alt in _ALIASES.get(name, ()):
        if alt in _TOML and _TOML[alt]:
            return str(_TOML[alt]).strip()
    return str(default).strip()


def grok_api_key() -> str:
    return get_secret("GROK_API_KEY") or get_secret("XAI_API_KEY")


def tmdb_api_key() -> str:
    return get_secret("TMDB_API_KEY")


def supabase_configured() -> bool:
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY")
    if not url or not key:
        return False
    if url.startswith("din_") or key.startswith("din_"):
        return False
    if "YOUR_" in url.upper() or "YOUR_" in key.upper():
        return False
    return url.startswith("http")
