# -*- coding: utf-8 -*-
"""Food meal budget — optional cost constraint + ca-estimate display.

Architecture (same generate-then-verify split as nutrition / TMDB):
  - Profile opt-in: any (default) / billigt / snålt
  - When on, feasibility excludes dishes over the per-portion ceiling
  - Recipe view may show "ca N kr / portion" — never the pre-lock decision card
  - Prices are LLM/estimator ballparks, not store APIs — always labelled "ca"
"""

from __future__ import annotations

import re
from typing import Any

# Profile values
BUDGET_ANY = "any"
BUDGET_BILLIGT = "billigt"
BUDGET_SNALT = "snalt"

BUDGET_ORDER = (BUDGET_ANY, BUDGET_BILLIGT, BUDGET_SNALT)

# Soft ceilings (SEK / portion) — tune later
CEILING_SEK: dict[str, int | None] = {
    BUDGET_ANY: None,
    BUDGET_BILLIGT: 45,
    BUDGET_SNALT: 30,
}

LABELS_SV = {
    BUDGET_ANY: "Spelar ingen roll",
    BUDGET_BILLIGT: "Håll det billigt",
    BUDGET_SNALT: "Snålt",
}
LABELS_EN = {
    BUDGET_ANY: "Doesn't matter",
    BUDGET_BILLIGT: "Keep it cheap",
    BUDGET_SNALT: "Tight budget",
}

# Rough SEK for a typical whole-recipe amount of each ingredient (≈2 portions).
# Ballpark Swedish supermarket — never treat as verified store prices.
_COST_SEK_RECIPE: dict[str, float] = {
    "kycklingfilé": 55,
    "kyckling": 50,
    "nötfärs": 55,
    "köttfärs": 50,
    "färs": 50,
    "lax": 70,
    "torsk": 45,
    "bacon": 25,
    "räkor": 45,
    "ägg": 12,
    "mjölk": 8,
    "grädde": 18,
    "yoghurt": 12,
    "fil": 10,
    "ost": 25,
    "parmesan": 20,
    "smör": 10,
    "olja": 5,
    "pasta": 12,
    "ris": 10,
    "risnudlar": 15,
    "bröd": 15,
    "hamburgerbröd": 18,
    "havregryn": 8,
    "linser": 15,
    "röda linser": 15,
    "bönor": 12,
    "kokosmjölk": 18,
    "krossade tomater": 12,
    "tomat": 15,
    "gul lök": 5,
    "lök": 5,
    "vitlök": 5,
    "morot": 8,
    "broccoli": 15,
    "paprika": 15,
    "paprika (färsk)": 15,
    "spenat": 15,
    "sallad": 15,
    "gurka": 10,
    "avokado": 20,
    "zucchini": 12,
    "champinjon": 15,
    "potatis": 12,
    "banan": 8,
    "äpple": 8,
    "sojasås": 8,
    "tonfisk": 18,
    "skinka": 25,
    "korv": 25,
    "tortilla": 18,
    "müsli": 15,
    "sylt": 12,
}


def normalize_meal_budget(value: Any) -> str:
    """Return any | billigt | snalt."""
    key = str(value or "").strip().lower().replace("å", "a").replace("ä", "a").replace("ö", "o")
    key = re.sub(r"[\s\-]+", "_", key)
    if key in ("", "any", "none", "off", "spelar_ingen_roll", "spelarigenroll", "n_a", "na"):
        return BUDGET_ANY
    if key in (
        "billigt",
        "hall_det_billigt",
        "halldetbilligt",
        "cheap",
        "keep_it_cheap",
        "budget",
        "medium",
    ):
        return BUDGET_BILLIGT
    if key in ("snalt", "tight", "frugal", "thrifty", "low"):
        return BUDGET_SNALT
    if key in BUDGET_ORDER:
        return key
    return BUDGET_ANY


def budget_label(level: Any, language: str = "sv") -> str:
    key = normalize_meal_budget(level)
    table = LABELS_SV if language == "sv" else LABELS_EN
    return table.get(key, table[BUDGET_ANY])


def ceiling_sek(level: Any) -> int | None:
    """Per-portion SEK ceiling, or None when budget is off."""
    return CEILING_SEK.get(normalize_meal_budget(level))


def budget_active(level: Any) -> bool:
    return ceiling_sek(level) is not None


