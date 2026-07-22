# -*- coding: utf-8 -*-
"""Deterministic dish-image resolver — title keywords beat LLM category hints.

The model cannot know which files exist on disk. Unmatched categories used to
fall through to generic.jpg (a cooking-scene photo), which made named dishes
look broken. This module maps titles → existing files only; no match → None
(caller renders a tonal placeholder).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

log = logging.getLogger("onechoice.dish_images")

DISHES_DIR = Path(__file__).resolve().parent / "assets" / "dishes"

# Keyword → filename. Matched longest-first on normalized titles.
# Keep specific classics above generic form words (carbonara > pasta).
KEYWORD_FILES: dict[str, str] = {
    # Classics / specific
    "carbonara": "pasta_gradde.jpg",
    "pasta pesto": "pasta_pesto.jpg",
    "pesto pasta": "pasta_pesto.jpg",
    "pesto": "pasta_pesto.jpg",
    "tomatsas-pasta": "pasta.jpg",
    "tomatsaspasta": "pasta.jpg",
    "tomato pasta": "pasta.jpg",
    "kramig tomatsas": "pasta.jpg",
    "creamy tomato": "pasta.jpg",
    "bolognese": "pasta.jpg",
    "lasagne": "lasagne.jpg",
    "lasagna": "lasagne.jpg",
    "pad thai": "padthai.jpg",
    "padthai": "padthai.jpg",
    "kottbullar": "kottbullar.jpg",
    "meatballs": "kottbullar.jpg",
    "linsgryta": "linser.jpg",
    "linssoppa": "linser.jpg",
    "lentil stew": "linser.jpg",
    "lentil": "linser.jpg",
    "lins": "linser.jpg",
    "misir": "linser.jpg",
    "dal": "linser.jpg",
    # Named dishes / strong cues
    "tacos": "tacos.jpg",
    "taco": "tacos.jpg",
    "quesadilla": "quesadilla.jpg",
    "burrito": "wrap.jpg",
    "kycklingwok": "wok.jpg",
    "nudelwok": "wok.jpg",
    "noodle wok": "wok.jpg",
    "vegetable noodle": "wok.jpg",
    "wok": "wok.jpg",
    "stir fry": "wok.jpg",
    "stir-fry": "wok.jpg",
    "ramen": "ramen.jpg",
    "poke": "poke.jpg",
    "sushi": "sushi.jpg",
    "falafel": "falafel.jpg",
    "hummus": "falafel.jpg",
    "risotto": "risotto.jpg",
    "chili": "chili.jpg",
    "curry": "curry.jpg",
    "tikka": "curry.jpg",
    "kikaritscurry": "curry.jpg",
    "chickpea curry": "curry.jpg",
    "pizza": "pizza.jpg",
    "quiche": "quiche.jpg",
    "omelett": "omelett.jpg",
    "omelette": "omelett.jpg",
    "proteinomelett": "omelett.jpg",
    "aggrora": "aggora.jpg",
    "scramble": "aggora.jpg",
    "stekt agg": "aggora.jpg",
    "fried egg": "aggora.jpg",
    "pannkaka": "pannkakor.jpg",
    "pancake": "pannkakor.jpg",
    "havregryn": "grot.jpg",
    "oatmeal": "grot.jpg",
    "porridge": "grot.jpg",
    "grot": "grot.jpg",
    "musli": "musli.jpg",
    "muesli": "musli.jpg",
    "yoghurt": "yoghurt.jpg",
    "filmjolk": "yoghurt.jpg",
    "fil med": "yoghurt.jpg",
    "fil eller": "yoghurt.jpg",
    "burgare": "burgare.jpg",
    "burger": "burgare.jpg",
    "halloumi": "burgare.jpg",
    "korv": "korv.jpg",
    "sausage": "korv.jpg",
    "hotdog": "korv.jpg",
    "hot dog": "korv.jpg",
    "fiskgratang": "gratang.jpg",
    "fish gratin": "gratang.jpg",
    "gratang": "gratang.jpg",
    "gratin": "gratang.jpg",
    "ugnsbakad lax": "fisk.jpg",
    "oven-baked salmon": "fisk.jpg",
    "salmon": "fisk.jpg",
    "lax": "fisk.jpg",
    "torsk": "fisk.jpg",
    "fisk": "fisk.jpg",
    "fish": "fisk.jpg",
    "kycklinggryta": "gryta.jpg",
    "creamy chicken stew": "gryta.jpg",
    "chicken stew": "gryta.jpg",
    "gryta": "gryta.jpg",
    "stew": "gryta.jpg",
    "gulasch": "gryta.jpg",
    "wrap med kyckling": "wrap.jpg",
    "chicken wrap": "wrap.jpg",
    "kyckling": "kyckling.jpg",
    "chicken": "kyckling.jpg",
    "wrap": "wrap.jpg",
    "tortilla": "wrap.jpg",
    "smorgas": "smorgas.jpg",
    "sandwich": "smorgas.jpg",
    "macka": "smorgas.jpg",
    "toast": "smorgas.jpg",
    "aggmacka": "smorgas.jpg",
    "egg sandwich": "smorgas.jpg",
    "knacke": "smorgas.jpg",
    "crispbread": "smorgas.jpg",
    "avokado": "smorgas.jpg",
    "avocado": "smorgas.jpg",
    "quinoasallad": "sallad.jpg",
    "quinoa salad": "sallad.jpg",
    "kikartssallad": "sallad.jpg",
    "chickpea salad": "sallad.jpg",
    "sallad": "sallad.jpg",
    "salad": "sallad.jpg",
    "soppa": "soppa.jpg",
    "soup": "soppa.jpg",
    "nudlar": "nudlar.jpg",
    "noodle": "nudlar.jpg",
    "noodles": "nudlar.jpg",
    "spaghetti": "pasta.jpg",
    "penne": "pasta.jpg",
    "pasta": "pasta.jpg",
    "matlada": "matlada.jpg",
    "lunchbox": "matlada.jpg",
    "potatis": "potatis.jpg",
    "potato": "potatis.jpg",
    "mash": "potatis.jpg",
    "ugnsbak": "ugnsbakat.jpg",
    "bowl": "bowl.jpg",
    "buddha": "bowl.jpg",
    "plocktallrik": "plocktallrik.jpg",
    "stek": "stek.jpg",
    "steak": "stek.jpg",
    "kotlett": "stek.jpg",
}

# Category hint → file when no keyword hits (must exist on disk).
CATEGORY_FILES: dict[str, str] = {
    "wok": "wok.jpg",
    "gryta": "gryta.jpg",
    "pasta": "pasta.jpg",
    "omelett": "omelett.jpg",
    "sallad": "sallad.jpg",
    "soppa": "soppa.jpg",
    "tacos": "tacos.jpg",
    "pizza": "pizza.jpg",
    "fisk": "fisk.jpg",
    "kyckling": "kyckling.jpg",
    "gratang": "gratang.jpg",
    "bowl": "bowl.jpg",
    "smorgas": "smorgas.jpg",
    "grot": "grot.jpg",
    "pannkakor": "pannkakor.jpg",
    "risotto": "risotto.jpg",
    "curry": "curry.jpg",
    "burgare": "burgare.jpg",
    "korv": "korv.jpg",
    "quesadilla": "quesadilla.jpg",
    "sushi": "sushi.jpg",
    "plocktallrik": "plocktallrik.jpg",
    "aggora": "aggora.jpg",
    "yoghurt": "yoghurt.jpg",
    "musli": "musli.jpg",
    "matlada": "matlada.jpg",
    "lasagne": "lasagne.jpg",
    "nudlar": "nudlar.jpg",
    "wrap": "wrap.jpg",
    "falafel": "falafel.jpg",
    "potatis": "potatis.jpg",
    "ugnsbakat": "ugnsbakat.jpg",
    "linser": "linser.jpg",
    "chili": "chili.jpg",
    "padthai": "padthai.jpg",
    "ramen": "ramen.jpg",
    "poke": "poke.jpg",
    "quiche": "quiche.jpg",
    "stek": "stek.jpg",
    # Extended pasta / classics (not LLM taxonomy ids — file stems only)
    "pasta_gradde": "pasta_gradde.jpg",
    "pasta_pesto": "pasta_pesto.jpg",
    "kottbullar": "kottbullar.jpg",
}

# Eating-out / non-dish titles — never invent a photo
_NO_IMAGE_TITLES = frozenset(
    {
        "lunch nara dig",
        "lunch nearby",
    }
)


def _strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def normalize_title(title: str) -> str:
    """Lowercase + strip diacritics for keyword matching."""
    s = _strip_diacritics((title or "").strip().lower())
    s = s.replace("ä", "a").replace("å", "a").replace("ö", "o")
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _existing_path(filename: str, *, root: Path | None = None) -> Path | None:
    base = root or DISHES_DIR
    path = base / filename
    return path if path.is_file() else None


def _verify_maps_at_import() -> None:
    missing: list[str] = []
    for key, fname in KEYWORD_FILES.items():
        if not (DISHES_DIR / fname).is_file():
            missing.append(f"keyword[{key!r}] → {fname}")
    for key, fname in CATEGORY_FILES.items():
        if not (DISHES_DIR / fname).is_file():
            missing.append(f"category[{key!r}] → {fname}")
    if missing:
        log.error(
            "dish_images: %d mapping(s) point to missing files: %s",
            len(missing),
            "; ".join(missing[:12]),
        )


_verify_maps_at_import()


def resolve_dish_image(
    title: str,
    category_hint: str | None = None,
    *,
    root: Path | None = None,
) -> str | None:
    """Return absolute path to an existing dish jpg, or None.

    Keyword match (longest first) wins. category_hint is used only when no
    keyword matches AND that category file exists. Never returns a missing path.
    """
    base = root or DISHES_DIR
    norm = normalize_title(title)
    if not norm or norm in _NO_IMAGE_TITLES:
        return None

    # Longest keyword first so "carbonara" beats "pasta"/"spaghetti"
    for cue, fname in sorted(KEYWORD_FILES.items(), key=lambda kv: len(kv[0]), reverse=True):
        cue_n = normalize_title(cue)
        if not cue_n:
            continue
        if len(cue_n) <= 3:
            # Short cues need word edges — avoid "dal" in "medalj"
            if not re.search(rf"(?:^|[^a-z0-9]){re.escape(cue_n)}(?:[^a-z0-9]|$)", norm):
                continue
        elif cue_n not in norm:
            continue
        path = _existing_path(fname, root=base)
        if path is not None:
            return str(path)

    hint = (category_hint or "").strip().lower()
    if hint and hint != "generic" and hint != "other":
        # Accept both taxonomy ids and bare stems
        fname = CATEGORY_FILES.get(hint) or (
            f"{hint}.jpg" if re.fullmatch(r"[a-z0-9_]+", hint) else None
        )
        if fname:
            path = _existing_path(fname, root=base)
            if path is not None:
                return str(path)

    return None


def resolve_dish_image_bytes(
    title: str,
    category_hint: str | None = None,
    *,
    root: Path | None = None,
) -> bytes | None:
    path = resolve_dish_image(title, category_hint, root=root)
    if not path:
        return None
    try:
        return Path(path).read_bytes()
    except OSError:
        return None


def iter_local_pack_titles(*, languages: tuple[str, ...] = ("sv", "en")) -> list[str]:
    """Every dish title local packs / meal candidates can produce (finite set)."""
    import food_domain as fd
    import food_local_packs as flp

    titles: list[str] = []
    for lang in languages:
        for row in flp.dinner_pack(lang):
            titles.append(str(row.get("suggestion") or ""))
        for meal in ("frukost", "lunch", "kvallsmal"):
            for row in fd.meal_candidates(meal, lang):
                titles.append(str(row.get("suggestion") or ""))
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        key = t.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def assert_local_packs_resolve(*, root: Path | None = None) -> None:
    """Build/test gate: every cookable local-pack title maps to an existing file.

    Eating-out pins (Lunch nära dig) are allowed to resolve to None.
    """
    failures: list[str] = []
    for title in iter_local_pack_titles():
        norm = normalize_title(title)
        if norm in _NO_IMAGE_TITLES:
            if resolve_dish_image(title, root=root) is not None:
                failures.append(f"{title!r} should be None (eating out)")
            continue
        path = resolve_dish_image(title, root=root)
        if not path or not Path(path).is_file():
            failures.append(title)
    if failures:
        raise AssertionError(
            "local pack titles without dish image: " + "; ".join(failures[:20])
        )
