# -*- coding: utf-8 -*-
"""
Central LLM model configuration for OneChoice.

WHY THIS FILE EXISTS: xAI retired the grok-2 family while three call sites
still hardcoded "grok-2-latest" — every text LLM call failed silently and the
app ran on local fallback packs in production. Model names now live HERE only.

Override without a deploy via Streamlit secrets or env:
  TEXT_MODEL = "grok-4.5"
"""

from __future__ import annotations

import os

# Default aligned with fridge_domain.VISION_MODELS (grok-4.x family).
_DEFAULT_TEXT_MODEL = "grok-4.5"

XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"


def text_model() -> str:
    """Resolve the text model: secrets → env → default."""
    try:
        import streamlit as st  # noqa: PLC0415

        val = str(st.secrets.get("TEXT_MODEL", "") or "").strip()
        if val:
            return val
    except Exception:
        pass
    return os.environ.get("ONECHOICE_TEXT_MODEL", "").strip() or _DEFAULT_TEXT_MODEL


def llm_health_check(api_key: str, *, timeout: int = 15) -> tuple[bool, str]:
    """
    One tiny call at boot. Returns (ok, detail). Never raises.
    Callers must LOG LOUDLY and surface a dev banner when not ok —
    silent model failure must never happen again.
    """
    key = str(api_key or "").strip()
    if len(key) < 8:
        return False, "no_api_key"
    try:
        import requests  # noqa: PLC0415

        resp = requests.post(
            XAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": text_model(),
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            return True, text_model()
        return False, f"http_{resp.status_code}:{resp.text[:120]}"
    except Exception as exc:  # network etc.
        return False, f"error:{exc}"
