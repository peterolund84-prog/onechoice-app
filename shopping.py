# -*- coding: utf-8 -*-
"""
Food shopping lists — completeness first, then split.

Hard rules:
1. Generate the FULL ingredient list for the dish.
2. Split into:
   - to_buy: ALL fresh (meat/fish/dairy/produce) always + pantry a household might lack
   - assumed_at_home: ONLY true staples (salt, pepper, oil, butter, sugar, flour, common dried spices)
3. Every recipe ingredient must appear in exactly one list.
4. Main protein missing from to_buy is a critical failure → regenerate.
"""

from __future__ import annotations

import re
from typing import Any

# ONLY these may be assumed at home — nothing else qualifies
ASSUMED_STAPLES = frozenset(
    {
        "salt",
        "peppar",
        "svartpeppar",
        "olja",
        "matolja",
        "rapsolja",
        "olivolja",
        "smör",
        "socker",
        "strösocker",
        "mjöl",
        "vetemjöl",
        # common dried spices (shelf staples)
        "curry",
        "paprika",
        "spiskummin",
        "kanel",
        "oregano",
        "basilika",
        "timjan",
        "rosmarin",
        "chiliflingor",
        "cayenne",
        "ingefära (torkad)",
        "vitlökspulver",
        "lökpulver",
    }
)

# Fresh always → to_buy (never "assumed in fridge")
FRESH_MARKERS = (
    "kyckling",
    "kycklingfilé",
    "kycklinglår",
    "nötfärs",
    "färs",
    "köttfärs",
    "fläsk",
    "bacon",
    "korv",
    "lax",
    "torsk",
    "räkor",
    "fisk",
    "kött",
    "ägg",
    "mjölk",
    "grädde",
    "gräddfil",
    "yoghurt",
    "creme fraiche",
    "crème fraîche",
    "ost",
    "parmesan",
    "smörgåsost",
    "lök",
    "gul lök",
    "rödlök",
    "vitlök",
    "tomat",
    "gurka",
    "avokado",
    "spenat",
    "sallad",
    "morot",
    "broccoli",
    "paprika (färsk)",
    "citron",
    "lime",
    "ingefära (färsk)",
    "chili (färsk)",
    "potatis",
    "sötpotatis",
    "zucchini",
    "aubergine",
    "champinjon",
    "svamp",
    "banan",
    "äpple",
    "frukt",
)

# Pantry that a household might lack → always to_buy (with optional hint)
PANTRY_BUY = frozenset(
    {
        "ris",
        "jasminris",
        "basmatiris",
        "pasta",
        "spaghetti",
        "nudlar",
        "kokosmjölk",
        "soja",
        "sojasås",
        "krossade tomater",
        "passata",
        "tomatpuré",
        "buljong",
        "hönsbuljong",
        "grönsaksbuljong",
        "linser",
        "röda linser",
        "kikärtor",
        "bönor",
        "hamburgerbröd",
        "tortilla",
        "majsstärkelse",
        "honung",
        "vinäger",
        "balsamico",
        "sesamolja",
        "fish sauce",
        "fisksås",
        "miso",
        "tahini",
        "jordnötssmör",
        "kokosflingor",
        "quinoa",
        "couscous",
        "havregryn",
    }
)

STORE_ORDER = ("frukt & grönt", "kött & fisk", "mejeri", "skafferi", "fryst")

PROTEIN_ALIASES = {
    "kyckling": ("kyckling", "kycklingfilé", "kycklinglår", "chicken"),
    "lax": ("lax", "salmon"),
    "nötfärs": ("nötfärs", "köttfärs", "färs", "burgare"),
    "räkor": ("räkor", "scampi", "shrimp"),
    "torsk": ("torsk", "fisk"),
    "ägg": ("ägg", "omelett", "omelette"),
    "bacon": ("bacon",),
    "fläsk": ("fläsk", "karré", "kotlett"),
}


