# -*- coding: utf-8 -*-
"""Home hero inference — shared with React API (no Streamlit imports)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

APP_LOCAL_TZ = ZoneInfo("Europe/Stockholm")

DOMAIN_LABELS_SV = {
    "food": "Mat",
    "clothes": "Kläder",
    "movie": "Film",
    "workout": "Träning",
    "weekend": "Helg",
    "fridge": "Fota kylen",
}


def stockholm_now() -> datetime:
    return datetime.now(APP_LOCAL_TZ)


def infer_home_hero(
    now: datetime | None = None,
    *,
    language: str = "sv",
) -> dict[str, Any]:
    """Infer proactive home headline from local clock (meal windows + weekend alt)."""
    import food_domain as fd

    if now is None:
        local_fn = getattr(fd, "local_now", None)
        now = local_fn() if callable(local_fn) else stockholm_now()
    meal_type = fd.default_meal_type(now=now)
    meal_name = fd.meal_headline(meal_type, language)
    weekend_label = (
        DOMAIN_LABELS_SV["weekend"]
        if language == "sv"
        else "Weekend"
    )
    is_weekend = now.weekday() >= 5
    return {
        "headline": f"{meal_name}?",
        "domain": "food",
        "meal_type": meal_type,
        "weekend_alternate": is_weekend,
        "weekend_headline": f"{weekend_label}?",
        "sub": (
            "Ett tryck — jag tar beslutet."
            if language == "sv"
            else "One tap — I’ll decide."
        ),
        "cta": "Bestäm åt mig" if language == "sv" else "Decide for me",
        "section_label": "Eller välj själv" if language == "sv" else "Or choose yourself",
        "domains": [
            {"id": "food", "label": DOMAIN_LABELS_SV["food"]},
            {"id": "clothes", "label": DOMAIN_LABELS_SV["clothes"]},
            {"id": "movie", "label": DOMAIN_LABELS_SV["movie"]},
            {"id": "workout", "label": DOMAIN_LABELS_SV["workout"]},
            {"id": "weekend", "label": DOMAIN_LABELS_SV["weekend"]},
            {"id": "fridge", "label": DOMAIN_LABELS_SV["fridge"]},
        ],
        "something_else": "Något annat?" if language == "sv" else "Something else?",
    }