def round_cost_sek(value: Any) -> int | None:
    """Round to nearest 5 SEK — false precision invites scrutiny."""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    if n < 0:
        return None
    return int(round(n / 5.0) * 5)


def format_cost_label(sek: Any, *, language: str = "sv") -> str:
    """Always 'ca' — never claim exact store price."""
    n = round_cost_sek(sek)
    if n is None:
        return ""
    if language == "sv":
        return f"ca {n} kr"
    return f"approx. {n} SEK"


def _match_cost_key(name: str) -> str | None:
    low = str(name or "").strip().lower()
    if not low:
        return None
    if low in _COST_SEK_RECIPE:
        return low
    for key in sorted(_COST_SEK_RECIPE.keys(), key=len, reverse=True):
        if key in low:
            return key
    return None


def estimate_cost_per_portion(
    ingredients: list[Any] | None,
    *,
    servings: int = 2,
) -> int:
    """Ballpark SEK/portion from ingredient names — estimate only."""
    portions = max(1, int(servings or 2))
    total = 0.0
    matched = 0
    for raw in ingredients or []:
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("item") or "")
        else:
            name = str(raw)
        key = _match_cost_key(name)
        if not key:
            continue
        total += float(_COST_SEK_RECIPE[key])
        matched += 1
    if matched <= 0:
        # Modest default dinner when nothing matched
        per = 40.0
    else:
        per = total / portions
    rounded = round_cost_sek(per)
    return int(rounded if rounded is not None else 40)


def read_cost_per_portion(
    source: dict[str, Any] | None,
) -> int | None:
    """Read cost_per_portion_sek from recipe or candidate meta."""
    if not isinstance(source, dict):
        return None
    for key in ("cost_per_portion_sek", "cost_sek", "cost_per_portion"):
        if key in source:
            return round_cost_sek(source.get(key))
    nested = source.get("recipe") if isinstance(source.get("recipe"), dict) else None
    if nested:
        return read_cost_per_portion(nested)
    return None


def cost_from_candidate(candidate: dict[str, Any]) -> int | None:
    """Prefer meta.cost_per_portion_sek, else estimate from meta.ingredients."""
    meta = candidate.get("meta") if isinstance(candidate.get("meta"), dict) else {}
    direct = read_cost_per_portion(meta)
    if direct is not None:
        return direct
    recipe = meta.get("recipe") if isinstance(meta.get("recipe"), dict) else None
    if recipe:
        nested = read_cost_per_portion(recipe)
        if nested is not None:
            return nested
    ings = list(meta.get("ingredients") or [])
    if recipe and not ings:
        ings = list(recipe.get("ingredients") or recipe.get("ingredient_lines") or [])
    if not ings:
        return None
    servings = 2
    try:
        if recipe and recipe.get("portioner"):
            servings = int(recipe.get("portioner") or 2)
    except (TypeError, ValueError):
        servings = 2
    return estimate_cost_per_portion(ings, servings=servings)


def ensure_recipe_cost(
    recipe: dict[str, Any] | None,
    *,
    meta: dict[str, Any] | None = None,
    allow_estimate: bool = True,
) -> dict[str, Any]:
    """Attach cost_per_portion_sek (rounded) — single field for constraint + display."""
    out = dict(recipe or {})
    meta = meta if isinstance(meta, dict) else {}
    cost = read_cost_per_portion(out)
    if cost is None:
        cost = read_cost_per_portion(meta)
    if cost is None and allow_estimate:
        ings = list(out.get("ingredients") or out.get("ingredient_lines") or [])
        if not ings:
            ings = list(meta.get("ingredients") or [])
        try:
            servings = int(out.get("portioner") or out.get("portions") or 2)
        except (TypeError, ValueError):
            servings = 2
        cost = estimate_cost_per_portion(ings, servings=servings)
    if cost is not None:
        cost = round_cost_sek(cost)
        out["cost_per_portion_sek"] = cost
        out["cost_label"] = "ca"
    return out


def cost_stat(
    recipe: dict[str, Any] | None,
    *,
    language: str = "sv",
) -> dict[str, Any] | None:
    """Presentation helper for execute view: {sek, label, unit}."""
    if not isinstance(recipe, dict):
        return None
    healed = ensure_recipe_cost(recipe, allow_estimate=True)
    sek = read_cost_per_portion(healed)
    if sek is None:
        return None
    return {
        "sek": sek,
        "label": format_cost_label(sek, language=language),
        "unit": "portion",
        "approx": True,
    }
