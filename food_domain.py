# -*- coding: utf-8 -*-
"""Food domain: meal type as inferred, confirmable input."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Europe/Stockholm")

# Frukost / Lunch / Middag / Kvällsmål
MEAL_TYPES: dict[str, dict[str, Any]] = {
    "frukost": {
        "sv": "Frukost",
        "en": "Breakfast",
        "show_shopping": False,
        "max_minutes": 10,
        "assume_at_home_only": True,
        "repeat_days": 1,  # habit OK next morning
    },
    "lunch": {
        "sv": "Lunch",
        "en": "Lunch",
        "show_shopping": False,  # weekday: matlåda / snabbt / ute — no full shop
        "max_minutes": 20,
        "assume_at_home_only": False,
        "repeat_days": 3,
    },
    "middag": {
        "sv": "Middag",
        "en": "Dinner",
        "show_shopping": True,
        "max_minutes_weekday": 30,
        "max_minutes_weekend": 60,
        "assume_at_home_only": False,
        "repeat_days": 7,
    },
    "kvallsmal": {
        "sv": "Kvällsmål",
        "en": "Evening snack",
        "show_shopping": False,
        "max_minutes": 5,
        "assume_at_home_only": True,
        "no_cook": True,
        "repeat_days": 1,
    },
}

MEAL_ORDER = ("frukost", "lunch", "middag", "kvallsmal")


def meal_label(key: str, language: str = "sv") -> str:
    """Full meal name for segmented controls — never abbreviated."""
    row = MEAL_TYPES.get(key) or {}
    return str(row.get(language) or row.get("sv") or key)


def meal_headline(key: str, language: str = "sv") -> str:
    """Hero headline meal name (same as chip label — full words)."""
    return meal_label(key, language)


def local_now() -> datetime:
    """App-local clock for meal windows (Sweden)."""
    return datetime.now(LOCAL_TZ)


def default_meal_type(
    hour: int | None = None,
    minute: int = 0,
    *,
    now: datetime | None = None,
) -> str:
    """
    Infer meal type from local clock:
      05:00–10:00  → frukost
      10:00–13:30  → lunch
      13:30–20:00  → middag
      20:00–24:00 (+00–05) → kvällsmål
    """
    if now is not None:
        hour = now.hour
        minute = now.minute
    elif hour is None:
        local = local_now()
        hour = local.hour
        minute = local.minute
    t = hour * 60 + minute
    if 5 * 60 <= t < 10 * 60:
        return "frukost"
    if 10 * 60 <= t < 13 * 60 + 30:
        return "lunch"
    if 13 * 60 + 30 <= t < 20 * 60:
        return "middag"
    return "kvallsmal"


def max_minutes(meal_type: str, *, is_weekend: bool = False) -> int:
    row = MEAL_TYPES.get(meal_type) or MEAL_TYPES["middag"]
    if meal_type == "middag":
        return int(
            row["max_minutes_weekend"] if is_weekend else row["max_minutes_weekday"]
        )
    return int(row.get("max_minutes") or 30)


def show_shopping(meal_type: str) -> bool:
    return bool((MEAL_TYPES.get(meal_type) or {}).get("show_shopping"))


def repeat_days(meal_type: str) -> int:
    return int((MEAL_TYPES.get(meal_type) or {}).get("repeat_days") or 7)


def assume_at_home_only(meal_type: str) -> bool:
    return bool((MEAL_TYPES.get(meal_type) or {}).get("assume_at_home_only"))


def mentions_leftovers(text: str) -> bool:
    """True when suggestion/justification claims yesterday's food or a matlåda."""
    import re

    blob = (text or "").lower()
    if not blob:
        return False
    if (
        "matlåda" in blob
        or "leftover" in blob
        or "gårdagens" in blob
        or "värm en rest" in blob
        or "reheat leftover" in blob
    ):
        return True
    if re.search(r"\brest(er|en|erna)?\b", blob):
        return True
    if "yesterday" in blob and ("reheat" in blob or "warm" in blob):
        return True
    return False


