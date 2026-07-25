# -*- coding: utf-8 -*-
"""Env + optional .streamlit/secrets.toml for the HTML/API stack."""

from __future__ import annotations

import os
from pathlib import Path


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
            for kk, vv in v.items():
                if isinstance(vv, str):
                    out[str(kk)] = vv
    return out


_TOML = _load_toml_secrets()


def get_secret(name: str, default: str = "") -> str:
    env = os.environ.get(name, "").strip()
    if env:
        return env
    return str(_TOML.get(name) or default).strip()


def grok_api_key() -> str:
    return get_secret("GROK_API_KEY") or get_secret("XAI_API_KEY")