def build_shopping(
    suggestion: str,
    *,
    meta: dict[str, Any] | None = None,
    store: str = "ICA",
) -> dict[str, Any] | None:
    """
    Return structured shopping payload or None if validation fails
    (caller must regenerate / discard candidate).
    """
    meta = meta or {}
    full = meta.get("ingredients") or _infer_full_ingredients(suggestion)
    if not full:
        return None

    # Normalize + dedupe, preserve order
    seen: set[str] = set()
    ingredients: list[str] = []
    for item in full:
        name = _norm_item(str(item))
        if not name or name in seen:
            continue
        seen.add(name)
        ingredients.append(name)

    to_buy_flat: list[str] = []
    assumed: list[str] = []
    for item in ingredients:
        if _is_staple(item):
            assumed.append(item)
        else:
            to_buy_flat.append(item)

    # Critical: main protein from dish name must be on to_buy AND in ingredients
    missing = _missing_main_protein(suggestion, to_buy_flat)
    if missing:
        to_buy_flat.insert(0, missing)
        if missing in assumed:
            assumed = [a for a in assumed if a != missing]
        miss_n = _norm_item(missing)
        if miss_n not in {_norm_item(x) for x in ingredients}:
            ingredients = [missing] + list(ingredients)

    # Re-validate: every ingredient in exactly one list
    all_listed = {_norm_item(x) for x in to_buy_flat + assumed}
    for item in ingredients:
        if _norm_item(item) not in all_listed:
            return None

    # Protein still missing after patch → fail hard
    if _missing_main_protein(suggestion, to_buy_flat):
        return None

    to_buy = _group_by_store(to_buy_flat)
    # Annotate skippable pantry with hint
    to_buy = _annotate_skippable(to_buy)

    return {
        "store": store,
        "ingredients": ingredients,
        "to_buy": to_buy,
        "assumed_at_home": assumed or ["salt", "peppar", "olja"],
        "recipe": _materialize_shopping_recipe(
            suggestion,
            ingredients,
            meal_type=str((meta or {}).get("meal_type") or "middag"),
        ),
    }


def _materialize_shopping_recipe(
    suggestion: str,
    ingredients: list[str],
    *,
    meal_type: str = "middag",
) -> dict[str, Any]:
    """Build recipe without re-entering build_shopping (avoids recursion)."""
    import recipe_engine as reng

    return reng.materialize_recipe(
        suggestion,
        ingredients,
        meal_type=meal_type,
        allow_llm=False,
    )


def shopping_valid(payload: dict[str, Any] | None, suggestion: str) -> bool:
    if not payload:
        return False
    to_buy_flat = [
        _strip_hint(i)
        for section in (payload.get("to_buy") or {}).values()
        for i in section
    ]
    return _missing_main_protein(suggestion, to_buy_flat) is None


def format_assumed_line(assumed: list[str], *, language: str = "sv") -> str:
    items = ", ".join(assumed) if assumed else "salt, peppar, olja"
    if language == "en":
        return f"Assumed at home: {items}."
    return f"Hemma antas: {items}."


def build_recipe(
    suggestion: str,
    ingredients: list[str] | None = None,
    *,
    active_minutes: int | None = None,
    servings: int | None = None,
    meal_type: str = "middag",
    language: str = "sv",
    grok_api_key: str = "",
) -> dict[str, Any]:
    """Delegate to structured recipe engine — never title-only stubs."""
    import recipe_engine as reng

    return reng.materialize_recipe(
        suggestion,
        list(ingredients) if ingredients else None,
        meal_type=meal_type,
        active_minutes=active_minutes,
        portions=servings,
        language=language,
        grok_api_key=grok_api_key,
        allow_llm=bool(grok_api_key),
    )