def is_leftover_candidate(candidate: dict[str, Any]) -> bool:
    meta = candidate.get("meta") if isinstance(candidate.get("meta"), dict) else {}
    if meta.get("leftover"):
        return True
    blob = f"{candidate.get('suggestion') or ''} {candidate.get('justification') or ''}"
    return mentions_leftovers(blob)


def ground_leftover_candidates(
    candidates: list[dict[str, Any]],
    dinner_title: str | None,
    language: str = "sv",
) -> list[dict[str, Any]]:
    """
    Drop ungrounded leftover suggestions; rename grounded ones to the actual dish.
    Applies to pinned packs AND LLM output (meta.leftover is not required).
    """
    sv = language == "sv"
    out: list[dict[str, Any]] = []
    for c in candidates:
        if not is_leftover_candidate(c):
            out.append(c)
            continue
        if not dinner_title:
            continue
        row = dict(c)
        if sv:
            row["suggestion"] = f"Värm gårdagens {dinner_title.lower()}"
            row["justification"] = "Redan lagat — klart på 5 minuter."
        else:
            row["suggestion"] = f"Reheat yesterday's {dinner_title.lower()}"
            row["justification"] = "Already cooked — ready in 5 minutes."
        meta = dict(row.get("meta") or {})
        meta["leftover"] = True
        row["meta"] = meta
        out.append(row)
    return out


def leftover_meal_candidate(
    dinner_title: str,
    meal_type: str,
    language: str = "sv",
) -> dict[str, Any]:
    """Only emitted when recent_cooked_dinner returned evidence."""
    sv = language == "sv"
    title = dinner_title.strip()
    if sv:
        suggestion = f"Värm gårdagens {title.lower()}"
        justification = "Redan lagat — klart på 5 minuter."
    else:
        suggestion = f"Reheat yesterday's {title.lower()}"
        justification = "Already cooked — ready in 5 minutes."
    return {
        "suggestion": suggestion,
        "justification": justification,
        "meta": {
            "meal_type": meal_type,
            "active_minutes": 5,
            "leftover": True,
            "no_recipe": True,
            "ingredients": [],
        },
    }


def reheat_execution_recipe(suggestion: str, *, language: str = "sv") -> dict[str, Any]:
    """Honest reheat steps — never a fabricated cook-from-scratch recipe."""
    sv = language == "sv"
    if sv:
        steps = [
            "Ta fram matlådan eller resterna från kylen.",
            "Värm i mikro 2–3 min (eller i kastrull på medelvärme) tills maten är genomvarm.",
            "Rör om, smaka av. Servera direkt.",
        ]
    else:
        steps = [
            "Take the lunchbox or leftovers from the fridge.",
            "Reheat in the microwave 2–3 min (or in a pan) until piping hot.",
            "Stir, taste, and serve.",
        ]
    return {
        "title": suggestion,
        "ingredients": [],
        "ingredient_lines": [],
        "steps": steps,
        "nutrition": {"kcal": 0, "protein_g": 0, "fat_g": 0, "carbs_g": 0},
        "no_recipe": True,
        "leftover": True,
    }


def is_no_recipe_meal(
    suggestion: str,
    meta: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
) -> bool:
    """Leftovers and explicit no-recipe decisions — never run the recipe engine."""
    meta = meta if isinstance(meta, dict) else {}
    execution = execution if isinstance(execution, dict) else {}
    exec_meta = execution.get("meta") if isinstance(execution.get("meta"), dict) else {}
    if meta.get("leftover") or meta.get("no_recipe"):
        return True
    if exec_meta.get("leftover") or exec_meta.get("no_recipe"):
        return True
    if execution.get("type") == "simple" and execution.get("recipe") is None:
        if is_leftover_candidate({"suggestion": suggestion, "meta": meta}):
            return True
    return is_leftover_candidate({"suggestion": suggestion, "meta": meta})


