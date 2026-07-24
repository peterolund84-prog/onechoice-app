# -*- coding: utf-8 -*-
"""
Structured recipe generation — structure first, text second.

LLM returns strict JSON (when API key available); otherwise a curated catalog
of REAL recipes (never title-only stubs or placeholder steps).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import requests

import llm_config

import shopping

log = logging.getLogger("onechoice.recipe")

# Hard-fail placeholder patterns (never show in UI)
_PLACEHOLDER_STEP = re.compile(
    r"(?i)(gör i ordning|ta fram det du behöver|servera som den är — eller)$"
)
_GENERIC_PREP = re.compile(
    r"(?i)^förbered ingredienserna:"
)

# Seasonings / water may appear in steps without being listed as bought ingredients.
_PANTRY_STEP_ALLOW = frozenset(
    {
        "salt",
        "peppar",
        "vatten",
        "smör",
        "olja",
        "oljaolja",  # typo guard
        "svartpeppar",
        "vitlökssalt",
    }
)

# Tokens that look like "qty + unit + word" but are not foods.
_NON_FOOD_QTY_WORDS = frozenset(
    {
        "min",
        "minuter",
        "minut",
        "sek",
        "sekunder",
        "timme",
        "timmar",
        "grader",
        "gång",
        "gånger",
        "person",
        "personer",
        "portion",
        "portioner",
        "medelvärme",
        "hög",
        "låg",
        "sida",
        "sidor",
        "cm",
        "mm",
        "per",
        "pastavatten",
        "vatten",
    }
)

# qty + metric unit + food noun (e.g. "2 dl ris", "400 g kycklingfilé")
_QTY_FOOD = re.compile(
    r"(?i)(\d+[.,]?\d*)\s*"
    r"(dl|g|kg|msk|tsk|krm|st|burk|skiva|skivor|klyfta|klyftor|förp|ask)\s+"
    r"([a-zåäöé\-]+)"
)

RECIPE_JSON_SCHEMA = """
{
  "title": "string — dish name",
  "meal_type": "frukost|lunch|middag|kvallsmal",
  "portions": 1,
  "total_minutes": 5,
  "ingredients": [
    {"name": "havregryn", "amount": "1", "unit": "dl", "category": "assumed_home|to_buy"}
  ],
  "steps": ["concrete step with amounts and minutes", "..."],
  "nutrition": {"kcal": 350, "protein_g": 12, "fat_g": 8, "carbs_g": 55}
}
"""


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())


def _ingredient_line(ing: dict[str, Any]) -> str:
    name = str(ing.get("name") or "").strip()
    amount = str(ing.get("amount") or "").strip()
    unit = str(ing.get("unit") or "").strip()
    if amount and unit:
        return f"{name} {amount} {unit}".strip()
    if amount:
        return f"{name} {amount}".strip()
    return name


# Alternatives that must never appear as separate lines (double quantity / nutrition).
_OR_INGREDIENT_GROUPS: tuple[tuple[str, ...], ...] = (
    ("fil", "yoghurt", "filmjölk", "filmjolk"),
)


def _bare_ing_name(raw: Any) -> str:
    if isinstance(raw, dict):
        return _norm_title(str(raw.get("name") or ""))
    text = _strip_qty_from_name(str(raw or ""))
    return _norm_title(text)


def _coalesce_or_ingredients(items: list[Any]) -> list[Any]:
    """Merge 'fil' + 'yoghurt' (+ filmjölk) into one 'fil eller yoghurt' row."""
    if not items:
        return items
    names = [_bare_ing_name(x) for x in items]
    drop: set[int] = set()
    inserts: list[tuple[int, Any]] = []

    for group in _OR_INGREDIENT_GROUPS:
        idxs = [i for i, n in enumerate(names) if n in group and i not in drop]
        # Also treat already-combined names as hits for that group
        combo_idxs = [
            i
            for i, n in enumerate(names)
            if i not in drop and " eller " in n and any(g in n for g in group)
        ]
        if combo_idxs and idxs:
            # Keep the combined row; drop the split ones
            drop.update(idxs)
            continue
        if len(idxs) < 2:
            continue
        # Prefer amount/unit from the first structured dict in the group
        template: dict[str, Any] | None = None
        for i in idxs:
            if isinstance(items[i], dict):
                template = dict(items[i])
                break
        label_parts = []
        for g in group:
            if g in ("filmjolk",):
                continue
            if any(names[i] == g for i in idxs):
                label_parts.append("filmjölk" if g == "filmjölk" else g)
        # Canonical Swedish label for dairy alt
        if set(label_parts) >= {"fil", "yoghurt"} or (
            "fil" in label_parts and "yoghurt" in label_parts
        ):
            label = "fil eller yoghurt"
        elif label_parts:
            label = " eller ".join(label_parts)
        else:
            continue
        drop.update(idxs)
        if template is not None:
            merged = dict(template)
            merged["name"] = label
            inserts.append((idxs[0], merged))
        else:
            # String lines — keep first amount/unit if present
            first = str(items[idxs[0]] or "")
            m = re.search(
                rf"(\d+[.,]?\d*)\s*({_UNIT_TOKEN})\b",
                first,
                flags=re.I,
            )
            if m:
                inserts.append((idxs[0], f"{label} {m.group(1)} {m.group(2)}"))
            else:
                inserts.append((idxs[0], label))

    if not drop and not inserts:
        return items
    out: list[Any] = []
    insert_map = {i: v for i, v in inserts}
    for i, item in enumerate(items):
        if i in insert_map:
            out.append(insert_map[i])
        elif i in drop:
            continue
        else:
            out.append(item)
    return out


_UNIT_TOKEN = (
    r"dl|g|kg|msk|tsk|krm|st|burk|skiva|skivor|klyfta|klyftor|förp|ask|blad|kopp"
)


def _strip_qty_from_name(text: str) -> str:
    """Normalize 'fil 2 dl' / '2 dl fil' / 'paprika (färsk) 1 st' → bare food name."""
    text = str(text or "").strip()
    if not text:
        return ""
    # Drop parenthetical notes first: "paprika (färsk)" -> "paprika"
    text = re.sub(r"\s*\([^)]*\)\s*", " ", text).strip()
    # Leading qty+unit: "400 g kycklingfilé"
    text = re.sub(
        rf"(?i)^\d+[.,]?\d*\s*(?:{_UNIT_TOKEN})\s+",
        "",
        text,
    )
    # Trailing qty+unit (finalize lines): "fil 2 dl", "vitlök 2 klyftor"
    text = re.sub(
        rf"(?i)\s+\d+[.,]?\d*\s*(?:{_UNIT_TOKEN})\s*$",
        "",
        text,
    )
    return _norm_title(text)


def _ingredient_names(ingredients: list[Any]) -> list[str]:
    """Canonical lowercase ingredient names (no qty/unit)."""
    names: list[str] = []
    for raw in ingredients:
        if isinstance(raw, dict):
            text = _strip_qty_from_name(str(raw.get("name") or ""))
        else:
            text = _strip_qty_from_name(str(raw or ""))
        if text and text not in names:
            names.append(text)
    return names


def _name_variants(name: str) -> list[str]:
    """Match stems so kycklingfilé ↔ kyckling, tortillabröd ↔ tortilla."""
    n = _norm_title(name)
    out = [n]
    for stem in (
        "kyckling",
        "tortilla",
        "yoghurt",
        "sallad",
        "tomat",
        "pasta",
        "ris",
        "ägg",
        "ost",
        "lök",
        "morot",
        "broccoli",
        "paprika",
        "tonfisk",
        "gurka",
        "havregryn",
        "banan",
        "bröd",
        "smör",
        "färs",
        "nudlar",
        "quinoa",
        "feta",
        "avokado",
        "kikärtor",
        "pesto",
        "parmesan",
        "fil",
        "müsli",
        "musli",
    ):
        if stem in n and stem not in out:
            out.append(stem)
    # First token (≥3 chars) as soft stem — covers fil, ost, ägg
    first = re.split(r"[\s\-_/]+", n)[0]
    if len(first) >= 3 and first not in out:
        out.append(first)
    return out


def _name_in_text(name: str, blob: str) -> bool:
    return any(v in blob for v in _name_variants(name) if len(v) >= 3)


def _food_covered_by_ings(food: str, ing_names: list[str]) -> bool:
    food_n = _norm_title(food)
    if food_n in _PANTRY_STEP_ALLOW or food_n in _NON_FOOD_QTY_WORDS:
        return True
    for ing in ing_names:
        if _name_in_text(food_n, ing) or _name_in_text(ing, food_n):
            return True
        # shared stem
        for v in _name_variants(ing):
            if len(v) >= 4 and v in food_n:
                return True
    return False


def _ingredient_mirrors_title(title: str, name: str) -> bool:
    t = _norm_title(title)
    n = _norm_title(name)
    if not t or not n:
        return False
    if n == t:
        return True
    # Long ingredient names that mirror the dish title (stub pattern)
    min_len = max(12, int(len(t) * 0.6))
    return len(n) >= min_len and (n in t or t in n)


def _title_in_ingredients(title: str, ingredients: list[Any]) -> bool:
    """True when the dish title is used as a stub ingredient with nothing else real."""
    t = _norm_title(title)
    if not t:
        return False
    names: list[str] = []
    for raw in ingredients:
        if isinstance(raw, dict):
            n = _norm_title(str(raw.get("name") or ""))
        else:
            n = _bare_ing_name(raw)
        if n:
            names.append(n)
    if not names:
        return False
    has_title = any(_ingredient_mirrors_title(t, n) for n in names)
    if not has_title:
        return False
    # Dishes like "Fil eller yoghurt" legitimately list that as the main line
    # plus toppings — only reject title-only stubs.
    others = [n for n in names if not _ingredient_mirrors_title(t, n)]
    return len(others) == 0


def _step_is_concrete(step: str) -> bool:
    s = (step or "").strip()
    if len(s) < 12:
        return False
    if _PLACEHOLDER_STEP.search(s):
        return False
    if _GENERIC_PREP.search(s):
        return False
    if s.lower() in ("ät.", "servera.", "klart."):
        return False
    # Need a concrete cue: number, time unit, or strong cooking verb
    if re.search(r"\d", s):
        return True
    verbs = (
        "koka", "vispa", "stek", "blanda", "hacka", "skiva", "rör", "sjud",
        "förbered", "tillaga",
        "gratinera", "bryn", "krossa", "tillsätt", "häll", "bred", "lägg",
        "ta fram", "servera", "häll upp", "strö", "ät", "rosta", "stapla",
        "forma", "grilla", "krydda", "smaka", "värm", "skär", "strimla",
        "skölj", "riv", "fräs", "blögg", "toppa", "ringla", "vik", "rulla",
        "fördela", "varva", "gratinera", "vila", "spara", "späd",
        "boil", "fry", "mix", "slice", "simmer", "whisk",
    )
    low = s.lower()
    return any(v in low for v in verbs)


def _check_ingredient_step_grounding(
    ingredients: list[Any], steps: list[Any]
) -> tuple[bool, str]:
    """Coverage + grounding: list ↔ steps must agree on foods."""
    ing_names = _ingredient_names(list(ingredients or []))
    if not ing_names:
        return False, "no_ingredient_names"
    steps_blob = " ".join(str(s) for s in (steps or [])).lower()

    # Coverage: every listed ingredient appears in at least one step
    for name in ing_names:
        if name in _PANTRY_STEP_ALLOW:
            continue
        if not _name_in_text(name, steps_blob):
            return False, f"uncovered_ingredient:{name}"

    # Grounding: qty+unit+food in steps must exist in the ingredient list
    for m in _QTY_FOOD.finditer(steps_blob):
        food = _norm_title(m.group(3))
        if len(food) < 3:
            continue
        if food in _NON_FOOD_QTY_WORDS or food in _PANTRY_STEP_ALLOW:
            continue
        if not _food_covered_by_ings(food, ing_names):
            return False, f"ungrounded_step_food:{food}"
    return True, "ok"


def _ingredients_for_grounding(recipe: dict[str, Any]) -> list[Any]:
    """Prefer structured dicts (bare names) over finalize display lines."""
    structured = recipe.get("ingredients_structured")
    if (
        isinstance(structured, list)
        and structured
        and isinstance(structured[0], dict)
    ):
        return list(structured)
    ings = recipe.get("ingredients") or recipe.get("ingredient_lines") or []
    return list(ings or [])


def validate_recipe(recipe: dict[str, Any] | None, *, title: str = "") -> tuple[bool, str]:
    """Reject stubs and ingredient↔step contradictions before display."""
    if not isinstance(recipe, dict):
        return False, "not_a_dict"
    dish = str(recipe.get("title") or title or "")
    ings = _ingredients_for_grounding(recipe)
    if isinstance(ings, list) and ings and isinstance(ings[0], dict):
        ing_count = len(ings)
    else:
        ing_count = len(list(ings or []))
    if ing_count < 2:
        return False, "too_few_ingredients"
    if _title_in_ingredients(dish, ings):
        return False, "title_as_ingredient"
    steps = list(recipe.get("steps") or [])
    if len(steps) < 3:
        return False, "too_few_steps"
    for step in steps:
        if not _step_is_concrete(str(step)):
            return False, f"non_concrete_step:{step[:40]}"
    grounded, g_reason = _check_ingredient_step_grounding(ings, steps)
    if not grounded:
        return False, g_reason
    nut = recipe.get("nutrition")
    if not isinstance(nut, dict):
        return False, "missing_nutrition"
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        try:
            int(nut.get(key))
        except (TypeError, ValueError):
            return False, f"bad_nutrition_{key}"
    return True, "ok"


def recipe_is_valid(recipe: dict[str, Any] | None, title: str = "") -> bool:
    ok, _ = validate_recipe(recipe, title=title)
    return ok


def _round_nutrition_block(nut: dict[str, Any]) -> dict[str, int]:
    return shopping.round_nutrition(
        float(nut.get("kcal") or 0),
        float(nut.get("protein_g") or 0),
        float(nut.get("fat_g") or 0),
        float(nut.get("carbs_g") or 0),
    )


def _finalize_recipe(raw: dict[str, Any], *, source: str) -> dict[str, Any]:
    """Normalize to app-facing recipe dict."""
    title = str(raw.get("title") or "")
    structured = _coalesce_or_ingredients(list(raw.get("ingredients") or []))
    lines = _coalesce_or_ingredients(list(raw.get("ingredient_lines") or []))
    if not lines and structured and isinstance(structured[0], dict):
        lines = [_ingredient_line(i) for i in structured if isinstance(i, dict)]
    if not lines:
        lines = [str(x) for x in structured if x]
    # Coalesce again after line materialization (covers mixed shapes)
    lines = [str(x) for x in _coalesce_or_ingredients(lines)]
    if structured and isinstance(structured[0], dict):
        structured = _coalesce_or_ingredients(structured)
    portions = max(1, int(raw.get("portions") or raw.get("portioner") or 1))
    nut_raw = raw.get("nutrition") if isinstance(raw.get("nutrition"), dict) else {}
    rounded = _round_nutrition_block(nut_raw)
    # Catalog stores per-portion; LLM sometimes returns whole-pot totals.
    # Values ≥900 with portions≥2 are treated as totals and divided.
    per_flag = str(nut_raw.get("per") or "").lower()
    if portions > 1 and rounded["kcal"] >= 900 and per_flag not in ("portion", "serving", "per_portion"):
        rounded = shopping.round_nutrition(
            rounded["kcal"] / portions,
            rounded["protein_g"] / portions,
            rounded["fat_g"] / portions,
            rounded["carbs_g"] / portions,
        )
    mins = raw.get("total_minutes", raw.get("active_minutes"))
    out: dict[str, Any] = {
        "title": title,
        "meal_type": raw.get("meal_type"),
        "ingredients": lines,
        "ingredient_lines": lines,
        "ingredients_structured": structured if structured else None,
        "steps": list(raw.get("steps") or []),
        "unit_system": "metric",
        "language": raw.get("language") or "sv",
        "portioner": portions,
        "portions": portions,
        "kcal_per_portion": rounded["kcal"],
        "protein_g_per_portion": rounded["protein_g"],
        "nutrition": {
            **rounded,
            "per": "portion",
            "servings": portions,
            "kcal_per_portion": rounded["kcal"],
            "protein_g_per_portion": rounded["protein_g"],
            "portioner": portions,
            "label": "ca-värden",
            "suggestion": title,
        },
        "recipe_source": source,
    }
    if raw.get("_llm_raw"):
        out["_llm_raw"] = raw["_llm_raw"]
    if mins is not None:
        try:
            out["active_minutes"] = int(mins)
            out["total_minutes"] = int(mins)
        except (TypeError, ValueError):
            pass
    return out


# Curated REAL recipes — offline / LLM fallback (never stubs)
_CATALOG: dict[str, dict[str, Any]] = {
    "havregrynsgröt med banan": {
        "title": "Havregrynsgröt med banan",
        "meal_type": "frukost",
        "portions": 1,
        "total_minutes": 5,
        "ingredients": [
            {"name": "havregryn", "amount": "1", "unit": "dl", "category": "assumed_home"},
            {"name": "vatten", "amount": "2", "unit": "dl", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "banan", "amount": "1", "unit": "st", "category": "to_buy"},
        ],
        "steps": [
            "Koka upp 2 dl vatten med 1 krm salt (ca 2 min).",
            "Rör ner 1 dl havregryn. Sjud på låg värme 3–4 min under omrörning.",
            "Skiva banan ovanpå gröten. Servera varm.",
        ],
        "nutrition": {"kcal": 350, "protein_g": 10, "fat_g": 5, "carbs_g": 65},
    },
    "fil med müsli": {
        "title": "Fil med müsli",
        "meal_type": "frukost",
        "portions": 1,
        "total_minutes": 2,
        "ingredients": [
            {"name": "fil", "amount": "2", "unit": "dl", "category": "assumed_home"},
            {"name": "müsli", "amount": "0.5", "unit": "dl", "category": "assumed_home"},
        ],
        "steps": [
            "Häll 2 dl fil i en skål.",
            "Strö över 0,5 dl müsli.",
            "Servera direkt — ingen värme behövs (0 min).",
        ],
        "nutrition": {"kcal": 300, "protein_g": 15, "fat_g": 5, "carbs_g": 45},
    },
    "ägg och knäcke": {
        "title": "Ägg och knäcke",
        "meal_type": "frukost",
        "portions": 1,
        "total_minutes": 8,
        "ingredients": [
            {"name": "ägg", "amount": "2", "unit": "st", "category": "assumed_home"},
            {"name": "knäckebröd", "amount": "2", "unit": "skivor", "category": "assumed_home"},
            {"name": "smör", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Koka 2 ägg i 6–7 min (med skal) eller stek dem i 1 msk smör.",
            "Rosta knäckebröd 1 min i torr panna eller brödrost.",
            "Bred smör på knäckret, lägg äggen ovanpå. Smaka av med salt.",
        ],
        "nutrition": {"kcal": 400, "protein_g": 20, "fat_g": 25, "carbs_g": 25},
    },
    "smörgås med ost": {
        "title": "Smörgås med ost",
        "meal_type": "kvallsmal",
        "portions": 1,
        "total_minutes": 2,
        "ingredients": [
            {"name": "bröd", "amount": "2", "unit": "skivor", "category": "assumed_home"},
            {"name": "ost", "amount": "2", "unit": "skivor", "category": "assumed_home"},
            {"name": "smör", "amount": "1", "unit": "tsk", "category": "assumed_home"},
        ],
        "steps": [
            "Ta fram 2 skivor bröd och 2 skivor ost.",
            "Bred 1 tsk smör på brödet och lägg på osten.",
            "Servera direkt — eller grilla 1 min om du vill ha den varm.",
        ],
        "nutrition": {"kcal": 450, "protein_g": 20, "fat_g": 25, "carbs_g": 35},
    },
    "proteinomelett med frukt": {
        "title": "Proteinomelett med frukt",
        "meal_type": "middag",
        "portions": 1,
        "total_minutes": 15,
        "ingredients": [
            {"name": "ägg", "amount": "3", "unit": "st", "category": "to_buy"},
            {"name": "mjölk", "amount": "2", "unit": "msk", "category": "to_buy"},
            {"name": "tomat", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "spenat", "amount": "1", "unit": "näve", "category": "to_buy"},
            {"name": "ost", "amount": "40", "unit": "g", "category": "to_buy"},
            {"name": "smör", "amount": "1", "unit": "tsk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Vispa 3 ägg med 2 msk mjölk, salt och peppar.",
            "Hacka tomat och skölj spenat. Riv ost.",
            "Smält 1 tsk smör i nonstick-panna. Häll i äggblandningen.",
            "När ytan stelnar: lägg på grönt och ost, vik ihop. Stek 1 min till.",
        ],
        "nutrition": {"kcal": 450, "protein_g": 30, "fat_g": 30, "carbs_g": 10},
    },
    "äggröra": {
        "title": "Äggröra",
        "meal_type": "frukost",
        "portions": 1,
        "total_minutes": 8,
        "ingredients": [
            {"name": "ägg", "amount": "2", "unit": "st", "category": "assumed_home"},
            {"name": "smör", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Vispa 2 ägg med 1 krm salt och peppar i en skål (30 sek).",
            "Smält 1 msk smör i stekpanna på medelvärme.",
            "Häll i äggen och rör långsamt 2–3 min tills röran är krämig. Servera direkt.",
        ],
        "nutrition": {"kcal": 350, "protein_g": 20, "fat_g": 25, "carbs_g": 5},
    },
    "proteinomelett med grönt": {
        "title": "Proteinomelett med grönt",
        "meal_type": "middag",
        "portions": 1,
        "total_minutes": 15,
        "ingredients": [
            {"name": "ägg", "amount": "3", "unit": "st", "category": "to_buy"},
            {"name": "mjölk", "amount": "2", "unit": "msk", "category": "to_buy"},
            {"name": "tomat", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "spenat", "amount": "1", "unit": "näve", "category": "to_buy"},
            {"name": "ost", "amount": "40", "unit": "g", "category": "to_buy"},
            {"name": "smör", "amount": "1", "unit": "tsk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Vispa 3 ägg med 2 msk mjölk, salt och peppar.",
            "Hacka tomat och skölj spenat. Riv ost.",
            "Smält 1 tsk smör i nonstick-panna. Häll i äggblandningen.",
            "När ytan stelnar: lägg på grönt och ost, vik ihop. Stek 1 min till.",
        ],
        "nutrition": {"kcal": 450, "protein_g": 30, "fat_g": 30, "carbs_g": 10},
    },
    "fil eller yoghurt": {
        "title": "Fil eller yoghurt",
        "meal_type": "frukost",
        "portions": 1,
        "total_minutes": 2,
        "ingredients": [
            {
                "name": "fil eller yoghurt",
                "amount": "2",
                "unit": "dl",
                "category": "assumed_home",
            },
            {"name": "honung", "amount": "1", "unit": "tsk", "category": "assumed_home"},
        ],
        "steps": [
            "Ta fram fil eller yoghurt (2 dl) i en skål.",
            "Ringla 1 tsk honung ovanpå om du vill ha sötma.",
            "Servera direkt — ingen värme behövs (0 min).",
        ],
        "nutrition": {"kcal": 250, "protein_g": 12, "fat_g": 5, "carbs_g": 35},
    },
    "sallad med tonfisk": {
        "title": "Sallad med tonfisk",
        "meal_type": "lunch",
        "portions": 1,
        "total_minutes": 10,
        "ingredients": [
            {"name": "tonfisk", "amount": "1", "unit": "burk", "category": "to_buy"},
            {"name": "sallad", "amount": "4", "unit": "dl", "category": "to_buy"},
            {"name": "gurka", "amount": "0.5", "unit": "st", "category": "to_buy"},
            {"name": "olja", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Skölj och strimla sallad (ca 4 dl). Skär halv gurka i kuber.",
            "Öppna 1 burk tonfisk i vatten och låt rinna av.",
            "Blanda sallad, gurka och tonfisk i en skål. Ringla 1 msk olja.",
            "Krydda med salt och peppar. Servera direkt.",
        ],
        "nutrition": {"kcal": 320, "protein_g": 28, "fat_g": 12, "carbs_g": 8},
    },
    "äggmacka och kaffe": {
        "title": "Äggmacka och kaffe",
        "meal_type": "lunch",
        "portions": 1,
        "total_minutes": 8,
        "ingredients": [
            {"name": "ägg", "amount": "2", "unit": "st", "category": "assumed_home"},
            {"name": "bröd", "amount": "2", "unit": "skivor", "category": "assumed_home"},
            {"name": "smör", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Stek 2 ägg i 1 msk smör till önskad konsistens (ca 4 min).",
            "Rosta 2 skivor bröd i brödrost eller torr panna (1 min).",
            "Lägg äggen på brödet. Smaka av med salt och peppar. Servera med kaffe.",
        ],
        "nutrition": {"kcal": 380, "protein_g": 18, "fat_g": 18, "carbs_g": 32},
    },
    "kycklingwok med ris": {
        "title": "Kycklingwok med ris",
        "meal_type": "middag",
        "portions": 2,
        "total_minutes": 25,
        "ingredients": [
            {"name": "kycklingfilé", "amount": "400", "unit": "g", "category": "to_buy"},
            {"name": "ris", "amount": "2", "unit": "dl", "category": "to_buy"},
            {"name": "broccoli", "amount": "200", "unit": "g", "category": "to_buy"},
            {"name": "morot", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "paprika (färsk)", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "sojasås", "amount": "2", "unit": "msk", "category": "to_buy"},
            {"name": "olja", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Skölj 2 dl ris och koka enligt förpackning (ca 12 min).",
            "Skär 400 g kycklingfilé i bitar. Strimla morot, broccoli och paprika.",
            "Hetta upp 1 msk olja i wok. Stek kyckling 5–6 min tills genomstekt.",
            "Tillsätt grönsaker, stek 4 min. Ringla 2 msk sojasås. Servera med ris.",
        ],
        "nutrition": {"kcal": 550, "protein_g": 45, "fat_g": 15, "carbs_g": 55},
    },
    "krämig tomatsås-pasta": {
        "title": "Krämig tomatsås-pasta",
        "meal_type": "middag",
        "portions": 2,
        "total_minutes": 20,
        "ingredients": [
            {"name": "pasta", "amount": "200", "unit": "g", "category": "to_buy"},
            {"name": "krossade tomater", "amount": "400", "unit": "g", "category": "to_buy"},
            {"name": "gul lök", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "vitlök", "amount": "2", "unit": "klyftor", "category": "assumed_home"},
            {"name": "grädde", "amount": "1", "unit": "dl", "category": "to_buy"},
            {"name": "parmesan", "amount": "50", "unit": "g", "category": "to_buy"},
            {"name": "olja", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Koka 200 g pasta i saltat vatten enligt förpackning (ca 10 min).",
            "Fräs hackad lök och vitlök i 1 msk olja 3 min.",
            "Tillsätt 400 g krossade tomater och 1 dl grädde. Sjud 8 min.",
            "Blanda pastan i såsen. Riv 50 g parmesan ovanpå. Servera.",
        ],
        "nutrition": {"kcal": 550, "protein_g": 20, "fat_g": 25, "carbs_g": 60},
    },
    "klassisk burgare hemma": {
        "title": "Klassisk burgare hemma",
        "meal_type": "middag",
        "portions": 2,
        "total_minutes": 25,
        "ingredients": [
            {"name": "nötfärs", "amount": "400", "unit": "g", "category": "to_buy"},
            {"name": "hamburgerbröd", "amount": "2", "unit": "st", "category": "to_buy"},
            {"name": "ost", "amount": "2", "unit": "skivor", "category": "to_buy"},
            {"name": "sallad", "amount": "4", "unit": "blad", "category": "to_buy"},
            {"name": "tomat", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "gul lök", "amount": "0.5", "unit": "st", "category": "to_buy"},
            {"name": "olja", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Blanda 400 g nötfärs med salt och peppar. Forma 2 biffar (ca 2 cm tjocka).",
            "Stek i 1 msk olja 3–4 min per sida. Lägg ost sista minuten.",
            "Rosta hamburgerbröd 1 min. Stapla bröd, sallad, tomat, lök och biff.",
            "Servera direkt med valfri sås.",
        ],
        "nutrition": {"kcal": 650, "protein_g": 35, "fat_g": 35, "carbs_g": 45},
    },
    "wrap med kyckling": {
        "title": "Wrap med kyckling",
        "meal_type": "lunch",
        "portions": 1,
        "total_minutes": 12,
        "ingredients": [
            {"name": "tortilla", "amount": "2", "unit": "st", "category": "to_buy"},
            {"name": "kycklingfilé", "amount": "200", "unit": "g", "category": "to_buy"},
            {"name": "sallad", "amount": "4", "unit": "blad", "category": "to_buy"},
            {"name": "tomat", "amount": "1", "unit": "st", "category": "to_buy"},
            {"name": "yoghurt", "amount": "2", "unit": "msk", "category": "to_buy"},
            {"name": "olja", "amount": "1", "unit": "msk", "category": "assumed_home"},
            {"name": "salt", "amount": "1", "unit": "krm", "category": "assumed_home"},
            {"name": "peppar", "amount": "1", "unit": "krm", "category": "assumed_home"},
        ],
        "steps": [
            "Värm 2 tortilla i torr panna 20 sek per sida (eller 15 sek i mikro).",
            "Skär 200 g kycklingfilé i strimlor. Stek i 1 msk olja 5–6 min tills genomstekt. Krydda med salt och peppar.",
            "Strimla sallad och skär tomat i klyftor.",
            "Fördela kyckling, sallad och tomat på tortillan. Ringla 2 msk yoghurt ovanpå.",
            "Rulla ihop wrapen tätt. Servera direkt.",
        ],
        "nutrition": {"kcal": 480, "protein_g": 38, "fat_g": 14, "carbs_g": 42},
    },
}


# English pack titles → Swedish catalog keys. V1 note: the recipe body stays
# Swedish until the catalog is translated; this keeps EN mode WORKING instead
# of raising ValueError (which killed decide() for language="en").
_EN_ALIASES: dict[str, str] = {
    "oatmeal with banana": "havregrynsgröt med banan",
    "oatmeal porridge": "havregrynsgröt med banan",
    "cheese sandwich": "smörgås med ost",
    "ham and cheese sandwich": "smörgås med ost",
    "egg sandwich and coffee": "smörgås med ost",
    "egg sandwiches": "smörgås med ost",
    "eggs and crispbread": "ägg och knäcke",
    "scrambled eggs": "äggröra",
    "fried eggs with tomato": "äggröra",
    "filmjölk or yoghurt": "fil eller yoghurt",
    "plain yoghurt": "fil eller yoghurt",
    "yoghurt with jam": "fil eller yoghurt",
    "yoghurt med sylt": "fil eller yoghurt",
    "yoghurt bowl with banana": "fil med müsli",
    "filmjölk with muesli": "fil med müsli",
    "egg sandwich and coffee": "äggmacka och kaffe",
    "tuna salad": "sallad med tonfisk",
    "omelette with pepper and cheese": "proteinomelett med grönt",
    "chicken stir-fry from what you have": "kycklingwok med ris",
    "chicken wok with rice": "kycklingwok med ris",
    "creamy tomato pasta": "krämig tomatsås-pasta",
    "tomato pasta with garlic": "krämig tomatsås-pasta",
    "chicken wrap": "wrap med kyckling",
    "wrap with chicken": "wrap med kyckling",
    "ethiopian-inspired lentil stew": "etiopisk-inspirerad linsgryta",
}


def _catalog_lookup(title: str) -> dict[str, Any] | None:
    key = _norm_title(title)
    alias = _EN_ALIASES.get(key)
    if alias and alias in _CATALOG:
        out = dict(_CATALOG[alias])
        out["title"] = title
        return out
    if key in _CATALOG:
        return dict(_CATALOG[key])
    for cat_key, recipe in _CATALOG.items():
        if cat_key in key or key in cat_key:
            out = dict(recipe)
            out["title"] = title
            return out
    return None


def _parse_llm_recipe(content: str) -> dict[str, Any]:
    raw = str(content or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", raw)
    if brace:
        raw = brace.group(0)
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("recipe JSON must be object")
    return data


def _grok_recipe_json(
    title: str,
    *,
    meal_type: str,
    ingredient_hints: list[str] | None,
    language: str,
    api_key: str,
    retry_hint: str = "",
) -> dict[str, Any]:
    lang = "Swedish" if language == "sv" else "English"
    hints = json.dumps(list(ingredient_hints or []), ensure_ascii=False)
    system = (
        "You are a Swedish home-cook recipe writer for OneChoice. "
        "Return ONLY valid JSON — no markdown, no commentary. "
        "Structure first: complete ingredients with metric amounts, then concrete steps, "
        "then nutrition estimated from those amounts for ONE portion."
    )
    user = f"""