# Per 100 g (or per unit where noted): kcal, protein_g, fat_g, carbs_g
# Honest ballpark for ca-värden — never pretend lab precision.
_NUTRIENT_PER_100G: dict[str, tuple[float, float, float, float]] = {
    "kycklingfilé": (110, 23, 1.5, 0),
    "kyckling": (110, 23, 1.5, 0),
    "nötfärs": (250, 17, 20, 0),
    "köttfärs": (250, 17, 20, 0),
    "färs": (250, 17, 20, 0),
    "lax": (200, 20, 13, 0),
    "torsk": (80, 18, 0.5, 0),
    "bacon": (350, 15, 30, 1),
    "räkor": (90, 18, 1, 0),
    "ägg": (140, 12, 10, 1),  # per 100 g ≈ 2 eggs
    "mjölk": (45, 3.5, 1.5, 5),
    "grädde": (300, 2, 30, 3),
    "yoghurt": (60, 4, 3, 5),
    "fil": (60, 3.5, 3, 4),
    "ost": (350, 25, 28, 1),
    "parmesan": (400, 35, 28, 1),
    "smör": (720, 0.5, 80, 0.5),
    "olja": (900, 0, 100, 0),
    "pasta": (350, 12, 1.5, 70),
    "ris": (350, 7, 0.5, 78),
    "risnudlar": (350, 1, 0, 85),
    "bröd": (250, 8, 3, 45),
    "hamburgerbröd": (270, 9, 4, 48),
    "havregryn": (370, 13, 7, 60),
    "linser": (330, 24, 1.5, 50),
    "röda linser": (330, 24, 1.5, 50),
    "bönor": (120, 8, 0.5, 18),
    "kokosmjölk": (180, 1.5, 18, 3),
    "krossade tomater": (25, 1, 0.2, 4),
    "tomat": (20, 1, 0.2, 3),
    "gul lök": (40, 1, 0.1, 8),
    "lök": (40, 1, 0.1, 8),
    "vitlök": (140, 6, 0.5, 28),
    "morot": (40, 1, 0.2, 8),
    "broccoli": (35, 3, 0.4, 5),
    "paprika": (30, 1, 0.3, 5),
    "paprika (färsk)": (30, 1, 0.3, 5),
    "spenat": (25, 3, 0.4, 1),
    "sallad": (15, 1, 0.2, 2),
    "gurka": (15, 0.7, 0.1, 3),
    "avokado": (160, 2, 15, 7),
    "zucchini": (20, 1, 0.3, 3),
    "champinjon": (25, 3, 0.3, 2),
    "potatis": (80, 2, 0.1, 17),
    "banan": (90, 1, 0.3, 20),
    "äpple": (50, 0.3, 0.2, 12),
    "sojasås": (60, 8, 0, 6),
    "tonfisk": (110, 25, 1, 0),
    "skinka": (120, 20, 4, 1),
    "korv": (250, 12, 22, 2),
    "tortilla": (300, 8, 7, 50),
    "müsli": (370, 10, 6, 65),
    "sylt": (250, 0.3, 0.1, 60),
}

# Typical whole-recipe grams when the list is name-only (≈ 2 portions)
_DEFAULT_GRAMS: dict[str, float] = {
    "kycklingfilé": 400,
    "kyckling": 400,
    "nötfärs": 400,
    "köttfärs": 400,
    "färs": 400,
    "lax": 250,
    "torsk": 300,
    "bacon": 100,
    "räkor": 200,
    "ägg": 150,  # ~3 eggs
    "mjölk": 100,
    "grädde": 100,
    "yoghurt": 200,
    "fil": 200,
    "ost": 80,
    "parmesan": 30,
    "smör": 15,
    "olja": 15,
    "pasta": 200,
    "ris": 160,  # dry
    "risnudlar": 200,
    "bröd": 120,
    "hamburgerbröd": 160,
    "havregryn": 80,
    "linser": 160,
    "röda linser": 160,
    "bönor": 200,
    "kokosmjölk": 200,
    "krossade tomater": 400,
    "tomat": 150,
    "gul lök": 100,
    "lök": 100,
    "vitlök": 10,
    "morot": 100,
    "broccoli": 200,
    "paprika": 150,
    "paprika (färsk)": 150,
    "spenat": 80,
    "sallad": 50,
    "gurka": 100,
    "avokado": 150,
    "zucchini": 200,
    "champinjon": 150,
    "potatis": 400,
    "banan": 120,
    "äpple": 150,
    "sojasås": 30,
    "tonfisk": 150,
    "skinka": 80,
    "korv": 200,
    "tortilla": 120,
    "müsli": 60,
    "sylt": 30,
}


def _default_servings(suggestion: str, ingredients: list[str]) -> int:
    s = (suggestion or "").lower()
    # Single-serve no-cook / fridge snacks
    if any(w in s for w in ("äggröra", "äggmack", "yoghurt", "macka", "smörgås", "fil ")):
        return 1
    if len(ingredients) <= 4 and any(_norm_item(i) in ("ägg", "yoghurt", "fil") for i in ingredients):
        return 1
    return 2


def _match_nutrient_key(name: str) -> str | None:
    n = _norm_item(name)
    if n in _NUTRIENT_PER_100G:
        return n
    # Longest substring match among known keys
    best = None
    best_len = 0
    for key in _NUTRIENT_PER_100G:
        if key in n or n in key:
            if len(key) > best_len:
                best = key
                best_len = len(key)
    return best