def ingredient_hints_for(suggestion: str, meal_type: str, language: str = "sv") -> list[str]:
    """Ingredient list from pinned meal packs — used when recipe must be rebuilt."""
    target = (suggestion or "").strip().lower()
    for c in meal_candidates(meal_type, language):
        if (c.get("suggestion") or "").strip().lower() == target:
            meta = c.get("meta") if isinstance(c.get("meta"), dict) else {}
            return [str(x) for x in (meta.get("ingredients") or []) if str(x).strip()]
    return []


def meal_candidates(
    meal_type: str,
    language: str = "sv",
    *,
    recent_dinner: str | None = None,
) -> list[dict[str, Any]]:
    """Pinned candidates shaped by meal type (generation, not just filter)."""
    sv = language == "sv"
    if meal_type == "frukost":
        return [
            {
                "suggestion": "Havregrynsgröt med banan" if sv else "Oatmeal with banana",
                "justification": (
                    "Frukost på 5 min — allt du redan har hemma."
                    if sv
                    else "Breakfast in 5 — everything you already have."
                ),
                "meta": {
                    "meal_type": "frukost",
                    "active_minutes": 5,
                    "assume_at_home_only": True,
                    "ingredients": ["havregryn", "mjölk", "banan", "salt"],
                },
            },
            {
                "suggestion": "Fil med müsli" if sv else "Filmjölk with muesli",
                "justification": (
                    "Ingen matlagning — öppna kylen och ät."
                    if sv
                    else "No cooking — open the fridge and eat."
                ),
                "meta": {
                    "meal_type": "frukost",
                    "active_minutes": 2,
                    "assume_at_home_only": True,
                    "ingredients": ["fil", "müsli"],
                },
            },
            {
                "suggestion": "Ägg och knäcke" if sv else "Eggs and crispbread",
                "justification": (
                    "Max 10 min — ägg du har, knäcke i skafferiet."
                    if sv
                    else "Max 10 min — eggs and crispbread you have."
                ),
                "meta": {
                    "meal_type": "frukost",
                    "active_minutes": 8,
                    "assume_at_home_only": True,
                    "ingredients": ["ägg", "knäckebröd", "smör", "salt", "peppar"],
                },
            },
        ]
    if meal_type == "lunch":
        out: list[dict[str, Any]] = []
        if recent_dinner:
            out.append(leftover_meal_candidate(recent_dinner, "lunch", language))
        import food_local_packs as flp

        # Skip "Lunch nära dig" duplicate if we already have eating_out elsewhere
        for row in flp.lunch_pack(language):
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
            if meta.get("eating_out") or (meta.get("dish_category") == "other" and not meta.get("ingredients")):
                # Keep map option once at end
                continue
            out.append(row)
        # Always offer eating-out as last pin
        out.append(
            {
                "suggestion": "Lunch nära dig" if sv else "Lunch nearby",
                "justification": (
                    "Ät ute i dag — öppna kartan och välj närmaste."
                    if sv
                    else "Eat out today — open the map and pick nearby."
                ),
                "meta": {
                    "meal_type": "lunch",
                    "eating_out": True,
                    "active_minutes": 0,
                    "dish_category": "other",
                },
            }
        )
        return out
    if meal_type == "kvallsmal":
        out = [
            {
                "suggestion": "Smörgås med ost" if sv else "Cheese sandwich",
                "justification": (
                    "Kvällsmål utan matlagning — klart på en minut."
                    if sv
                    else "Evening bite, no cooking — done in a minute."
                ),
                "meta": {
                    "meal_type": "kvallsmal",
                    "active_minutes": 2,
                    "no_cook": True,
                    "assume_at_home_only": True,
                    "ingredients": ["bröd", "ost", "smör"],
                },
            },
            {
                "suggestion": "Fil eller yoghurt" if sv else "Filmjölk or yoghurt",
                "justification": (
                    "Enkelt kvällsmål — öppna och ät."
                    if sv
                    else "Simple evening snack — open and eat."
                ),
                "meta": {
                    "meal_type": "kvallsmal",
                    "active_minutes": 1,
                    "no_cook": True,
                    "assume_at_home_only": True,
                    "ingredients": ["fil"],
                },
            },
        ]
        if recent_dinner:
            out.append(leftover_meal_candidate(recent_dinner, "kvallsmal", language))
        return out
    # middag — empty here; pipeline local dinner pack is used
    return []


