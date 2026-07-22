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
    year: Any = None,
) -> str:
    """
    Confident statement that frames the APP as the decider.
    This is the hook that makes recipients ask what OneChoice is.
    """
    sug = (suggestion or "").strip() or (
        "ett beslut" if language == "sv" else "a decision"
    )
    d = (domain or "").strip()
    em = domain_emoji(d)
    year_s = str(year).strip() if year is not None and str(year).strip() else ""

    if language == "en":
        if d == "food":
            return f"{em} OneChoice decided: {sug} tonight."
        if d == "movie" and year_s:
            return f"{em} OneChoice decided: {sug} ({year_s})."
        if d == "workout":
            return f"{em} Today's workout according to OneChoice: {sug}."
        return f"{em} OneChoice decided: {sug}."

    # Swedish (default) — same pattern across domains
    if d == "food":
        return f"{em} OneChoice har bestämt: {sug} ikväll."
    if d == "movie" and year_s:
        return f"{em} OneChoice har bestämt: {sug} ({year_s})."
    if d == "workout":
        return f"{em} OneChoice har bestämt: {sug}."
    return f"{em} OneChoice har bestämt: {sug}."


def format_list_share_text(
    items: list[dict[str, Any]] | None,
    *,
    language: str = "sv",
) -> str:
    """Plain-text shopping list for Messenger/SMS — unchecked only, by aisle.

    Example::

        🛒 Inköpslista (OneChoice)
        FRUKT & GRÖNT
        – gul lök
        – krossade tomater
        KÖTT & FISK
        – tonfisk
    """
    import shopping_items as si

    rows = [
        r
        for r in (items or [])
        if isinstance(r, dict) and not bool(r.get("checked"))
    ]
    header = (
        "🛒 Inköpslista (OneChoice)"
        if language != "en"
        else "🛒 Shopping list (OneChoice)"
    )
    if not rows:
        empty = "Listan är tom." if language != "en" else "The list is empty."
        return f"{header}\n{empty}"

    grouped = si.group_items(rows)
    # group_items may still include checked depending on version — keep filter
    lines: list[str] = [header]
    for cat in si.CATEGORIES:
        cat_rows = [
            r
            for r in (grouped.get(cat) or [])
            if not bool(r.get("checked"))
        ]
        if not cat_rows:
            continue
        lines.append(str(cat).upper())
        for r in cat_rows:
            name = str(r.get("name") or "").strip()
            if name:
                lines.append(f"– {name}")
    # Any leftover categories not in CATEGORIES (shouldn't happen after group_items)
    for cat, cat_rows in grouped.items():
        if cat in si.CATEGORIES:
            continue
        open_rows = [r for r in cat_rows if not bool(r.get("checked"))]
        if not open_rows:
            continue
        lines.append(str(cat).upper())
        for r in open_rows:
            name = str(r.get("name") or "").strip()
            if name:
                lines.append(f"– {name}")
    return "\n".join(lines)


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
            "movie_tmdb_year": ctx.get("movie_tmdb_year"),
            "movie_poster_url": ctx.get("movie_poster_url"),
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
    # Always produce origin/?share=… (never origin/share=…)
    if "://" in base:
        return f"{base}/{path}"
    return f"{base}{path}"
