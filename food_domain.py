# -*- coding: utf-8 -*-
"""Food domain: meal type as inferred, confirmable input."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

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
    row = MEAL_TYPES.get(key) or {}
    return str(row.get(language) or row.get("sv") or key)


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
    if hour is None:
        hour = datetime.now().astimezone().hour
        minute = datetime.now().astimezone().minute
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


def meal_candidates(meal_type: str, language: str = "sv") -> list[dict[str, Any]]:
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
        return [
            {
                "suggestion": "Matlåda från gårdagens gryta" if sv else "Leftover lunchbox",
                "justification": (
                    "Lunch utan krångel — värm det du redan lagat."
                    if sv
                    else "Easy lunch — reheat what you already cooked."
                ),
                "meta": {
                    "meal_type": "lunch",
                    "active_minutes": 5,
                    "leftover": True,
                    "ingredients": [],
                },
            },
            {
                "suggestion": "Äggmacka och kaffe" if sv else "Egg sandwich and coffee",
                "justification": (
                    "Snabbt vardagslunch — klart på några minuter."
                    if sv
                    else "Fast weekday lunch — done in minutes."
                ),
                "meta": {
                    "meal_type": "lunch",
                    "active_minutes": 8,
                    "ingredients": ["ägg", "bröd", "smör"],
                },
            },
            {
                "suggestion": "Sallad med tonfisk" if sv else "Tuna salad",
                "justification": (
                    "Lätt lunch — burk och grönt du har hemma."
                    if sv
                    else "Light lunch — pantry tuna and greens."
                ),
                "meta": {
                    "meal_type": "lunch",
                    "active_minutes": 10,
                    "ingredients": ["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"],
                },
            },
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
                },
            },
        ]
    if meal_type == "kvallsmal":
        return [
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
            {
                "suggestion": "Värm en rest" if sv else "Reheat leftovers",
                "justification": (
                    "Ingen ny matlagning — mikra det som finns."
                    if sv
                    else "No new cooking — microwave what’s there."
                ),
                "meta": {
                    "meal_type": "kvallsmal",
                    "active_minutes": 3,
                    "no_cook": True,
                    "leftover": True,
                    "ingredients": [],
                },
            },
        ]
    # middag — empty here; pipeline local dinner pack is used
    return []


def apply_meal_execution(
    meal_type: str,
    suggestion: str,
    execution: dict[str, Any],
    *,
    language: str = "sv",
    location: str = "Sverige",
) -> dict[str, Any]:
    """Adjust execution payload for meal type (shopping / labels)."""
    out = dict(execution or {})
    out["meal_type"] = meal_type
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
        return out
    # middag keeps full shopping from pipeline
    out["label"] = out.get("label") or (
        "Handla & laga" if language == "sv" else "Shop & cook"
    )
    return out
