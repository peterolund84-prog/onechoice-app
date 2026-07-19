# -*- coding: utf-8 -*-
"""Share copy + public decision payloads — distribution channel for OneChoice."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

# Domain emoji — one visual hook per share
_EMOJI = {
    "food": "🍽",
    "workout": "💪",
    "clothes": "👕",
    "movie": "🎬",
    "weekend": "🌿",
}


def domain_emoji(domain: str) -> str:
    return _EMOJI.get((domain or "").strip(), "✨")


def share_message(
    *,
    domain: str,
    suggestion: str,
    language: str = "sv",
) -> str:
    """
    Confident statement that frames the APP as the decider.
    This is the hook that makes recipients ask what OneChoice is.
    """
    sug = (suggestion or "").strip() or ("ett beslut" if language == "sv" else "a decision")
    d = (domain or "").strip()
    em = domain_emoji(d)
    if language == "en":
        if d == "workout":
            return f"{em} Today's workout according to OneChoice: {sug}."
        if d == "food":
            return f"{em} OneChoice decided: {sug}."
        return f"{em} OneChoice decided: {sug}."
    # Swedish (default)
    if d == "workout":
        return f"{em} Dagens pass enligt OneChoice: {sug}."
    if d == "food":
        return f"{em} OneChoice har bestämt: {sug}."
    return f"{em} OneChoice har bestämt: {sug}."


def public_payload_from_decision(cur: dict[str, Any], *, language: str = "sv") -> dict[str, Any]:
    """Denormalized snapshot safe to show without login."""
    ctx = cur.get("context") if isinstance(cur.get("context"), dict) else {}
    return {
        "decision_id": cur.get("decision_id") or cur.get("id"),
        "domain": cur.get("domain") or "",
        "suggestion": cur.get("suggestion") or "",
        "justification": cur.get("justification") or "",
        "execution_type": cur.get("execution_type"),
        "execution_label": cur.get("execution_label"),
        "execution_url": cur.get("execution_url"),
        "language": language,
        "context": {
            "shopping": ctx.get("shopping"),
            "recipe": ctx.get("recipe"),
            "workout": ctx.get("workout"),
            "execution_detail": ctx.get("execution_detail"),
            "meal_type": ctx.get("meal_type"),
            "occasion": ctx.get("occasion"),
        },
    }


def share_path(*, token: str, decision_id: Any = None) -> str:
    """Relative query path used as the share landing URL."""
    q: dict[str, str] = {"share": str(token), "ref": "share"}
    if decision_id is not None and str(decision_id).strip() != "":
        q["decision_id"] = str(decision_id)
    return "?" + urlencode(q)


def absolute_share_url(base: str, *, token: str, decision_id: Any = None) -> str:
    base = (base or "").rstrip("/")
    path = share_path(token=token, decision_id=decision_id)
    if not base:
        return path
    return f"{base}/{path.lstrip('?')}" if "://" in base else f"{base}{path}"
