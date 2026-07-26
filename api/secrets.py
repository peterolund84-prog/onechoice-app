# -*- coding: utf-8 -*-
"""Env + optional .streamlit/secrets.toml for the HTML/API stack."""

from __future__ import annotations

import os
import re
from pathlib import Path

_ALIASES: dict[str, tuple[str, ...]] = {
    "SUPABASE_URL": ("supabase_url", "SUPABASE_URL"),
    "SUPABASE_KEY": (
        "SUPABASE_ANON_KEY",
        "supabase_key",
        "supabase_anon_key",
        "SUPABASE_KEY",
    ),
    "GROK_API_KEY": ("XAI_API_KEY", "grok_api_key"),
    "TMDB_API_KEY": ("tmdb_api_key", "TMDB_KEY", "tmdb_key"),
}


def secrets_paths() -> list[Path]:
    """Candidate locations for secrets.toml (project + cwd)."""
    root = Path(__file__).resolve().parent.parent
    cwd = Path.cwd()
    paths = [
        root / ".streamlit" / "secrets.toml",
        cwd / ".streamlit" / "secrets.toml",
    ]
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def secrets_file() -> Path | None:
    for p in secrets_paths():
        if p.is_file():
            return p
    return None


def _flatten_toml(raw: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (raw or {}).items():
        if isinstance(v, str):
            out[str(k)] = v
            continue
        if not isinstance(v, dict):
            continue
        section = str(k).lower()
        for kk, vv in v.items():
            if isinstance(vv, dict):
                # One more level: [connections.supabase] style
                for kkk, vvv in vv.items():
                    if isinstance(vvv, str):
                        out[str(kkk)] = vvv
                continue
            if not isinstance(vv, str):
                continue
            key = str(kk)
            out[key] = vv
            low = key.lower()
            if section in ("supabase", "api", "secrets", "connections"):
                if low in ("url", "supabase_url"):
                    out.setdefault("SUPABASE_URL", vv)
                elif low in (
                    "key",
                    "anon_key",
                    "supabase_key",
                    "supabase_anon_key",
                    "supabase_anon_public_key",
                ):
                    out.setdefault("SUPABASE_KEY", vv)
                elif low in ("tmdb_api_key", "tmdb_key"):
                    out.setdefault("TMDB_API_KEY", vv)
                elif low in ("grok_api_key", "xai_api_key"):
                    out.setdefault("GROK_API_KEY", vv)
            elif section == "tmdb":
                if low in ("api_key", "key", "tmdb_api_key", "tmdb_key"):
                    out.setdefault("TMDB_API_KEY", vv)
            elif "supabase" in section:
                if low in ("url", "supabase_url"):
                    out.setdefault("SUPABASE_URL", vv)
                elif low in ("key", "anon_key", "supabase_key", "supabase_anon_key"):
                    out.setdefault("SUPABASE_KEY", vv)
    # Promote common lowercase top-level names
    if "supabase_url" in out and "SUPABASE_URL" not in out:
        out["SUPABASE_URL"] = out["supabase_url"]
    if "supabase_key" in out and "SUPABASE_KEY" not in out:
        out["SUPABASE_KEY"] = out["supabase_key"]
    if "supabase_anon_key" in out and "SUPABASE_KEY" not in out:
        out["SUPABASE_KEY"] = out["supabase_anon_key"]
    if "tmdb_api_key" in out and "TMDB_API_KEY" not in out:
        out["TMDB_API_KEY"] = out["tmdb_api_key"]
    return out


def _parse_toml_text(text: str) -> dict[str, str]:
    text = text.lstrip("\ufeff")  # strip BOM
    try:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore

        raw = tomllib.loads(text)
        return _flatten_toml(raw if isinstance(raw, dict) else {})
    except Exception:
        pass
    # Naive fallback: KEY = "value" lines (helps odd/partial files)
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("["):
            continue
        m = re.match(
            r'^([A-Za-z0-9_]+)\s*=\s*"(.*)"\s*$',
            s,
        ) or re.match(
            r"^([A-Za-z0-9_]+)\s*=\s*'(.*)'\s*$",
            s,
        )
        if m:
            out[m.group(1)] = m.group(2)
    return _flatten_toml(out)


def _load_toml_secrets() -> dict[str, str]:
    path = secrets_file()
    if not path:
        return {}
    try:
        return _parse_toml_text(path.read_text(encoding="utf-8"))
    except Exception:
        try:
            return _parse_toml_text(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {}


_TOML = _load_toml_secrets()


def reload_secrets() -> None:
    """Re-read secrets.toml (e.g. after the file was edited)."""
    global _TOML
    _TOML = _load_toml_secrets()


def _normalize_secret_value(value: str) -> str:
    """Match Streamlit app.py: strip quotes / Bearer so pasted keys still work."""
    k = (value or "").strip()
    for _ in range(2):
        if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'“”‘’":
            k = k[1:-1].strip()
    if k.lower().startswith("bearer "):
        k = k[7:].strip()
    return k


def _toml_secret(name: str) -> str:
    if name in _TOML and str(_TOML[name]).strip():
        return _normalize_secret_value(str(_TOML[name]))
    for alt in _ALIASES.get(name, ()):
        if alt in _TOML and str(_TOML[alt]).strip():
            return _normalize_secret_value(str(_TOML[alt]))
    want = name.lower()
    for k, v in _TOML.items():
        if str(k).lower() == want and str(v).strip():
            return _normalize_secret_value(str(v))
    return ""


def _env_secret(name: str) -> str:
    env = os.environ.get(name, "")
    if str(env).strip():
        return _normalize_secret_value(str(env))
    for alt in _ALIASES.get(name, ()):
        if alt == name:
            continue
        env_alt = os.environ.get(alt, "")
        if str(env_alt).strip():
            return _normalize_secret_value(str(env_alt))
    return ""


def get_secret(name: str, default: str = "") -> str:
    """Read secret: secrets.toml first (like Streamlit), then process env.

    Env used to win and could override a good local secrets.toml with a
    stale Windows user variable — that looked like "Invalid API key" on HTML
    while Streamlit (secrets-first) still worked.
    """
    reload_secrets()
    from_toml = _toml_secret(name)
    if from_toml and not _looks_placeholder(from_toml):
        return from_toml
    from_env = _env_secret(name)
    if from_env and not _looks_placeholder(from_env):
        return from_env
    if from_toml:
        return from_toml
    if from_env:
        return from_env
    return _normalize_secret_value(str(default))


def grok_api_key() -> str:
    reload_secrets()
    return get_secret("GROK_API_KEY") or get_secret("XAI_API_KEY")


def grok_key_diagnostics() -> dict:
    """Safe key diagnostics for Profile — never returns the secret value."""
    reload_secrets()
    toml_g = _toml_secret("GROK_API_KEY") or _toml_secret("XAI_API_KEY")
    env_g = _env_secret("GROK_API_KEY") or _env_secret("XAI_API_KEY")
    chosen = grok_api_key()
    source = "none"
    if chosen:
        if toml_g and chosen == toml_g:
            source = "secrets.toml"
        elif env_g and chosen == env_g:
            source = "env"
        elif toml_g:
            source = "secrets.toml"
        elif env_g:
            source = "env"
    return {
        "source": source,
        "configured": bool(chosen) and not _looks_placeholder(chosen),
        "len": len(chosen),
        "prefix": chosen[:4] if chosen else "",
        "startswith_xai": chosen.lower().startswith("xai-"),
        "toml_present": bool(toml_g),
        "env_present": bool(env_g),
        "env_differs_from_toml": bool(env_g and toml_g and env_g != toml_g),
    }


def tmdb_api_key() -> str:
    reload_secrets()
    return get_secret("TMDB_API_KEY")


def _looks_placeholder(val: str) -> bool:
    v = (val or "").strip()
    if not v:
        return True
    low = v.lower()
    if low.startswith("din_") or "your_" in low or "xxx" in low:
        return True
    if "your_project" in low or "din_riktiga" in low:
        return True
    return False


def supabase_configured() -> bool:
    reload_secrets()
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY") or get_secret("SUPABASE_ANON_KEY")
    if _looks_placeholder(url) or _looks_placeholder(key):
        return False
    return url.startswith("http")


def secrets_status() -> dict:
    """Safe diagnostics for Profil/Auth — never returns secret values."""
    reload_secrets()
    path = secrets_file()
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_KEY") or get_secret("SUPABASE_ANON_KEY")
    tmdb = get_secret("TMDB_API_KEY")
    grok = get_secret("GROK_API_KEY") or get_secret("XAI_API_KEY")
    return {
        "secrets_file": str(path) if path else None,
        "secrets_file_found": bool(path),
        "searched_paths": [str(p) for p in secrets_paths()],
        "supabase_url_set": bool(url) and not _looks_placeholder(url),
        "supabase_key_set": bool(key) and not _looks_placeholder(key),
        "supabase_configured": supabase_configured(),
        "tmdb_configured": bool(tmdb) and not _looks_placeholder(tmdb),
        "grok_configured": bool(grok) and not _looks_placeholder(grok),
        "hint": (
            None
            if path
            else "Ingen .streamlit/secrets.toml hittades i projektmappen. "
            "Streamlit Cloud-nycklar syns inte automatiskt i uvicorn — "
            "kopiera samma nycklar till lokal secrets.toml."
        ),
    }
