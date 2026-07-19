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
        "recipe": build_recipe(suggestion, ingredients),
    }


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
) -> dict[str, Any]:
    """Swedish metric recipe: full ingredient list + ordered steps.

    active_minutes is the single source of truth for cook time when provided.
    """
    ings = list(ingredients or _infer_full_ingredients(suggestion) or [])
    if not ings:
        ings = ["gul lök", "vitlök", "olja", "salt", "peppar", "säsongsgrönsaker", "ris"]
    # Dish-name protein must appear in the recipe ingredient list
    missing = _missing_main_protein(suggestion, ings)
    if missing:
        miss_n = _norm_item(missing)
        ings = [missing] + [i for i in ings if _norm_item(i) != miss_n]
    steps = _recipe_steps(suggestion, ings)
    out: dict[str, Any] = {
        "title": suggestion,
        "ingredients": ings,
        "steps": steps,
        "unit_system": "metric",
        "language": "sv",
    }
    if active_minutes is not None:
        out["active_minutes"] = int(active_minutes)
    return out


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
    if "omelett" in s or "omelette" in s:
        return [
            "Vispa 3 ägg med 2 msk mjölk, salt och peppar.",
            "Hacka tomat och skölj spenat. Riv ost.",
            "Smält 1 tsk smör i en nonstick-panna. Häll i äggblandningen.",
            "När ytan börjar stelna: lägg på grönt och ost, vik ihop. Stek 1 min till. Servera.",
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