def round_nutrition(kcal: float, protein_g: float, fat_g: float, carbs_g: float) -> dict[str, int]:
    """Aggressive rounding — false precision invites scrutiny."""
    return {
        "kcal": int(round(max(0, kcal) / 50.0) * 50),
        "protein_g": int(round(max(0, protein_g) / 5.0) * 5),
        "fat_g": int(round(max(0, fat_g) / 5.0) * 5),
        "carbs_g": int(round(max(0, carbs_g) / 5.0) * 5),
    }


def estimate_nutrition(
    ingredients: list[str],
    *,
    suggestion: str = "",
    servings: int = 2,
) -> dict[str, Any]:
    """Per-portion ca-värden from ingredient names + typical recipe amounts."""
    portions = max(1, int(servings or 2))
    tot_kcal = tot_p = tot_f = tot_c = 0.0
    for raw in ingredients or []:
        key = _match_nutrient_key(str(raw))
        if not key:
            continue
        per100 = _NUTRIENT_PER_100G[key]
        grams = float(_DEFAULT_GRAMS.get(key, 80))
        factor = grams / 100.0
        tot_kcal += per100[0] * factor
        tot_p += per100[1] * factor
        tot_f += per100[2] * factor
        tot_c += per100[3] * factor
    # Unknown / empty list → modest default so UI never invents zeros as truth
    if tot_kcal <= 0:
        rounded = round_nutrition(400, 20, 15, 40)
    else:
        rounded = round_nutrition(
            tot_kcal / portions,
            tot_p / portions,
            tot_f / portions,
            tot_c / portions,
        )
    return {
        **rounded,
        "per": "portion",
        "servings": portions,
        "kcal_per_portion": rounded["kcal"],
        "protein_g_per_portion": rounded["protein_g"],
        "portioner": portions,
        "label": "ca-värden",
        "suggestion": suggestion or "",
    }