def apply_meal_execution(
    meal_type: str,
    suggestion: str,
    execution: dict[str, Any],
    *,
    language: str = "sv",
    location: str = "Sverige",
    ingredients: list[str] | None = None,
    active_minutes: int | None = None,
    candidate_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adjust execution payload for meal type (shopping / labels)."""
    out = dict(execution or {})
    out["meal_type"] = meal_type
    meta = candidate_meta if isinstance(candidate_meta, dict) else {}
    if is_no_recipe_meal(suggestion, meta=meta, execution=execution):
        out["recipe"] = reheat_execution_recipe(suggestion, language=language)
        out["shopping"] = None
        out["shopping_list"] = None
        out["type"] = "simple"
        out["label"] = "Ät nu" if language == "sv" else "Eat now"
        out["detail"] = out.get("detail") or (
            "Inget recept behövs — värm och ät."
            if language == "sv"
            else "No recipe needed — heat and eat."
        )
        return out
    if meal_type == "frukost" or meal_type == "kvallsmal":
        out["shopping"] = None
        out["shopping_list"] = None
        out["type"] = out.get("type") or "recipe"
        out["label"] = "Ät nu" if language == "sv" else "Eat now"
        out["url"] = None
        out["detail"] = (
            "Hemma antas — ingen inköpsrunda."
            if language == "sv"
            else "Assumed at home — no shopping trip."
        )
        # Always attach a validated structured recipe for execute view
        import recipe_engine as reng

        ings = list(ingredients or [])
        mins = active_minutes
        if mins is None and isinstance(execution, dict):
            mins = (execution.get("meta") or {}).get("active_minutes")
        out["recipe"] = reng.ensure_valid_recipe(
            out.get("recipe") if isinstance(out.get("recipe"), dict) else None,
            suggestion,
            meal_type=meal_type,
            ingredient_hints=ings or None,
            active_minutes=int(mins) if mins is not None else None,
            portions=1,
            language=language,
            grok_api_key="",
        )
        return out
    if meal_type == "lunch":
        if out.get("type") == "map" or (execution or {}).get("type") == "map":
            out["type"] = "map"
            out["label"] = "Öppna karta" if language == "sv" else "Open map"
            out["url"] = out.get("url") or (
                f"https://www.google.com/maps/search/{suggestion}+lunch+nära+{location}"
            )
            out["shopping"] = None
            out["shopping_list"] = None
            return out
        out["shopping"] = None
        out["shopping_list"] = None
        out["label"] = out.get("label") or ("Ät nu" if language == "sv" else "Eat now")
        out["detail"] = out.get("detail") or (
            "Snabblunch — ingen stor inköpslista."
            if language == "sv"
            else "Quick lunch — no big shopping list."
        )
        import recipe_engine as reng

        ings = list(ingredients or []) or ingredient_hints_for(suggestion, meal_type, language)
        mins = active_minutes
        if mins is None and isinstance(execution, dict):
            mins = (execution.get("meta") or {}).get("active_minutes")
        out["recipe"] = reng.ensure_valid_recipe(
            out.get("recipe") if isinstance(out.get("recipe"), dict) else None,
            suggestion,
            meal_type=meal_type,
            ingredient_hints=ings or None,
            active_minutes=int(mins) if mins is not None else None,
            portions=1,
            language=language,
            grok_api_key="",
        )
        import shopping as shop_mod
        import shopping_compat as shop_compat

        mini = shop_compat.shopping_from_recipe(out["recipe"], suggestion=suggestion)
        if mini and mini.get("to_buy"):
            out["shopping"] = mini
            out["shopping_list"] = mini.get("to_buy")
            out["detail"] = shop_mod.format_assumed_line(
                list(mini.get("assumed_at_home") or []), language=language
            )
        return out
    # middag keeps full shopping from pipeline
    out["label"] = out.get("label") or (
        "Handla & laga" if language == "sv" else "Shop & cook"
    )
    return out
