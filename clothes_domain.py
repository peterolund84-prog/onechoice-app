# -*- coding: utf-8 -*-
"""Clothes domain: occasion matrix + profile helpers."""

from __future__ import annotations

from typing import Any

# Primary input: "Vart ska du?" — one tap, never a form
OCCASIONS: dict[str, dict[str, Any]] = {
    "jobb": {
        "sv": "Jobb",
        "en": "Work",
        "formality": "smart_casual",
        "notes_sv": "jobb: din arbetsbas — snyggt nog utan kavaj om du inte behöver",
        "notes_en": "work baseline — polished without a blazer unless required",
        "hours": (7, 8, 9),  # preselect weekday mornings
    },
    "vardag": {
        "sv": "Vardag hemma",
        "en": "Home / everyday",
        "formality": "casual",
        "notes_sv": "bekvämt hemma — mjuka lager, noll dresscode",
        "notes_en": "comfortable at home — soft layers, no dress code",
        "hours": (10, 11, 12, 13, 14, 15),
    },
    "fest": {
        "sv": "Fest",
        "en": "Party",
        "formality": "dressy",
        "notes_sv": "fest: mörkare, mer ansträngt — fint utan att överdriva",
        "notes_en": "party: darker, more dressed — sharp without overdoing it",
        "hours": (20, 21, 22),
    },
    "middag": {
        "sv": "Middag ute",
        "en": "Dinner out",
        "formality": "smart",
        "notes_sv": "middag ute: smart casual, snygg men avslappnad",
        "notes_en": "dinner out: smart casual, polished but relaxed",
        "hours": (17, 18, 19),
    },
    "traffa": {
        "sv": "Träffa folk",
        "en": "Meet people",
        "formality": "casual_plus",
        "notes_sv": "träffa folk: vardagsstil med ett lyft",
        "notes_en": "meet people: everyday with a small lift",
        "hours": (16,),
    },
    "barnkalas": {
        "sv": "Barnkalas & familj",
        "en": "Kids / family",
        "formality": "practical",
        "notes_sv": "barnkalas: bekvämt, tål fläckar, rörligt",
        "notes_en": "kids/family: comfortable, stain-ok, easy to move",
        "hours": (),
    },
}

OCCASION_ORDER = ("jobb", "vardag", "fest", "middag", "traffa", "barnkalas")


def occasion_label(key: str, language: str = "sv") -> str:
    row = OCCASIONS.get(key) or {}
    return str(row.get(language) or row.get("sv") or key)


def default_occasion(hour: int, *, weekday: bool = True) -> str:
    """Preselect the most likely occasion for this hour (one tap to confirm)."""
    if weekday and 7 <= hour <= 9:
        return "jobb"
    if 17 <= hour <= 19:
        return "middag"
    if 20 <= hour <= 23:
        return "fest"
    if 10 <= hour <= 15:
        return "vardag"
    if hour == 16:
        return "traffa"
    return "vardag"


def formality_for(occasion: str) -> str:
    return str((OCCASIONS.get(occasion) or {}).get("formality") or "casual")


def occasion_guidance(occasion: str, language: str = "sv") -> str:
    row = OCCASIONS.get(occasion) or {}
    key = "notes_sv" if language == "sv" else "notes_en"
    return str(row.get(key) or "")


def ensure_clothes_profile(profile_json: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize clothes onboarding fields used by the generator."""
    root = dict(profile_json or {})
    clothes = dict(root.get("clothes") or {})
    section = str(clothes.get("section") or "båda").lower()
    if section not in ("herr", "dam", "båda"):
        section = "båda"
    sizes = dict(clothes.get("sizes") or {})
    sizes.setdefault("top", "M")
    sizes.setdefault("bottom", "32")
    sizes.setdefault("shoes", "42")
    styles = clothes.get("styles") or ["casual"]
    if not isinstance(styles, list):
        styles = ["casual"]
    retailers = clothes.get("retailers") or ["Zalando", "H&M", "Lindex"]
    if not isinstance(retailers, list):
        retailers = ["Zalando", "H&M", "Lindex"]
    clothes.update(
        {
            "section": section,
            "sizes": sizes,
            "styles": styles,
            "retailers": retailers,
            "wardrobe": clothes.get("wardrobe") or [],
            "workwear_baseline": clothes.get("workwear_baseline")
            or ("skjorta + chinos" if section != "dam" else "blus + byxa"),
        }
    )
    root["clothes"] = clothes
    return root


def clothes_profile_complete(profile_json: dict[str, Any] | None) -> bool:
    clothes = (profile_json or {}).get("clothes") or {}
    return bool(clothes.get("section") and clothes.get("sizes") and clothes.get("onboarded"))


def outfit_for_occasion(
    occasion: str,
    *,
    section: str = "båda",
    language: str = "sv",
    temp_c: float | None = None,
) -> dict[str, Any]:
    """Deterministic outfit suggestion shaped by occasion + section + weather."""
    formal = formality_for(occasion)
    cold = temp_c is not None and temp_c < 8
    warm = temp_c is not None and temp_c > 22
    herr = section in ("herr", "men", "male")
    dam = section in ("dam", "women", "female")

    if language != "sv":
        # English variants kept short; Swedish is primary
        pass

    if occasion == "fest":
        if dam:
            sug = "Mörk klänning + jacka" if not cold else "Mörk klänning + kappa"
            just = "Festfint — mörkare och mer ansträngt utan att överdriva."
        else:
            sug = "Mörk skjorta + chinos"
            just = "Mörk skjorta + chinos — festfint utan kavaj."
            if cold:
                sug = "Mörk skjorta + chinos + kappa"
    elif occasion == "barnkalas":
        sug = "Jeans + mjuk tröja"
        just = "Bekvämt som tål fläckar — barnkalas och familj."
        if warm:
            sug = "T-shirt + jeans"
    elif occasion == "jobb":
        if dam:
            sug = "Blus + mörka byxor"
            just = "Jobbstil utan krångel — snyggt nog för kontoret."
        else:
            sug = "Skjorta + chinos"
            just = "Jobbstil utan kavaj — din vardagsbas på kontoret."
        if cold:
            sug = sug + " + stickad tröja"
    elif occasion == "middag":
        if dam:
            sug = "Fin blus + mörka byxor"
        else:
            sug = "Skjorta + mörka jeans"
        just = "Middag ute — smart casual, snygg men avslappnad."
    elif occasion == "traffa":
        sug = "Ren t-shirt + overshirt + jeans" if not dam else "Fin t-shirt + jeansjacka"
        just = "Träffa folk — vardag med ett lyft."
    else:  # vardag
        sug = "Hoodie + joggers" if not dam else "Mjuk byxa + hoodie"
        just = "Vardag hemma — bekvämt, noll dresscode."
        if formal:  # keep linter quiet / structure
            pass

    if warm and "kappa" in sug.lower():
        sug = sug.replace(" + kappa", "").replace("+ kappa", "")

    return {
        "suggestion": sug,
        "justification": just,
        "occasion": occasion,
        "formality": formal,
        "meta": {"occasion": occasion, "formality": formal, "active_minutes": 5},
    }