def _as_nutrition_int(value: Any) -> int | None:
    """Coerce to int; reject bool/None/non-numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def nutrition_fields_valid(
    kcal: Any,
    protein: Any,
    portions: Any,
) -> bool:
    """True when portion nutrition fields are usable integers."""
    k = _as_nutrition_int(kcal)
    p = _as_nutrition_int(protein)
    n = _as_nutrition_int(portions)
    return k is not None and p is not None and n is not None and k > 0 and p >= 0 and n >= 1


def read_recipe_nutrition(
    recipe: dict[str, Any] | None,
) -> tuple[int | None, int | None, int | None]:
    """Read kcal/protein/portioner from top-level or nested nutrition (legacy)."""
    if not isinstance(recipe, dict):
        return None, None, None
    nut = recipe.get("nutrition") if isinstance(recipe.get("nutrition"), dict) else {}
    kcal = _as_nutrition_int(
        recipe.get("kcal_per_portion", nut.get("kcal_per_portion", nut.get("kcal")))
    )
    protein = _as_nutrition_int(
        recipe.get(
            "protein_g_per_portion",
            nut.get("protein_g_per_portion", nut.get("protein_g")),
        )
    )
    portions = _as_nutrition_int(
        recipe.get("portioner", nut.get("portioner", nut.get("servings")))
    )
    return kcal, protein, portions


def ensure_recipe_nutrition(
    recipe: dict[str, Any] | None,
    *,
    suggestion: str = "",
    allow_estimate: bool = True,
) -> dict[str, Any]:
    """Attach kcal_per_portion / protein_g_per_portion / portioner.

    Recipes are built by the static estimator (not LLM JSON). If fields are
    missing or non-numeric we re-estimate once from ingredients; old history
    payloads without nutrition stay safe (no raise).
    """
    out = dict(recipe or {})
    title = str(out.get("title") or suggestion or "")
    ings = [str(x) for x in (out.get("ingredients") or [])]
    kcal, protein, portions = read_recipe_nutrition(out)

    if not nutrition_fields_valid(kcal, protein, portions) and allow_estimate:
        # One re-estimate pass (mirrors the LLM "retry once" contract)
        seed_portions = portions if _as_nutrition_int(portions) and int(portions) >= 1 else None
        if seed_portions is None:
            seed_portions = _default_servings(title, ings)
        estimated = estimate_nutrition(
            ings,
            suggestion=title,
            servings=int(seed_portions),
        )
        kcal = estimated["kcal"]
        protein = estimated["protein_g"]
        portions = estimated["servings"]
        # Second pass only if still invalid (should not happen)
        if not nutrition_fields_valid(kcal, protein, portions):
            estimated = estimate_nutrition(
                ings or ["ägg", "bröd"],
                suggestion=title or "Måltid",
                servings=1,
            )
            kcal = estimated["kcal"]
            protein = estimated["protein_g"]
            portions = estimated["servings"]

    if nutrition_fields_valid(kcal, protein, portions):
        k_i, p_i, n_i = int(kcal), int(protein), int(portions)
        out["kcal_per_portion"] = k_i
        out["protein_g_per_portion"] = p_i
        out["portioner"] = n_i
        nested = dict(out.get("nutrition") or {}) if isinstance(out.get("nutrition"), dict) else {}
        nested.update(
            {
                "kcal": k_i,
                "protein_g": p_i,
                "servings": n_i,
                "kcal_per_portion": k_i,
                "protein_g_per_portion": p_i,
                "portioner": n_i,
                "per": "portion",
                "label": nested.get("label") or "ca-värden",
                "suggestion": nested.get("suggestion") or title,
            }
        )
        # Keep fat/carbs if already estimated
        if "fat_g" not in nested or "carbs_g" not in nested:
            est = estimate_nutrition(ings, suggestion=title, servings=n_i)
            nested.setdefault("fat_g", est.get("fat_g"))
            nested.setdefault("carbs_g", est.get("carbs_g"))
        out["nutrition"] = nested
    return out


def format_nutrition_line(
    nutrition: dict[str, Any] | None,
    *,
    language: str = "sv",
    recipe: dict[str, Any] | None = None,
) -> str:
    """UI line for the nutrition control — never empty, never None/null text.

    Prefer: \"≈ 520 kcal · 32 g protein / portion\"
    Missing: \"Näringsvärden saknas\" (secondary grey in UI).
    """
    kcal = protein = portions = None
    if isinstance(recipe, dict):
        kcal, protein, portions = read_recipe_nutrition(recipe)
    if not nutrition_fields_valid(kcal, protein, portions) and isinstance(nutrition, dict):
        kcal = _as_nutrition_int(
            nutrition.get("kcal_per_portion", nutrition.get("kcal"))
        )
        protein = _as_nutrition_int(
            nutrition.get("protein_g_per_portion", nutrition.get("protein_g"))
        )
        portions = _as_nutrition_int(
            nutrition.get("portioner", nutrition.get("servings", 1))
        )
    if not nutrition_fields_valid(kcal, protein, portions):
        return "Nutrition unavailable" if language == "en" else "Näringsvärden saknas"
    fat = _as_nutrition_int(
        recipe.get("fat_g_per_portion") if isinstance(recipe, dict) else None
    ) if isinstance(recipe, dict) else None
    carbs = _as_nutrition_int(
        recipe.get("carbs_g_per_portion") if isinstance(recipe, dict) else None
    ) if isinstance(recipe, dict) else None
    if isinstance(nutrition, dict):
        if fat is None:
            fat = _as_nutrition_int(nutrition.get("fat_g"))
        if carbs is None:
            carbs = _as_nutrition_int(nutrition.get("carbs_g"))
    if fat is None:
        fat = 0
    if carbs is None:
        carbs = 0
    if language == "en":
        return (
            f"Approx. {kcal} kcal · {protein} g protein · "
            f"{fat} g fat · {carbs} g carbs"
        )
    return (
        f"Ca {kcal} kcal · {protein} g protein · "
        f"{fat} g fett · {carbs} g kolh."
    )


def _recipe_steps(suggestion: str, ingredients: list[str]) -> list[str]:
    """Deterministic Swedish cook steps for known dishes (metric)."""
    s = (suggestion or "").lower()
    join = ", ".join(ingredients[:6])
    protein = _missing_main_protein(suggestion, [])  # canonical from name, if any
    # If protein already in ingredients, still resolve display name from aliases
    if protein is None:
        for canonical, cues in PROTEIN_ALIASES.items():
            if any(c in s for c in cues):
                protein = canonical
                break

    if "kycklingwok" in s or ("kyckling" in s and "wok" in s):
        return [
            "Skölj 2 dl ris och koka enligt förpackningen (ca 1,5 dl vatten per dl ris).",
            "Skär 400 g kycklingfilé i bitar. Strimla grönsakerna (lök, morot, broccoli, paprika).",
            "Hetta upp 1 msk olja i en wok. Stek kycklingen 5–6 min tills den är genomstekt.",
            "Tillsätt grönsakerna och stek 4–5 min. Krydda med 2 msk sojasås, salt och peppar.",
            "Servera woket över riset. Klart.",
        ]
    if "kyckling" in s or "chicken" in s:
        return [
            "Skölj 2 dl ris (eller annat tillbehör) och koka enligt förpackningen.",
            "Skär 400 g kycklingfilé i bitar. Hacka grönsakerna.",
            "Hetta upp 1 msk olja. Stek kycklingen 6–8 min tills den är genomstekt.",
            "Tillsätt grönsaker och kryddor. Stek/sjuda 5–8 min. Smaka av med salt och peppar.",
            "Servera kycklingen med tillbehöret. Klart.",
        ]
    if "pasta" in s or "tomatsås" in s:
        return [
            "Koka pasta enligt förpackningen i saltat vatten (ca 100 g per person).",
            "Fräs finhackad gul lök och 1 klyfta vitlök i 1 msk olja i 3 min.",
            "Häll i 400 g krossade tomater, låt sjuda 8–10 min. Krydda med oregano, salt och peppar.",
            "Rör ihop pastan med såsen. Toppa med riven parmesan.",
        ]
    if "lins" in s:
        return [
            "Skölj 2 dl ris och koka. Skölj 2 dl röda linser.",
            "Fräs lök, vitlök och morot i 1 msk olja i 4 min. Tillsätt curry.",
            "Häll i linser, 4 dl vatten och 2 dl kokosmjölk. Koka 15–18 min.",
            "Rör i spenat sista minuten. Smaka av med salt och peppar. Servera med ris.",
        ]
    if "havregrynsgröt" in s or ("havregryn" in s and "banan" in s):
        return [
            "Koka upp 2 dl vatten med 1 krm salt (ca 2 min).",
            "Rör ner 1 dl havregryn. Sjud på låg värme 3–4 min under omrörning.",
            "Skiva banan ovanpå gröten. Servera varm.",
        ]
    if "omelett" in s or "omelette" in s:
        return [
            "Vispa 3 ägg med 2 msk mjölk, salt och peppar.",
            "Hacka tomat och skölj spenat. Riv ost.",
            "Smält 1 tsk smör i en nonstick-panna. Häll i äggblandningen.",
            "När ytan börjar stelna: lägg på grönt och ost, vik ihop. Stek 1 min till. Servera.",
        ]
    if "smörgås" in s or "macka" in s or ("sandwich" in s and "egg" not in s):
        return [
            "Ta fram 2 skivor bröd och 2 skivor ost.",
            "Bred 1 tsk smör på brödet och lägg på osten.",
            "Servera direkt — eller grilla 1 min om du vill ha den varm.",
        ]
    if "äggröra" in s or "scrambled egg" in s:
        return [
            "Vispa 2 ägg med 1 krm salt och peppar i en skål.",
            "Smält 1 msk smör i stekpanna på medelvärme.",
            "Häll i äggen och rör långsamt 2–3 min tills röran är krämig. Servera direkt.",
        ]
    if "yoghurt" in s or s.startswith("fil ") or "fil eller" in s or "filmjölk" in s:
        if "müsli" in s or "musli" in s:
            return [
                "Häll 2 dl fil i en skål.",
                "Strö över 0,5 dl müsli.",
                "Servera direkt — ingen värme behövs (0 min).",
            ]
        return [
            "Häll 2 dl fil eller yoghurt i en skål.",
            "Toppa med frukt eller sylt om du vill.",
            "Servera direkt (0 min).",
        ]
    if "värm en rest" in s or "reheat leftover" in s:
        return [
            "Ta fram matlådan eller resterna från kylen.",
            "Värm i mikrougn 2–3 min (eller i panna) tills det är genomsvarmt.",
            "Smaka av. Klart.",
        ]
    if "burgare" in s or "burger" in s:
        return [
            "Blanda 400 g nötfärs med salt och peppar. Forma 2–4 biffar (ca 2 cm tjocka).",
            "Stek i 1 msk olja 3–4 min per sida. Lägg ost sista minuten om du vill.",
            "Rosta hamburgerbröden. Stapla: bröd, sallad, tomat, lök, biff.",
            "Servera direkt.",
        ]
    if "poke" in s or "poké" in s or ("lax" in s and "bowl" in s):
        return [
            "Koka 2 dl ris. Låt svalna något.",
            "Skär 250 g lax i tärningar. Skiva gurka och avokado.",
            "Blanda ris, lax och grönt. Ringla över 1 msk sojasås och 1 tsk sesamolja.",
            "Smaka av med salt och peppar. Servera kallt eller ljummet.",
        ]
    if "pad thai" in s or "padthai" in s:
        return [
            "Blögg 200 g risnudlar enligt förpackningen. Skär 300 g kycklingfilé i strimlor.",
            "Stek kycklingen i 1 msk olja 5–6 min. Skjut åt sidan, stek 2 ägg snabbt.",
            "Tillsätt nudlar, lök, vitlök, 2 msk sojasås och 1 msk fisksås. Rör om 3–4 min.",
            "Servera med limeklyftor. Smaka av med salt och peppar.",
        ]

    if protein:
        return [
            f"Förbered ingredienserna: {join}.",
            f"Tillaga proteinkällan ({protein}) tills den är genomstekt.",
            "Fräs lök/vitlök i 1 msk olja, tillsätt övrigt och låt sjuda 8–12 min.",
            "Smaka av med salt och peppar. Servera med tillbehöret.",
        ]

    return [
        f"Förbered ingredienserna: {join}.",
        "Fräs lök och vitlök i 1 msk olja i 3–4 minuter.",
        "Tillsätt huvudråvaran och övriga ingredienser. Tillaga tills allt är genomstekt (ca 10–15 min).",
        "Krydda med salt och peppar. Servera med tillbehöret (ris/pasta/bröd).",
    ]


def _norm_item(name: str) -> str:
    n = name.strip().lower()
    n = re.sub(r"\s+", " ", n)
    return n


def _strip_hint(name: str) -> str:
    # "ris — hoppa över om du har" → "ris"
    return _norm_item(re.split(r"\s*[—–-]\s*", name, maxsplit=1)[0])


def _is_staple(item: str) -> bool:
    n = _norm_item(item)
    # Fresh produce/meat never qualifies as a shelf staple
    if "färsk" in n or "fresh" in n:
        return False
    if n in ASSUMED_STAPLES:
        return True
    # "olja (rapsolja)" etc. — but not "paprika (färsk)" (handled above)
    base = n.split("(")[0].strip()
    return base in ASSUMED_STAPLES


def _missing_main_protein(suggestion: str, to_buy: list[str]) -> str | None:
    s = suggestion.lower()
    buy = " ".join(_strip_hint(x) for x in to_buy)
    for canonical, cues in PROTEIN_ALIASES.items():
        if any(c in s for c in cues):
            if not any(c in buy or canonical in buy for c in cues):
                return canonical
    return None


def _group_by_store(items: list[str]) -> dict[str, list[str]]:
    grouped = {k: [] for k in STORE_ORDER}
    for item in items:
        section = _section_for(item)
        if item not in grouped[section]:
            grouped[section].append(item)
    return {k: v for k, v in grouped.items() if v}


def _section_for(item: str) -> str:
    n = _strip_hint(item)
    meat = (
        "kyckling", "nöt", "färs", "fläsk", "bacon", "korv", "lax", "torsk",
        "räkor", "fisk", "kött", "karré", "kotlett",
    )
    dairy = (
        "mjölk", "grädde", "yoghurt", "ost", "parmesan", "ägg", "gräddfil",
        "creme", "crème", "smörgåsost",
    )
    # Note: smör is staple — shouldn't reach here often
    produce = (
        "lök", "vitlök", "tomat", "gurka", "avokado", "spenat", "sallad",
        "morot", "broccoli", "citron", "lime", "ingefära", "chili", "potatis",
        "zucchini", "aubergine", "svamp", "champinjon", "paprika", "frukt",
        "banan", "äpple", "grönt", "säsong",
    )
    frozen = ("fryst", "ärtor", "edamame")
    if any(m in n for m in meat):
        return "kött & fisk"
    if any(d in n for d in dairy):
        return "mejeri"
    if any(f in n for f in frozen):
        return "fryst"
    if any(p in n for p in produce):
        return "frukt & grönt"
    return "skafferi"


def _annotate_skippable(to_buy: dict[str, list[str]]) -> dict[str, list[str]]:
    """Pantry buys get a soft 'skip if you have' hint — never for fresh."""
    out: dict[str, list[str]] = {}
    for section, items in to_buy.items():
        lined = []
        for item in items:
            base = _strip_hint(item)
            if section == "skafferi" and any(p in base for p in PANTRY_BUY):
                if "hoppa över" not in item:
                    lined.append(f"{base} — hoppa över om du har")
                else:
                    lined.append(item)
            else:
                lined.append(base)
        out[section] = lined
    return out


def _infer_full_ingredients(suggestion: str) -> list[str]:
    """Complete ingredient list for known local dishes — never leave protein implied."""
    s = suggestion.lower()

    if (
        "kycklingwok" in s
        or ("kyckling" in s and "wok" in s)
        or ("chicken" in s and ("stir" in s or "wok" in s))
    ):
        return [
            "kycklingfilé",
            "gul lök",
            "vitlök",
            "morot",
            "broccoli",
            "paprika (färsk)",
            "ris",
            "sojasås",
            "olja",
            "salt",
            "peppar",
        ]
    if "pasta" in s or "tomatsås" in s or "tomato" in s:
        return [
            "pasta",
            "krossade tomater",
            "gul lök",
            "vitlök",
            "parmesan",
            "olja",
            "salt",
            "peppar",
            "oregano",
        ]
    if "lins" in s or "lentil" in s:
        return [
            "röda linser",
            "gul lök",
            "vitlök",
            "morot",
            "spenat",
            "kokosmjölk",
            "ris",
            "curry",
            "olja",
            "salt",
            "peppar",
        ]
    if "omelett" in s or "omelette" in s or ("ägg" in s and "protein" in s):
        return [
            "ägg",
            "mjölk",
            "tomat",
            "spenat",
            "ost",
            "smör",
            "salt",
            "peppar",
        ]
    if "smörgås" in s or "macka" in s or "sandwich" in s:
        ings = ["bröd", "smör"]
        if "ost" in s or "cheese" in s:
            ings.insert(1, "ost")
        elif "skinka" in s or "ham" in s:
            ings.insert(1, "skinka")
        else:
            ings.insert(1, "ost")
        return ings
    if "müsli" in s or "musli" in s:
        if "fil" in s or "filmjölk" in s:
            return ["fil", "müsli"]
    if "yoghurt" in s or "fil eller" in s or s.startswith("fil ") or "filmjölk" in s:
        if "müsli" in s or "musli" in s:
            return ["fil", "müsli"]
        if "fil" in s and "yoghurt" in s:
            return ["fil", "yoghurt", "honung"]
        return ["fil", "honung"]
    if "poke" in s or "poké" in s or ("lax" in s and "bowl" in s):
        return [
            "lax",
            "ris",
            "gurka",
            "avokado",
            "sojasås",
            "sesamolja",
            "salt",
            "peppar",
        ]
    if "burgare" in s or "burger" in s:
        return [
            "nötfärs",
            "hamburgerbröd",
            "ost",
            "sallad",
            "tomat",
            "gul lök",
            "olja",
            "salt",
            "peppar",
        ]
    if "pad thai" in s or "padthai" in s:
        return [
            "kycklingfilé",
            "risnudlar",
            "ägg",
            "gul lök",
            "vitlök",
            "sojasås",
            "fisksås",
            "lime",
            "olja",
            "salt",
            "peppar",
        ]

    # Generic cook: still require something concrete — fail soft with staples + veg + carb
    # If dish names a protein, include it
    ingredients = ["gul lök", "vitlök", "olja", "salt", "peppar"]
    for canonical, cues in PROTEIN_ALIASES.items():
        if any(c in s for c in cues):
            ingredients.insert(0, canonical)
            break
    else:
        # no protein detected — still need a main; use seasonal veg + carb to buy
        ingredients.extend(["säsongsgrönsaker", "ris"])
        return ingredients

    ingredients.extend(["säsongsgrönsaker", "ris"])
    return ingredients
