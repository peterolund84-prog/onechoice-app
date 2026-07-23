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
    "tonfisk": ("tonfisk", "tuna"),
    "torsk": ("torsk", "cod"),
    "ägg": ("ägg", "omelett", "omelette"),
    "bacon": ("bacon",),
    "fläsk": ("fläsk", "karré", "kotlett"),
}


def _title_mentions(term: str, text: str) -> bool:
    """Word-boundary match — 'tonfisk' must not match cue 'fisk'."""
    return bool(re.search(rf"\b{re.escape(term)}\b", (text or "").lower()))


def _cue_in_title(cue: str, text: str) -> bool:
    """Match whole words or compound titles (kycklinggryta), not tonfisk→fisk."""
    s = (text or "").lower()
    c = cue.lower()
    if _title_mentions(c, s):
        return True
    return len(c) >= 5 and c in s


def _dish_protein(suggestion: str) -> str | None:
    s = (suggestion or "").lower()
    for canonical, cues in PROTEIN_ALIASES.items():
        if any(_cue_in_title(cue, s) for cue in cues):
            return canonical
    return None


def build_shopping(
    suggestion: str,
    *,
    meta: dict[str, Any] | None = None,
    store: str = "",
    recipe: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Return structured shopping payload or None if validation fails.

    Prefer recipe-first: when a structured recipe exists, derive to_buy from it
    (single source of truth for ingredients + amounts).
    """
    meta = meta or {}
    meal_type = str(meta.get("meal_type") or "middag")
    existing = recipe if isinstance(recipe, dict) else meta.get("recipe")
    if isinstance(existing, dict):
        shop = shopping_from_recipe(existing, suggestion=suggestion, store=store)
        if shop and shopping_valid(shop, suggestion):
            return shop

    hints = list(meta.get("ingredients") or []) or _infer_full_ingredients(suggestion)
    if hints:
        non_staple = [h for h in hints if not _is_staple(str(h))]
        missing = _missing_main_protein(suggestion, non_staple)
        if missing and _norm_item(missing) not in {_norm_item(str(h)) for h in hints}:
            hints = [missing] + hints
        try:
            built = _materialize_shopping_recipe(
                suggestion, hints, meal_type=meal_type
            )
            import recipe_engine as reng

            if reng.recipe_is_valid(built, suggestion):
                shop = shopping_from_recipe(built, suggestion=suggestion, store=store)
                if shop and shopping_valid(shop, suggestion):
                    return shop
        except Exception:
            pass

    return _build_shopping_from_names(suggestion, hints, store=store, meal_type=meal_type)


def _build_shopping_from_names(
    suggestion: str,
    full: list[str] | None,
    *,
    store: str = "",
    meal_type: str = "middag",
) -> dict[str, Any] | None:
    """Legacy name-list path — used when recipe materialization fails."""
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

    missing = _missing_main_protein(suggestion, to_buy_flat)
    if missing:
        to_buy_flat.insert(0, missing)
        if missing in assumed:
            assumed = [a for a in assumed if a != missing]
        miss_n = _norm_item(missing)
        if miss_n not in {_norm_item(x) for x in ingredients}:
            ingredients = [missing] + list(ingredients)

    all_listed = {_norm_item(x) for x in to_buy_flat + assumed}
    for item in ingredients:
        if _norm_item(item) not in all_listed:
            return None

    if _missing_main_protein(suggestion, to_buy_flat):
        return None

    to_buy = _annotate_skippable(_group_by_store(to_buy_flat))
    recipe = _materialize_shopping_recipe(
        suggestion, ingredients, meal_type=meal_type
    )

    return {
        "store": store,
        "ingredients": ingredients,
        "to_buy": to_buy,
        "assumed_at_home": assumed or ["salt", "peppar", "olja"],
        "recipe": recipe,
    }


def _names_from_recipe(recipe: dict[str, Any]) -> list[str]:
    """Plain ingredient names from a structured recipe."""
    structured = recipe.get("ingredients_structured")
    if isinstance(structured, list) and structured:
        names: list[str] = []
        for ing in structured:
            if isinstance(ing, dict):
                n = _norm_item(str(ing.get("name") or ""))
                if n:
                    names.append(n)
        if names:
            return names
    lines = list(recipe.get("ingredient_lines") or recipe.get("ingredients") or [])
    out: list[str] = []
    for line in lines:
        raw = str(line).strip()
        if not raw:
            continue
        out.append(_strip_hint(raw))
    return out


def shopping_from_recipe(
    recipe: dict[str, Any],
    *,
    suggestion: str = "",
    store: str = "",
) -> dict[str, Any] | None:
    """
    Smart shopping list: split recipe ingredients into to_buy vs assumed_at_home.
    Respects ingredients_structured category when present.
    """
    if not isinstance(recipe, dict):
        return None
    title = suggestion or str(recipe.get("title") or "")
    structured = recipe.get("ingredients_structured")
    to_buy_flat: list[str] = []
    assumed: list[str] = []
    all_names: list[str] = []

    if isinstance(structured, list) and structured and isinstance(structured[0], dict):
        for ing in structured:
            if not isinstance(ing, dict):
                continue
            name = _norm_item(str(ing.get("name") or ""))
            if not name:
                continue
            all_names.append(name)
            cat = str(ing.get("category") or "").lower()
            if cat == "assumed_home" or _is_staple(name):
                if name not in assumed:
                    assumed.append(name)
            elif name not in to_buy_flat:
                to_buy_flat.append(name)
    else:
        for name in _names_from_recipe(recipe):
            if not name or name in all_names:
                continue
            all_names.append(name)
            if _is_staple(name):
                assumed.append(name)
            else:
                to_buy_flat.append(name)

    missing = _missing_main_protein(title, to_buy_flat)
    if missing:
        to_buy_flat.insert(0, missing)
        if _norm_item(missing) not in {_norm_item(x) for x in all_names}:
            all_names.insert(0, missing)

    if not all_names:
        return None

    to_buy = _annotate_skippable(_group_by_store(to_buy_flat))

    return {
        "store": store,
        "ingredients": all_names,
        "to_buy": to_buy,
        "assumed_at_home": assumed or ["salt", "peppar", "olja"],
        "recipe": recipe,
    }


def build_meal_bundle(
    suggestion: str,
    *,
    meta: dict[str, Any] | None = None,
    meal_type: str = "middag",
    store: str = "",
    language: str = "sv",
    grok_api_key: str = "",
    include_shopping: bool = True,
    active_minutes: int | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """
    Recipe first, shopping derived from recipe — one pipeline for execute/decide.
    Returns (recipe, shopping_payload).
    """
    import recipe_engine as reng

    meta = dict(meta or {})
    meta.setdefault("meal_type", meal_type)
    hints = [str(x).strip() for x in (meta.get("ingredients") or []) if str(x).strip()]
    existing = meta.get("recipe") if isinstance(meta.get("recipe"), dict) else None

    recipe: dict[str, Any] | None = None
    if existing and reng.recipe_is_valid(existing, suggestion):
        recipe = dict(existing)
    else:
        try:
            recipe = reng.materialize_recipe(
                suggestion,
                hints or None,
                meal_type=meal_type,
                active_minutes=active_minutes or meta.get("active_minutes"),
                language=language,
                grok_api_key=grok_api_key,
                allow_llm=bool(grok_api_key),
            )
        except Exception:
            recipe = None

    if not recipe or not reng.recipe_is_valid(recipe, suggestion):
        return None, None

    shop = None
    if include_shopping:
        shop = shopping_from_recipe(recipe, suggestion=suggestion, store=store)
        if shop and not shopping_valid(shop, suggestion):
            shop = None
    return recipe, shop


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


def nutrition_segment_visible(
    recipe: dict[str, Any] | None,
    nutrition: dict[str, Any] | None = None,
) -> bool:
    """True when we have honest per-portion nutrition to show (never all-zero stubs)."""
    if not isinstance(recipe, dict):
        return False
    if recipe.get("no_recipe") or recipe.get("leftover"):
        nut = recipe.get("nutrition") if isinstance(recipe.get("nutrition"), dict) else {}
        kcal = _as_nutrition_int(nut.get("kcal"))
        protein = _as_nutrition_int(nut.get("protein_g"))
        fat = _as_nutrition_int(nut.get("fat_g"))
        carbs = _as_nutrition_int(nut.get("carbs_g"))
        if not any(x and x > 0 for x in (kcal, protein, fat, carbs)):
            return False
    kcal, protein, portions = read_recipe_nutrition(recipe)
    if not nutrition_fields_valid(kcal, protein, portions):
        return False
    nut = nutrition if isinstance(nutrition, dict) else {}
    if not nut and isinstance(recipe.get("nutrition"), dict):
        nut = recipe["nutrition"]
    fat = _as_nutrition_int(
        recipe.get("fat_g_per_portion", nut.get("fat_g"))
    )
    carbs = _as_nutrition_int(
        recipe.get("carbs_g_per_portion", nut.get("carbs_g"))
    )
    if fat == 0 and carbs == 0 and _as_nutrition_int(kcal) == 0:
        return False
    return True


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
        # Guard: LLM/history sometimes stores whole-pot kcal as kcal_per_portion
        if n_i > 1 and k_i >= 900:
            k_i = int(round(k_i / n_i / 50.0) * 50)
            p_i = int(round(p_i / n_i / 5.0) * 5)
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
    if not nutrition_segment_visible(recipe, nutrition):
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
    if language == "en":
        parts = [f"Approx. {kcal} kcal per serving", f"{protein} g protein"]
        if fat and fat > 0:
            parts.append(f"{fat} g fat")
        if carbs and carbs > 0:
            parts.append(f"{carbs} g carbs")
        return " · ".join(parts)
    parts = [f"Ca {kcal} kcal per portion", f"{protein} g protein"]
    if fat and fat > 0:
        parts.append(f"{fat} g fett")
    if carbs and carbs > 0:
        parts.append(f"{carbs} g kolh.")
    return " · ".join(parts)


def _hint_tokens(ingredients: list[str]) -> list[str]:
    """Bare ingredient names for coverage (skip empty)."""
    out: list[str] = []
    for raw in ingredients:
        n = _strip_hint(str(raw or ""))
        if n and n not in out:
            out.append(n)
    return out


def _ing_blob(ingredients: list[str]) -> str:
    return " ".join(_hint_tokens(ingredients)).lower()


def _hint_grounded_steps(suggestion: str, ingredients: list[str]) -> list[str]:
    """Per-category step skeleton built from the actual hint list.

    Replaces the old protein+ris / 'Förbered ingredienserna' prose that passed
    surface validation while contradicting the dish. Every non-pantry hint is
    named in the steps (coverage); quantified foods only appear if listed.
    """
    s = (suggestion or "").lower()
    names = _hint_tokens(ingredients)
    blob = " ".join(names)
    pantry = {"salt", "peppar", "olja", "smör", "vatten", "svartpeppar"}
    mains = [n for n in names if n not in pantry]
    join = ", ".join(mains[:8]) if mains else (", ".join(names[:6]) or "ingredienserna")
    has = lambda *cues: any(c in blob or c in s for c in cues)

    if has("taco", "tacoskal") or "taco" in s:
        return [
            f"Stek färs (eller annan fyllning) i 1 msk olja 6–8 min. Krydda med salt och peppar.",
            f"Hacka tillbehör: {join}.",
            "Värm tacoskal enligt förpackningen.",
            f"Fyll skalen med färs och {join}. Servera med gräddfil om du har.",
        ]
    if has("nudlar", "ramen", "pad thai") or any(x in s for x in ("ramen", "nudel", "noodle")):
        return [
            f"Koka nudlar enligt förpackningen. Skölj övrigt: {join}.",
            "Hetta upp 1 msk olja. Fräs vitlök (och ingefära om du har) 1 min.",
            f"Tillsätt grönsaker och protein från listan ({join}). Stek 4–6 min.",
            "Rör ner nudlarna med 2 msk sojasås. Smaka av med salt och peppar. Servera.",
        ]
    if has("quinoa") or "quinoa" in s or ("sallad" in s and not has("tonfisk", "tuna")):
        return [
            f"Koka quinoa eller skölj basen. Skär grönt: {join}.",
            f"Blanda allt i en skål: {join}.",
            "Ringla 1 msk olja och pressa citron om du har. Krydda med salt och peppar.",
            "Servera kallt eller ljummet.",
        ]
    if has("soppa", "buljong") or "soppa" in s or "soup" in s:
        return [
            f"Hacka grönsakerna: {join}.",
            "Fräs lök i 1 msk olja 3 min. Tillsätt övrigt och 8 dl buljong eller vatten.",
            "Koka 12–15 min tills grönsakerna är mjuka. Smaka av med salt och peppar.",
            "Servera varm soppa.",
        ]
    if has("korv") or "korv" in s or "sausage" in s:
        return [
            "Stek korvarna i 1 msk olja eller smör 8–10 min tills genomstekta.",
            f"Koka potatis mjuk (ca 15 min). Mosa med mjölk och smör. Krydda med salt och peppar.",
            f"Servera korv med mos och eventuellt övrigt ({join}).",
        ]
    if has("köttbull", "nötfärs") and ("köttbull" in s or "meatball" in s or "gräddsås" in s):
        return [
            "Blanda nötfärs med ägg, ströbröd, salt och peppar. Forma köttbullar.",
            "Bryn i 1 msk smör 8–10 min tills genomstekta.",
            "Häll i grädde, låt sjuda 5 min till en gräddsås. Smaka av.",
            f"Servera med tillbehören: {join}.",
        ]
    if has("lax", "torsk", "fisk") or any(x in s for x in ("lax", "salmon", "fisk", "fish", "torsk")):
        return [
            f"Sätt ugnen på 200°. Skär potatis/grönt: {join}.",
            "Lägg fisken i en form med smör, citron och dill om du har. Salta och peppra.",
            "Ugnbaka 12–18 min tills fisken är genomstekt och grönsakerna mjuka.",
            f"Servera fisken med {join}.",
        ]
    if has("kikärt") or "curry" in s or "kikärt" in s:
        return [
            f"Fräs lök och vitlök i 1 msk olja 3 min. Tillsätt kryddor.",
            f"Häll i kikärtor, tomatpuré/kokosmjölk och övrigt: {join}. Sjud 12–15 min.",
            "Koka ris enligt förpackningen om ris finns i listan.",
            "Smaka av med salt och peppar. Servera varmt.",
        ]
    if has("avokado") and has("bröd") or "toast" in s or "avokado" in s:
        return [
            "Rosta brödet 1–2 min.",
            "Krossa avokado med citron, salt och peppar.",
            f"Bred avokadon på brödet. Toppa med övrigt om du har ({join}). Servera direkt.",
        ]
    if (has("ris") and has("ägg")) or ("ris" in s and "ägg" in s) or ("rice" in s and "egg" in s):
        return [
            "Koka 2 dl ris enligt förpackningen (ca 12 min).",
            "Stek 2 ägg i 1 msk olja 3–4 min. Krydda med salt och peppar.",
            f"Fräs grönt ({join}) 2–3 min. Ringla sojasås om du har.",
            "Servera riset med stekt ägg och grönt.",
        ]
    if has("pesto") or "pesto" in s:
        return [
            "Koka pasta enligt förpackningen i saltat vatten.",
            f"Häll av pastan. Rör ner pesto och övrigt: {join}.",
            "Smaka av med salt och peppar. Servera direkt.",
        ]
    if "carbonara" in s:
        return [
            "Koka spaghetti enligt förpackningen. Spara 1 dl pastavatten.",
            "Stek bacon knaprigt. Vispa ägg med parmesan och svartpeppar.",
            "Rör ihop het pasta, bacon och äggblandning av plattan (sås ska inte bli äggröra).",
            "Smaka av med salt och peppar. Servera genast.",
        ]
    if "lasagne" in s or "lasagna" in s:
        return [
            f"Fräs gul lök, vitlök och grönsaker ({join}) i 1 msk olja. Tillsätt krossade tomater, sjud 10 min.",
            "Varva lasagneplattor, sås och ost i en form.",
            "Gratinera i ugn 200° i 25–30 min. Vila 5 min. Servera.",
        ]
    if has("grädde") and has("kyckling") or ("gryta" in s and has("kyckling", "chicken")):
        return [
            "Skär kycklingfilé i bitar. Fräs i 1 msk olja 5–6 min.",
            f"Tillsätt lök och övrigt: {join}. Häll i grädde och sjud 10–12 min.",
            "Smaka av med salt och peppar. Servera varmt (med ris endast om ris finns i listan).",
        ]

    # Generic but dish-aware: name every main ingredient, no invented sides
    return [
        f"Skölj och skär det som behövs: {join}.",
        f"Hetta upp 1 msk olja i en panna eller gryta. Tillaga huvudråvarorna 6–10 min.",
        f"Tillsätt resten ({join}). Låt sjuda eller steka 5–8 min. Smaka av med salt och peppar.",
        "Servera varmt. Klart.",
    ]


def _recipe_steps(suggestion: str, ingredients: list[str]) -> list[str]:
    """Deterministic Swedish cook steps for known dishes (metric)."""
    s = (suggestion or "").lower()
    names = _hint_tokens(ingredients)
    pantry = {"salt", "peppar", "olja", "smör", "vatten", "svartpeppar"}
    mains = [n for n in names if n not in pantry]
    join = ", ".join(mains[:10]) if mains else ", ".join(names[:8])
    blob = " ".join(names)
    protein = _missing_main_protein(suggestion, [])  # canonical from name, if any
    # If protein already in ingredients, still resolve display name from aliases
    if protein is None:
        protein = _dish_protein(suggestion)

    if ("tonfisk" in s or "tuna" in s) and "sallad" in s:
        return [
            "Skölj och strimla sallad (ca 4 dl). Skär 1 gurka i kuber.",
            "Öppna 1 burk tonfisk i vatten och låt rinna av.",
            "Blanda sallad, gurka och tonfisk i en skål. Ringla 1 msk olja.",
            "Krydda med salt och peppar. Servera direkt.",
        ]
    if "äggmacka" in s or ("egg" in s and "sandwich" in s):
        return [
            "Stek 2 ägg i 1 msk smör till önskad konsistens (ca 4 min).",
            "Rosta 2 skivor bröd i brödrost eller torr panna (1 min).",
            "Lägg äggen på brödet. Smaka av med salt och peppar. Servera med kaffe.",
        ]
    if (
        "kycklingwok" in s
        or ("kyckling" in s and "wok" in s)
        or ("chicken" in s and "wok" in s)
        or ("chicken" in s and "stir" in s)
    ):
        veg = join or "lök, morot, broccoli, paprika"
        return [
            "Skölj 2 dl ris och koka enligt förpackningen (ca 1,5 dl vatten per dl ris).",
            f"Skär 400 g kycklingfilé i bitar. Strimla grönsakerna ({veg}).",
            "Hetta upp 1 msk olja i en wok. Stek kycklingen 5–6 min tills den är genomstekt.",
            "Tillsätt grönsakerna och stek 4–5 min. Krydda med 2 msk sojasås, salt och peppar.",
            "Servera woket över riset. Klart.",
        ]
    # Wrap / tortilla BEFORE generic kyckling (else protein+ris template leaks in)
    if "wrap" in s or "tortilla" in s or "burrito" in s or "quesadilla" in s:
        return [
            "Värm 2 tortilla i torr panna 20 sek per sida (eller 15 sek i mikro).",
            "Skär 200 g kycklingfilé i strimlor. Stek i 1 msk olja 5–6 min tills genomstekt. Krydda med salt och peppar.",
            "Strimla sallad och skär tomat i klyftor.",
            "Fördela kyckling, sallad och tomat på tortillan. Ringla 2 msk yoghurt ovanpå.",
            "Rulla ihop wrapen tätt. Servera direkt.",
        ]
    if "pesto" in s:
        return [
            "Koka pasta enligt förpackningen i saltat vatten (ca 100 g per person).",
            f"Häll av pastan. Rör ner pesto och övrigt: {join}.",
            "Smaka av med salt och peppar. Toppa med riven parmesan om du har. Servera.",
        ]
    if "carbonara" in s:
        return [
            "Koka spaghetti enligt förpackningen. Spara 1 dl pastavatten.",
            f"Stek bacon knaprigt. Vispa ägg med parmesan och svartpeppar. (Ingredienser: {join})",
            "Rör ihop het pasta, bacon och äggblandning av plattan. Späd med pastavatten.",
            "Smaka av med salt och peppar. Servera genast.",
        ]
    if "lasagne" in s or "lasagna" in s:
        return [
            f"Fräs gul lök, vitlök och grönsaker. Tillsätt krossade tomater, sjud 10 min. ({join})",
            f"Gör en snabb béchamel av smör, mjöl och mjölk om du har. Varva lasagneplattor, sås och ost ({join}).",
            "Gratinera i ugn 200° i 25–30 min. Vila 5 min. Servera.",
        ]
    if "pasta" in s or "tomatsås" in s or "spaghetti" in s:
        return [
            "Koka pasta enligt förpackningen i saltat vatten (ca 100 g per person).",
            f"Fräs finhackad gul lök och vitlök i 1 msk olja i 3 min. ({join})",
            "Häll i 400 g krossade tomater, låt sjuda 8–10 min. Krydda med oregano, salt och peppar.",
            "Rör ihop pastan med såsen. Toppa med riven parmesan.",
        ]
    if "lins" in s or "lentil" in s:
        return [
            f"Skölj 2 dl ris och koka. Skölj 2 dl röda linser. Övrigt: {join}.",
            "Fräs lök, vitlök och morot i 1 msk olja i 4 min. Tillsätt curry.",
            "Häll i linser, 4 dl vatten och 2 dl kokosmjölk. Koka 15–18 min.",
            "Rör i spenat sista minuten. Smaka av med salt och peppar. Servera med ris.",
        ]
    if "havregrynsgröt" in s or ("havregryn" in s and "banan" in s) or "oatmeal" in s:
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
        if "müsli" in s or "musli" in s or "muesli" in s:
            return [
                f"Häll 2 dl fil i en skål. ({join})",
                "Strö över 0,5 dl müsli.",
                "Servera direkt — ingen värme behövs (0 min).",
            ]
        return [
            f"Häll 2 dl fil eller yoghurt i en skål. ({join})",
            "Toppa med frukt, sylt eller honung om du har.",
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
    # Chicken with rice only when ris is actually in the dish/hints
    if "kyckling" in s or "chicken" in s:
        if "ris" in s or "ris" in blob or "rice" in s:
            return [
                "Skölj 2 dl ris och koka enligt förpackningen.",
                "Skär 400 g kycklingfilé i bitar. Hacka grönsakerna.",
                "Hetta upp 1 msk olja. Stek kycklingen 6–8 min tills den är genomstekt.",
                f"Tillsätt grönsaker ({join}). Stek/sjuda 5–8 min. Smaka av med salt och peppar.",
                "Servera kycklingen med riset. Klart.",
            ]
        return _hint_grounded_steps(suggestion, ingredients)

    # Everything else: category skeleton from the real hint list
    return _hint_grounded_steps(suggestion, ingredients)

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
        if any(_cue_in_title(cue, s) for cue in cues):
            if not any(_cue_in_title(cue, buy) or canonical in buy for cue in cues):
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

    if "kycklingwok" in s or ("kyckling" in s and "wok" in s) or (
        "chicken" in s and ("stir" in s or "wok" in s)
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
    if "wrap" in s or "tortilla" in s or "burrito" in s:
        return [
            "tortilla",
            "kycklingfilé",
            "sallad",
            "tomat",
            "yoghurt",
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
    if "tonfisk" in s or ("tuna" in s and "salad" in s):
        return ["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"]
    if "äggmacka" in s or ("egg" in s and "sandwich" in s):
        return ["ägg", "bröd", "smör", "salt", "peppar"]
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
    protein = _dish_protein(suggestion)
    if protein:
        ingredients.insert(0, protein)
    else:
        # no protein detected — still need a main; use seasonal veg + carb to buy
        ingredients.extend(["säsongsgrönsaker", "ris"])
        return ingredients

    ingredients.extend(["säsongsgrönsaker", "ris"])
    return ingredients