Dish: {title}
Meal type: {meal_type}
Language: {lang}
Known ingredient hints (use or expand): {hints}
{retry_hint}

Return JSON matching exactly:
{RECIPE_JSON_SCHEMA}

Rules:
- ingredients.length >= 3 with real amounts (dl, g, st, msk, krm)
- steps.length >= 3; each step names amounts/times and a concrete action
- EVERY ingredient name MUST appear in at least one step (coverage)
- EVERY quantified food in steps (e.g. "2 dl ris") MUST be in the ingredient list (grounding)
- NEVER invent sides (ris, pasta) that are not in the ingredient list
- NEVER use placeholder steps like "Ta fram det du behöver" or "Gör i ordning och ät"
- The dish title must NOT appear as an ingredient name
- nutrition: per ONE portion, reasonable estimates from ingredient amounts
- Swedish supermarket basics only (major chains — no specialty imports)
"""
    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": llm_config.text_model(),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.4,
            "max_tokens": 1200,
        },
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("empty grok choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    parsed = _parse_llm_recipe(content)
    parsed["_llm_raw"] = content
    return parsed


def _hints_to_structured(hints: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hints:
        name = str(h).strip()
        if not name:
            continue
        out.append({"name": name, "amount": "", "unit": "", "category": "to_buy"})
    return out


def _template_from_hints(
    title: str,
    *,
    meal_type: str,
    hints: list[str],
    active_minutes: int | None,
) -> dict[str, Any] | None:
    """Dish-aware structured recipe from hints + shopping._recipe_steps.

    Kept (not retired): offline / allow_llm=False still needs a path when the
    catalog misses a title. Steps come from per-dish branches in
    shopping._recipe_steps — the generic protein+ris prose is rejected by
    validate_recipe grounding if it contradicts the hint list.
    """
    if len(hints) < 2:
        return None
    steps = shopping._recipe_steps(title, hints)  # noqa: SLF001 — reuse dish-specific steps
    if len(steps) < 3:
        return None
    if any(_PLACEHOLDER_STEP.search(s) or _GENERIC_PREP.search(s) for s in steps):
        return None
    structured = _hints_to_structured(hints)
    est = shopping.estimate_nutrition(hints, suggestion=title, servings=1)
    raw = {
        "title": title,
        "meal_type": meal_type,
        "portions": 1 if meal_type in ("frukost", "kvallsmal") else 2,
        "total_minutes": active_minutes or 15,
        "ingredients": structured,
        "ingredient_lines": hints,
        "steps": steps,
        "nutrition": {
            "kcal": est.get("kcal", 400),
            "protein_g": est.get("protein_g", 20),
            "fat_g": est.get("fat_g", 15),
            "carbs_g": est.get("carbs_g", 40),
        },
    }
    # Fail closed — never hand a contradictory template to the UI
    finalized = _finalize_recipe(raw, source="template")
    ok, _ = validate_recipe(finalized, title=title)
    if not ok:
        return None
    return raw


def materialize_recipe(
    title: str,
    ingredient_hints: list[str] | None = None,
    *,
    meal_type: str = "middag",
    active_minutes: int | None = None,
    portions: int | None = None,
    language: str = "sv",
    grok_api_key: str = "",
    allow_llm: bool = True,
) -> dict[str, Any]:
    """
    Produce a validated structured recipe. Never returns title-only stubs.
    Order: catalog → LLM (retry once) → hint template → raise.
    """
    title = str(title or "").strip()
    hints = [str(x).strip() for x in (ingredient_hints or []) if str(x).strip()]

    # 1) Curated catalog
    cat = _catalog_lookup(title)
    if cat:
        if portions:
            cat["portions"] = int(portions)
        if active_minutes is not None:
            cat["total_minutes"] = int(active_minutes)
        finalized = _finalize_recipe(cat, source="catalog")
        ok, reason = validate_recipe(finalized, title=title)
        if ok:
            return finalized
        last_err = reason
    else:
        last_err = "no_catalog_match"
    if allow_llm and grok_api_key and len(str(grok_api_key).strip()) > 10:
        last_err = ""
        for attempt in range(2):
            try:
                retry = (
                    f"\nPREVIOUS ATTEMPT INVALID: {last_err}. Fix all validation errors."
                    if attempt
                    else ""
                )
                raw = _grok_recipe_json(
                    title,
                    meal_type=meal_type,
                    ingredient_hints=hints,
                    language=language,
                    api_key=grok_api_key.strip(),
                    retry_hint=retry,
                )
                if portions:
                    raw["portions"] = int(portions)
                if active_minutes is not None:
                    raw["total_minutes"] = int(active_minutes)
                raw["title"] = title
                raw["meal_type"] = meal_type
                finalized = _finalize_recipe(raw, source="llm")
                ok, reason = validate_recipe(finalized, title=title)
                if ok:
                    return finalized
                last_err = reason
            except Exception as exc:
                last_err = str(exc)
                log.warning("LLM recipe attempt %s failed: %s", attempt + 1, exc)

    # 3) Hint + shopping steps template
    tmpl = _template_from_hints(
        title,
        meal_type=meal_type,
        hints=hints,
        active_minutes=active_minutes,
    )
    if tmpl:
        if portions:
            tmpl["portions"] = int(portions)
        finalized = _finalize_recipe(tmpl, source="template")
        ok, _ = validate_recipe(finalized, title=title)
        if ok:
            return finalized

    # 4) Last resort: infer ingredient list from dish name (never call build_shopping — recursion)
    try:
        inferred = shopping._infer_full_ingredients(title)  # noqa: SLF001
        if inferred:
            tmpl2 = _template_from_hints(
                title,
                meal_type=meal_type,
                hints=inferred,
                active_minutes=active_minutes,
            )
            if tmpl2:
                finalized = _finalize_recipe(tmpl2, source="inferred_template")
                ok, _ = validate_recipe(finalized, title=title)
                if ok:
                    return finalized
    except Exception as exc:
        log.warning("inferred template fallback failed: %s", exc)

    raise ValueError(f"Could not materialize valid recipe for {title!r} ({last_err})")


def ensure_valid_recipe(
    recipe: dict[str, Any] | None,
    title: str,
    *,
    meal_type: str = "middag",
    ingredient_hints: list[str] | None = None,
    active_minutes: int | None = None,
    portions: int | None = None,
    language: str = "sv",
    grok_api_key: str = "",
) -> dict[str, Any]:
    """Keep valid recipes; regenerate stubs."""
    if recipe_is_valid(recipe, title):
        return dict(recipe)  # type: ignore[arg-type]
    return materialize_recipe(
        title,
        ingredient_hints,
        meal_type=meal_type,
        active_minutes=active_minutes,
        portions=portions,
        language=language,
        grok_api_key=grok_api_key,
    )
