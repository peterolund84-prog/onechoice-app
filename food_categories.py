# -*- coding: utf-8 -*-
"""Dish category taxonomy + local image lookup for decision cards."""

from __future__ import annotations

import re
from pathlib import Path

# ~40 Swedish everyday-dish categories — filenames under assets/dishes/{id}.jpg
# "generic" is a taxonomy fallback id only (no photo; UI uses tonal placeholder).
DISH_CATEGORIES: tuple[str, ...] = (
    "wok",
    "gryta",
    "pasta",
    "omelett",
    "sallad",
    "soppa",
    "tacos",
    "pizza",
    "fisk",
    "kyckling",
    "gratang",
    "bowl",
    "smorgas",
    "grot",
    "pannkakor",
    "risotto",
    "curry",
    "burgare",
    "korv",
    "quesadilla",
    "sushi",
    "plocktallrik",
    "aggora",
    "yoghurt",
    "musli",
    "matlada",
    "lasagne",
    "nudlar",
    "wrap",
    "falafel",
    "potatis",
    "ugnsbakat",
    "linser",
    "chili",
    "padthai",
    "ramen",
    "poke",
    "quiche",
    "stek",
    "generic",
)

DISH_CATEGORY_SET = frozenset(DISH_CATEGORIES)

# Cue → category (longest cues first via sorted matching)
_CATEGORY_CUES: tuple[tuple[str, str], ...] = (
    ("pad thai", "padthai"),
    ("padthai", "padthai"),
    ("quesadilla", "quesadilla"),
    ("plocktallrik", "plocktallrik"),
    ("äggröra", "aggora"),
    ("aggrora", "aggora"),
    ("scramble", "aggora"),
    ("omelett", "omelett"),
    ("omelet", "omelett"),
    ("pannkaka", "pannkakor"),
    ("pancake", "pannkakor"),
    ("lasagne", "lasagne"),
    ("lasagna", "lasagne"),
    ("risotto", "risotto"),
    ("falafel", "falafel"),
    ("hummus", "falafel"),
    ("quesadilla", "quesadilla"),
    ("burrito", "wrap"),
    ("wrap", "wrap"),
    ("sushi", "sushi"),
    ("poke", "poke"),
    ("ramen", "ramen"),
    ("nudlar", "nudlar"),
    ("noodle", "nudlar"),
    ("ugnsbak", "ugnsbakat"),
    ("gratäng", "gratang"),
    ("gratang", "gratang"),
    ("gratin", "gratang"),
    ("matlåda", "matlada"),
    ("matlada", "matlada"),
    ("lunchbox", "matlada"),
    ("smörgås", "smorgas"),
    ("smorgas", "smorgas"),
    ("macka", "smorgas"),
    ("sandwich", "smorgas"),
    ("havregryn", "grot"),
    ("gröt", "grot"),
    ("grot", "grot"),
    ("porridge", "grot"),
    ("müsli", "musli"),
    ("musli", "musli"),
    ("yoghurt", "yoghurt"),
    ("fil med", "yoghurt"),
    ("burgare", "burgare"),
    ("burger", "burgare"),
    ("korv", "korv"),
    ("hotdog", "korv"),
    ("kycklingwok", "wok"),
    ("wok", "wok"),
    ("stir", "wok"),
    ("kyckling", "kyckling"),
    ("chicken", "kyckling"),
    ("lax", "fisk"),
    ("torsk", "fisk"),
    ("fisk", "fisk"),
    ("tuna", "fisk"),
    ("tonfisk", "fisk"),
    ("lins", "linser"),
    ("dal", "linser"),
    ("chili", "chili"),
    ("curry", "curry"),
    ("tikka", "curry"),
    ("pasta", "pasta"),
    ("spaghetti", "pasta"),
    ("penne", "pasta"),
    ("bolognese", "pasta"),
    ("pizza", "pizza"),
    ("taco", "tacos"),
    ("tacos", "tacos"),
    ("sallad", "sallad"),
    ("salad", "sallad"),
    ("soppa", "soppa"),
    ("soup", "soppa"),
    ("gryta", "gryta"),
    ("stew", "gryta"),
    ("gulasch", "gryta"),
    ("bowl", "bowl"),
    ("buddha", "bowl"),
    ("potatis", "potatis"),
    ("potato", "potatis"),
    ("quiche", "quiche"),
    ("paj", "quiche"),
    ("stek", "stek"),
    ("karré", "stek"),
    ("kotlett", "stek"),
)


