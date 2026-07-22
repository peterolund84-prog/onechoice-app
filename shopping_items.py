# -*- coding: utf-8 -*-
"""Persistent user shopping list — merge, categorize, dedupe."""

from __future__ import annotations

import json
import re
from typing import Any

import shopping

# Store layout order (matches shopping.STORE_ORDER + övrigt)
CATEGORIES: tuple[str, ...] = (
    "frukt & grönt",
    "kött & fisk",
    "mejeri",
    "skafferi",
    "fryst",
    "övrigt",
)

# TODO: quantity merging — two decisions needing gul lök should become "2 st", not one row.

_HINT_RE = re.compile(r"\s*[—–-]\s*hoppa över.*$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, strip shopping hints, collapse whitespace."""
    raw = str(name or "").strip()
    raw = _HINT_RE.sub("", raw).strip()
    raw = _WS_RE.sub(" ", raw)
    return raw.lower()


def categorize_item(
    name: str,
    section: str | None = None,
    *,
    grok_api_key: str = "",
) -> str:
    """Route a manual item into a store-layout category."""
    if section and section in CATEGORIES:
        return section
    base = normalize_name(name)
    if not base:
        return "övrigt"
    mapped = shopping._section_for(base)  # noqa: SLF001 — reuse aisle logic
    if mapped in CATEGORIES:
        return mapped
    if grok_api_key:
        try:
            cat = _llm_categorize(base, grok_api_key)
            if cat in CATEGORIES:
                return cat
        except Exception:
            pass
    return "övrigt"


def flatten_to_buy(to_buy: dict[str, Any] | None) -> list[tuple[str, str]]:
    """Expand a decision shopping payload into (name, category) pairs."""
    if not isinstance(to_buy, dict):
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for section, items in to_buy.items():
        cat = section if section in CATEGORIES else categorize_item("", section)
        if not isinstance(items, (list, tuple)):
            if isinstance(items, str):
                items = [items]
            else:
                continue
        for item in items:
            name = normalize_name(str(item))
            if not name or name in seen:
                continue
            seen.add(name)
            out.append((name, cat if cat in CATEGORIES else categorize_item(name)))
    return out


def _newest_first_key(row: dict[str, Any]) -> tuple[str, int]:
    """Sort key for newest-first (use with reverse=True)."""
    return (str(row.get("created_at") or ""), int(row.get("id") or 0))


def _checked_at_key(row: dict[str, Any]) -> tuple[str, int]:
    """Sort key for most-recently-checked first (use with reverse=True)."""
    return (str(row.get("checked_at") or ""), int(row.get("id") or 0))


def group_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group unchecked rows by aisle; newest first within each category.

    Checked items are excluded — they belong in the Klart section via
    ``checked_items``. Empty categories are omitted so headers hide.
    """
    buckets: dict[str, list[dict[str, Any]]] = {c: [] for c in CATEGORIES}
    for row in items:
        if bool(row.get("checked")):
            continue
        cat = str(row.get("category") or "övrigt")
        if cat not in buckets:
            cat = "övrigt"
        buckets[cat].append(row)
    for cat in buckets:
        buckets[cat].sort(key=_newest_first_key, reverse=True)
    return {k: v for k, v in buckets.items() if v}


def checked_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Checked rows for the Klart section — most recently checked first.

    Kept as a module-level helper so Lista can split aisles vs Klart without
    Streamlit Cloud serving a stale shopping_items module mid-redeploy.
    """
    done = [row for row in items if bool(row.get("checked"))]
    done.sort(key=_checked_at_key, reverse=True)
    return done


def _llm_categorize(name: str, api_key: str) -> str | None:
    import urllib.request

    import llm_config

    model = llm_config.text_model()
    prompt = (
        "Klassificera livsmedlet i exakt en butikskategori. "
        f"Vara: {name}\n"
        f"Kategorier: {', '.join(CATEGORIES)}\n"
        'Svara med JSON: {"category": "..."}'
    )
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=12) as resp:
        payload = json.loads(resp.read().decode())
    text = (
        ((payload.get("choices") or [{}])[0].get("message") or {}).get("content")
        or ""
    )
    m = re.search(r"\{[^{}]*\}", text)
    if not m:
        return None
    data = json.loads(m.group())
    cat = str(data.get("category") or "").strip().lower()
    for c in CATEGORIES:
        if c.lower() == cat:
            return c
    return None
