# -*- coding: utf-8 -*-
"""Food meal budget — optional cost constraint + ca-estimate display.

Architecture (same generate-then-verify split as nutrition / TMDB):
  - Profile opt-in: any (default) / billigt / snålt
  - When on, feasibility excludes dishes over the per-portion ceiling
  - Recipe view may show "ca N kr / portion" — never the pre-lock decision card
  - Prices are LLM/estimator ballparks, not store APIs — always labelled "ca"

Cost estimates must reflect amounts USED, not full package prices
(2 eggs ≠ a carton; 1 msk oil ≠ a bottle).
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

# Plausible per-portion sanity ceilings — reject whole-package LLM guesses.
# Breakfast ≈ 10–25 kr; weekday dinner ≈ 30–70 kr (per portion ballpark).
SANITY_MAX_PER_PORTION: dict[str, int] = {
    "frukost": 30,
    "kvallsmal": 30,
    "lunch": 50,
    "middag": 70,
}
SANITY_MAX_DEFAULT = 70

# Pantry staples: used amount costs negligibly (salt, pepper, oil, spices).
_PANTRY_NEGLIGIBLE = frozenset(
    {
        "salt",
        "peppar",
        "svartpeppar",
        "olja",
        "olivolja",
        "rapsolja",
        "matolja",
        "vitlök",
        "krydda",
        "kryddor",
        "paprikapulver",
        "curry",
        "currypulver",
        "cumin",
        "spiskummin",
        "oregano",
        "basilika",
        "timjan",
        "kanel",
        "chili",
        "chilipulver",
        "socker",
        "mjöl",
        "vetemjöl",
        "bakpulver",
        "jäst",
        "vatten",
        "buljongtärning",
        "buljong",
    }
)

# SEK per gram (Swedish supermarket ballpark for the edible amount used).
_SEK_PER_G: dict[str, float] = {
    "kycklingfilé": 0.14,
    "kyckling": 0.12,
    "nötfärs": 0.14,
    "köttfärs": 0.12,
    "färs": 0.12,
    "lax": 0.28,
    "torsk": 0.18,
    "bacon": 0.20,
    "räkor": 0.22,
    "skinka": 0.15,
    "korv": 0.10,
    "tonfisk": 0.12,
    "ost": 0.12,
    "parmesan": 0.25,
    "smör": 0.08,
    "pasta": 0.03,
    "ris": 0.025,
    "risnudlar": 0.04,
    "havregryn": 0.02,
    "linser": 0.03,
    "röda linser": 0.03,
    "bönor": 0.02,
    "broccoli": 0.04,
    "morot": 0.02,
    "spenat": 0.05,
    "sallad": 0.03,
    "zucchini": 0.03,
    "champinjon": 0.05,
    "potatis": 0.015,
    "krossade tomater": 0.02,
    "kokosmjölk": 0.03,
    "grädde": 0.04,
    "mjölk": 0.015,
    "yoghurt": 0.02,
    "fil": 0.02,
    "bröd": 0.04,
    "hamburgerbröd": 0.05,
    "tortilla": 0.05,
    "müsli": 0.04,
    "banan": 0.02,
    "äpple": 0.02,
    "avokado": 0.08,
    "sojasås": 0.03,
    "sylt": 0.04,
}

# SEK per piece / countable unit
_SEK_PER_ST: dict[str, float] = {
    "ägg": 2.5,  # share of a carton — not the carton
    "tomat": 4.0,
    "gul lök": 3.0,
    "lök": 3.0,
    "paprika": 8.0,
    "paprika (färsk)": 8.0,
    "gurka": 8.0,
    "avokado": 15.0,
    "banan": 3.0,
    "äpple": 3.0,
    "hamburgerbröd": 4.0,
    "tortilla": 3.0,
    "bröd": 3.0,  # per slice-ish when unit=skivor handled below
}

# SEK per tablespoon (msk) / teaspoon (tsk) when used as the recipe unit
_SEK_PER_MSK: dict[str, float] = {
    "smör": 1.2,
    "yoghurt": 0.8,
    "grädde": 1.0,
    "sojasås": 0.6,
    "sylt": 0.8,
    "honung": 1.0,
}

_SEK_PER_DL: dict[str, float] = {
    "mjölk": 1.5,
    "grädde": 4.0,
    "yoghurt": 2.0,
    "fil": 2.0,
    "ris": 2.5,
    "havregryn": 1.5,
    "linser": 2.0,
    "röda linser": 2.0,
    "müsli": 2.0,
    "sallad": 1.0,
    "kokosmjölk": 3.0,
}

# Typical USED amount (not package) when the list is name-only — whole recipe ≈2 portions.
_DEFAULT_USED: dict[str, tuple[float, str]] = {
    "kycklingfilé": (400, "g"),
    "kyckling": (400, "g"),
    "nötfärs": (400, "g"),
    "köttfärs": (400, "g"),
    "färs": (400, "g"),
    "lax": (250, "g"),
    "torsk": (300, "g"),
    "bacon": (80, "g"),
    "räkor": (200, "g"),
    "ägg": (2, "st"),
    "mjölk": (1, "dl"),
    "grädde": (1, "dl"),
    "yoghurt": (2, "dl"),
    "fil": (2, "dl"),
    "ost": (60, "g"),
    "parmesan": (30, "g"),
    "smör": (1, "msk"),
    "pasta": (200, "g"),
    "ris": (1.5, "dl"),
    "risnudlar": (200, "g"),
    "bröd": (2, "st"),
    "hamburgerbröd": (2, "st"),
    "havregryn": (1, "dl"),
    "linser": (2, "dl"),
    "röda linser": (2, "dl"),
    "bönor": (200, "g"),
    "kokosmjölk": (2, "dl"),
    "krossade tomater": (400, "g"),
    "tomat": (2, "st"),
    "gul lök": (1, "st"),
    "lök": (1, "st"),
    "morot": (2, "st"),
    "broccoli": (200, "g"),
    "paprika": (1, "st"),
    "paprika (färsk)": (1, "st"),
    "spenat": (50, "g"),
    "sallad": (4, "dl"),
    "gurka": (0.5, "st"),
    "avokado": (1, "st"),
    "zucchini": (1, "st"),
    "champinjon": (150, "g"),
    "potatis": (400, "g"),
    "banan": (1, "st"),
    "äpple": (1, "st"),
    "sojasås": (2, "msk"),
    "tonfisk": (1, "burk"),
    "skinka": (80, "g"),
    "korv": (200, "g"),
    "tortilla": (2, "st"),
    "müsli": (1, "dl"),
    "sylt": (1, "msk"),
}

_UNIT_TOKEN = (
    r"dl|g|kg|msk|tsk|krm|st|burk|skiva|skivor|klyfta|klyftor|förp|ask|blad|näve|kopp"
)
_QTY_RE = re.compile(
    rf"(?i)(\d+[.,]?\d*)\s*({_UNIT_TOKEN})\b"
)


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


def sanity_max_per_portion(meal_type: Any = None) -> int:
    """Upper bound for a plausible per-portion estimate (rejects package pricing)."""
    key = str(meal_type or "").strip().lower()
    return int(SANITY_MAX_PER_PORTION.get(key, SANITY_MAX_DEFAULT))


def cost_exceeds_sanity(sek: Any, *, meal_type: Any = None) -> bool:
    n = round_cost_sek(sek)
    if n is None:
        return False
    return n > sanity_max_per_portion(meal_type)


def _match_cost_key(name: str) -> str | None:
    low = str(name or "").strip().lower()
    low = re.sub(r"\s*\([^)]*\)\s*", " ", low).strip()
    low = re.sub(r"\s+", " ", low)
    if not low:
        return None
    keys = sorted(
        set(_SEK_PER_G) | set(_SEK_PER_ST) | set(_SEK_PER_DL) | set(_DEFAULT_USED),
        key=len,
        reverse=True,
    )
    if low in keys:
        return low
    for key in keys:
        if key in low:
            return key
    return None


def _is_pantry(name: str) -> bool:
    low = str(name or "").strip().lower()
    if not low:
        return False
    if low in _PANTRY_NEGLIGIBLE:
        return True
    return any(p in low for p in _PANTRY_NEGLIGIBLE)


def _parse_qty(raw: Any) -> tuple[str, float | None, str]:
    """Return (name, amount, unit) from dict or free-text line."""
    if isinstance(raw, dict):
        name = str(raw.get("name") or raw.get("item") or "").strip()
        amount_s = str(raw.get("amount") or "").strip().replace(",", ".")
        unit = str(raw.get("unit") or "").strip().lower()
        amt: float | None = None
        if amount_s:
            try:
                amt = float(amount_s)
            except ValueError:
                m = _QTY_RE.search(amount_s)
                if m:
                    amt = float(m.group(1).replace(",", "."))
                    unit = unit or m.group(2).lower()
        if amt is None:
            m = _QTY_RE.search(name)
            if m:
                amt = float(m.group(1).replace(",", "."))
                unit = unit or m.group(2).lower()
                name = _QTY_RE.sub("", name).strip()
        return name, amt, unit

    text = str(raw or "").strip()
    if not text:
        return "", None, ""
    m = _QTY_RE.search(text)
    if not m:
        return text, None, ""
    amt = float(m.group(1).replace(",", "."))
    unit = m.group(2).lower()
    name = _QTY_RE.sub("", text).strip(" -–")
    return name, amt, unit


def _cost_for_used(name: str, amount: float | None, unit: str) -> float:
    """SEK for the amount used — never a full package price."""
    if _is_pantry(name):
        return 0.0
    key = _match_cost_key(name)
    if not key:
        return 0.0

    u = (unit or "").lower().strip()
    # Normalize aliases
    if u in ("skiva", "skivor", "blad", "klyfta", "klyftor", "näve"):
        u = "st"
    if u == "förp":
        u = "st"
    if u == "ask":
        u = "st"
    if u == "burk":
        # one can ≈ 120 g edible for tuna-like items
        amount = (amount or 1.0) * 120.0
        u = "g"
    if u == "kg":
        amount = (amount or 0.0) * 1000.0
        u = "g"
    if u == "tsk":
        amount = (amount or 0.0) / 3.0
        u = "msk"
    if u == "krm":
        return 0.0

    if amount is None:
        default = _DEFAULT_USED.get(key)
        if not default:
            # Modest unknown ingredient contribution
            return 5.0
        amount, u = default

    amt = float(amount)
    if amt <= 0:
        return 0.0

    if u in ("msk",):
        return amt * float(_SEK_PER_MSK.get(key, 0.3))
    if u in ("dl",):
        return amt * float(_SEK_PER_DL.get(key, _SEK_PER_G.get(key, 0.02) * 100))
    if u in ("st",):
        return amt * float(_SEK_PER_ST.get(key, 5.0))
    if u in ("g", ""):
        if u == "" and key in _SEK_PER_ST and amount is not None:
            # bare count sometimes stored without unit
            return amt * float(_SEK_PER_ST[key])
        return amt * float(_SEK_PER_G.get(key, 0.05))
    # Unknown unit — treat amount as pieces if small, else grams
    if amt <= 20 and key in _SEK_PER_ST:
        return amt * float(_SEK_PER_ST[key])
    return amt * float(_SEK_PER_G.get(key, 0.05))


def estimate_cost_per_portion(
    ingredients: list[Any] | None,
    *,
    servings: int = 2,
    meal_type: Any = None,
) -> int:
    """Ballpark SEK/portion from USED ingredient amounts — estimate only."""
    portions = max(1, int(servings or 2))
    total = 0.0
    matched = 0
    for raw in ingredients or []:
        name, amount, unit = _parse_qty(raw)
        if not name:
            continue
        if _is_pantry(name):
            matched += 1
            continue
        key = _match_cost_key(name)
        if not key and amount is None:
            continue
        total += _cost_for_used(name, amount, unit)
        matched += 1
    if matched <= 0:
        # Modest default dinner when nothing matched
        per = 35.0 if str(meal_type or "").lower() == "middag" else 20.0
    else:
        per = total / portions
    # Soft clamp before rounding so package-style blowups never surface
    max_ok = float(sanity_max_per_portion(meal_type))
    if per > max_ok:
        per = max_ok
    rounded = round_cost_sek(per)
    return int(rounded if rounded is not None else 20)


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
    meal_type = meta.get("meal_type")
    direct = read_cost_per_portion(meta)
    if direct is not None and not cost_exceeds_sanity(direct, meal_type=meal_type):
        return direct
    recipe = meta.get("recipe") if isinstance(meta.get("recipe"), dict) else None
    if recipe:
        nested = read_cost_per_portion(recipe)
        if nested is not None and not cost_exceeds_sanity(
            nested, meal_type=recipe.get("meal_type") or meal_type
        ):
            return nested
    ings = list(meta.get("ingredients") or [])
    if recipe and not ings:
        ings = list(
            recipe.get("ingredients_structured")
            or recipe.get("ingredients")
            or recipe.get("ingredient_lines")
            or []
        )
    if not ings:
        return None if direct is None else estimate_cost_per_portion(
            [], servings=2, meal_type=meal_type
        )
    servings = 2
    try:
        if recipe and recipe.get("portioner"):
            servings = int(recipe.get("portioner") or 2)
        elif recipe and recipe.get("portions"):
            servings = int(recipe.get("portions") or 2)
    except (TypeError, ValueError):
        servings = 2
    return estimate_cost_per_portion(ings, servings=servings, meal_type=meal_type)


def ensure_recipe_cost(
    recipe: dict[str, Any] | None,
    *,
    meta: dict[str, Any] | None = None,
    allow_estimate: bool = True,
    meal_type: Any = None,
) -> dict[str, Any]:
    """Attach cost_per_portion_sek (rounded) — single field for constraint + display.

    If an LLM/package-sized estimate exceeds the meal-type sanity bound, regenerate
    once from used ingredient amounts.
    """
    out = dict(recipe or {})
    meta = meta if isinstance(meta, dict) else {}
    mt = (
        meal_type
        or out.get("meal_type")
        or meta.get("meal_type")
        or ""
    )
    try:
        servings = int(out.get("portioner") or out.get("portions") or 2)
    except (TypeError, ValueError):
        servings = 2

    cost = read_cost_per_portion(out)
    if cost is None:
        cost = read_cost_per_portion(meta)

    regenerated = False
    if cost is not None and cost_exceeds_sanity(cost, meal_type=mt):
        # Whole-package / absurd LLM guess — regenerate from used amounts
        cost = None
        regenerated = True

    if cost is None and allow_estimate:
        ings = list(
            out.get("ingredients_structured")
            or out.get("ingredients")
            or out.get("ingredient_lines")
            or []
        )
        if not ings:
            ings = list(meta.get("ingredients") or [])
        cost = estimate_cost_per_portion(ings, servings=servings, meal_type=mt)
        regenerated = True

    if cost is not None and cost_exceeds_sanity(cost, meal_type=mt):
        # Still over after regenerate — clamp to sanity ceiling
        cost = sanity_max_per_portion(mt)

    if cost is not None:
        cost = round_cost_sek(cost)
        out["cost_per_portion_sek"] = cost
        out["cost_label"] = "ca"
        if regenerated:
            out["cost_regenerated"] = True
    return out


def cost_stat(
    recipe: dict[str, Any] | None,
    *,
    language: str = "sv",
    meal_type: Any = None,
) -> dict[str, Any] | None:
    """Presentation helper for execute view: {sek, label, unit}."""
    if not isinstance(recipe, dict):
        return None
    healed = ensure_recipe_cost(recipe, allow_estimate=True, meal_type=meal_type)
    sek = read_cost_per_portion(healed)
    if sek is None:
        return None
    return {
        "sek": sek,
        "label": format_cost_label(sek, language=language),
        "unit": "portion",
        "approx": True,
    }