def normalize_dish_category(raw: str | None) -> str:
    """Return a valid category id; unknown → generic."""
    if not raw:
        return "generic"
    key = re.sub(r"[^a-z0-9]", "", str(raw).strip().lower())
    # allow already-valid ids with underscores stripped
    for cat in DISH_CATEGORIES:
        if key == cat or key == cat.replace("å", "a").replace("ä", "a").replace("ö", "o"):
            return cat
    # accented aliases
    aliases = {
        "gratang": "gratang",
        "gratäng": "gratang",
        "smorgas": "smorgas",
        "smörgås": "smorgas",
        "grot": "grot",
        "gröt": "grot",
        "aggora": "aggora",
        "äggröra": "aggora",
        "musli": "musli",
        "müsli": "musli",
        "matlada": "matlada",
        "matlåda": "matlada",
    }
    low = str(raw).strip().lower()
    if low in aliases:
        return aliases[low]
    if low in DISH_CATEGORY_SET:
        return low
    return "generic"


def infer_dish_category(suggestion: str, *, meta: dict | None = None) -> str:
    """Pick category from meta.dish_category or suggestion cues."""
    meta = meta if isinstance(meta, dict) else {}
    s = (suggestion or "").lower()
    # Pulse identity beats stew/soup form words — "Etiopisk linsgryta" is
    # lentils, not beef stew (gryta.jpg). Same for linssoppa vs creamy soup.
    lentil_hit = any(
        cue in s for cue in ("lins", "lentil", "dal", "misir")
    )

    explicit = meta.get("dish_category") or meta.get("category")
    if explicit is not None and str(explicit).strip() != "":
        cat = normalize_dish_category(str(explicit))
        if lentil_hit and cat in ("gryta", "soppa", "generic"):
            return "linser"
        return cat

    # Dish-form words beat protein cues — "Sallad med tonfisk" is a salad, not fisk.jpg (salmon).
    if "sallad" in s or "salad" in s:
        return "sallad"
    if "smörgås" in s or "smorgas" in s or "macka" in s or "sandwich" in s:
        return "smorgas"
    if lentil_hit:
        return "linser"
    for cue, cat in sorted(_CATEGORY_CUES, key=lambda x: len(x[0]), reverse=True):
        if cue in s:
            return cat
    return "generic"


def dish_image_path(category: str, *, root: Path | None = None) -> Path:
    """Resolve local jpg path for a category id.

    Unknown / generic / missing file → path that is_file() is False.
    Callers must treat a missing file as “no photo” (tonal placeholder) —
    never invent a random fallback photo.
    """
    base = root or Path(__file__).resolve().parent / "assets" / "dishes"
    cat = normalize_dish_category(category)
    if cat == "generic" or cat not in DISH_CATEGORY_SET:
        return base / "__missing__.jpg"
    return base / f"{cat}.jpg"


def manifest_category_ids(*, root: Path | None = None) -> frozenset[str]:
    """Category ids that have a jpg on disk (excluding MANIFEST / generic)."""
    base = root or Path(__file__).resolve().parent / "assets" / "dishes"
    if not base.is_dir():
        return frozenset()
    return frozenset(
        p.stem
        for p in base.glob("*.jpg")
        if p.is_file() and p.stem in DISH_CATEGORY_SET and p.stem != "generic"
    )


def dish_image_bytes(category: str, *, root: Path | None = None) -> bytes | None:
    path = dish_image_path(category, root=root)
    try:
        if path.is_file():
            return path.read_bytes()
    except OSError:
        return None
    return None


def stamp_dish_category(candidate: dict) -> dict:
    """Ensure meta.dish_category is a valid taxonomy id (unknown → generic)."""
    row = dict(candidate)
    meta = dict(row.get("meta") or {}) if isinstance(row.get("meta"), dict) else {}
    meta["dish_category"] = infer_dish_category(
        str(row.get("suggestion") or ""), meta=meta
    )
    row["meta"] = meta
    return row


def stamp_dish_categories(candidates: list[dict]) -> list[dict]:
    return [stamp_dish_category(c) for c in candidates if isinstance(c, dict)]


def dish_category_prompt_list() -> str:
    """Comma-separated ids for LLM prompts (exclude generic as preferred pick)."""
    return ", ".join(c for c in DISH_CATEGORIES if c != "generic")
