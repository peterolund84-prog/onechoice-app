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

# Prefer fast text models for everyday decide latency; quality models as fallback.
_DEFAULT_TEXT_MODEL = "grok-4-fast"

# Auto-discovery candidates, tried in order. Fast models first.
CANDIDATE_TEXT_MODELS: tuple[str, ...] = (
    "grok-4-fast",
    "grok-3-mini",
    "grok-4.5",
    "grok-4",
    "grok-4-latest",
    "grok-3",
    "grok-3-latest",
)

XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"

# Cache: resolved once per process
_RESOLVED: dict[str, str] = {}
DIAGNOSTICS: dict[str, str] = {"status": "unresolved", "model": "", "detail": ""}


def _probe(model: str, key: str, *, timeout: int = 3) -> tuple[bool, str]:
    try:
        import requests  # noqa: PLC0415

        resp = requests.post(
            XAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            return True, model
        return False, f"http_{resp.status_code}"
    except Exception as exc:
        return False, f"error:{exc}"


def resolve_text_model(api_key: str, *, max_probes: int = 1) -> str:
    """
    Return a WORKING model name: explicit override first, then ONE probe
    (3s timeout) of the preferred candidate. Cached process-wide.

    Call lazily on the first real LLM use — never block first paint at boot.
    """
    key = str(api_key or "").strip()
    override = _explicit_override()
    if override:
        DIAGNOSTICS.update(status="override", model=override, detail="from secrets/env")
        return override
    if "model" in _RESOLVED:
        return _RESOLVED["model"]
    if len(key) < 8:
        DIAGNOSTICS.update(status="no_key", model="", detail="GROK_API_KEY missing/placeholder")
        return _DEFAULT_TEXT_MODEL

    def _resolve(k: str) -> str:
        failures: list[str] = []
        for cand in CANDIDATE_TEXT_MODELS[: max(1, int(max_probes))]:
            ok, detail = _probe(cand, k, timeout=3)
            if ok:
                _RESOLVED["model"] = cand
                DIAGNOSTICS.update(status="ok", model=cand, detail="probed")
                return cand
            failures.append(f"{cand}:{detail}")
        _RESOLVED["model"] = _DEFAULT_TEXT_MODEL
        DIAGNOSTICS.update(
            status="probe_partial",
            model=_DEFAULT_TEXT_MODEL,
            detail="; ".join(failures)[:400],
        )
        return _DEFAULT_TEXT_MODEL

    try:
        import streamlit as st

        @st.cache_resource(show_spinner=False)
        def _cached(k: str) -> str:
            # Mirror into module DIAGNOSTICS/RESOLVED for UI + text_model()
            return _resolve(k)

        model = _cached(key)
        if "model" not in _RESOLVED:
            _RESOLVED["model"] = model
        return model
    except Exception:
        return _resolve(key)


def _explicit_override() -> str:
    try:
        import streamlit as st  # noqa: PLC0415

        val = str(st.secrets.get("TEXT_MODEL", "") or "").strip()
        if val:
            return val
    except Exception:
        pass
    return os.environ.get("ONECHOICE_TEXT_MODEL", "").strip()


def text_model() -> str:
    """Resolve the text model: secrets → env → probed candidate → default.

    Triggers a lazy one-shot probe when an API key is available and nothing
    is cached yet (first real LLM call), instead of blocking boot paint.
    """
    override = _explicit_override()
    if override:
        return override
    if "model" in _RESOLVED:
        return _RESOLVED["model"]
    # Lazy probe — first decide/LLM path pays once; boot stays free.
    try:
        import streamlit as st  # noqa: PLC0415

        key = ""
        try:
            key = str(st.secrets.get("GROK_API_KEY", "") or "").strip()
        except Exception:
            key = ""
        if not key:
            key = os.environ.get("GROK_API_KEY", "").strip()
        if len(key) >= 8:
            return resolve_text_model(key, max_probes=1)
    except Exception:
        pass
    return _DEFAULT_TEXT_MODEL


def llm_health_check(api_key: str, *, timeout: int = 15) -> tuple[bool, str]:
    """
    One tiny call. Returns (ok, detail). Never raises.
    Callers must LOG LOUDLY and surface a dev banner when not ok —
    silent model failure must never happen again.
    """
    key = str(api_key or "").strip()
    if len(key) < 8:
        return False, "no_api_key"
    try:
        import requests  # noqa: PLC0415

        model = text_model()
        resp = requests.post(
            XAI_CHAT_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1,
            },
            timeout=timeout,
        )
        if resp.status_code == 200:
            return True, model
        return False, f"http_{resp.status_code}:{resp.text[:120]}"
    except Exception as exc:  # network etc.
        return False, f"error:{exc}"
