# -*- coding: utf-8 -*-
"""
V1 mocks for external feasibility data.

- Clothing stock: Zalando-style size-level availability (swap for affiliate feed later)
- Streaming: JustWatch-style title → service map (swap for JustWatch API later)
"""

from __future__ import annotations

from typing import Any

# Mainstream Swedish retailers used by the clothes validator
RETAILERS = ("H&M", "Kappahl", "Dressmann", "Lindex", "Zalando")

# Mock catalog: product key → {retailer, sizes_in_stock, section, season, url}
CLOTHING_CATALOG: dict[str, dict[str, Any]] = {
    "mörka jeans": {
        "retailer": "Zalando",
        "section": "herr",
        "sizes": {"S", "M", "L", "32", "33", "34"},
        "season": "all",
        "url": "https://www.zalando.se/catalog/?q=m%C3%B6rka+jeans",
    },
    "mörkblå jeans": {
        "retailer": "H&M",
        "section": "dam",
        "sizes": {"34", "36", "38", "40", "S", "M", "L"},
        "season": "all",
        "url": "https://www2.hm.com/sv_se/search-results.html?q=m%C3%B6rkbl%C3%A5+jeans",
    },
    "vit t-shirt": {
        "retailer": "H&M",
        "section": "båda",
        "sizes": {"XS", "S", "M", "L", "XL"},
        "season": "all",
        "url": "https://www2.hm.com/sv_se/search-results.html?q=vit+t-shirt",
    },
    "stickad tröja": {
        "retailer": "Kappahl",
        "section": "båda",
        "sizes": {"S", "M", "L", "XL"},
        "season": "cold",
        "url": "https://www.kappahl.com/sv-SE/sok/?q=stickad+tröja",
    },
    "sneakers": {
        "retailer": "Zalando",
        "section": "båda",
        "sizes": {"39", "40", "41", "42", "43", "44", "45"},
        "season": "all",
        "url": "https://www.zalando.se/catalog/?q=sneakers",
    },
    "linnebyxor": {
        "retailer": "Lindex",
        "section": "dam",
        "sizes": {"34", "36", "38", "40"},
        "season": "warm",
        "url": "https://www.lindex.com/se/search?q=linnebyxor",
    },
    "ulltröja": {
        "retailer": "Dressmann",
        "section": "herr",
        "sizes": {"S", "M", "L", "XL"},
        "season": "cold",
        "url": "https://www.dressmann.com/se/sok/?q=ulltr%C3%B6ja",
    },
    "klänning": {
        "retailer": "Lindex",
        "section": "dam",
        "sizes": {"34", "36", "38", "40", "42"},
        "season": "warm",
        "url": "https://www.lindex.com/se/search?q=kl%C3%A4nning",
    },
    "cargobyxor": {
        "retailer": "H&M",
        "section": "herr",
        "sizes": {"30", "32", "34", "M", "L"},
        "season": "all",
        "url": "https://www2.hm.com/sv_se/search-results.html?q=cargobyxor",
    },
    "hoodie": {
        "retailer": "H&M",
        "section": "båda",
        "sizes": {"S", "M", "L", "XL"},
        "season": "all",
        "url": "https://www2.hm.com/sv_se/search-results.html?q=hoodie",
    },
}

# Mock JustWatch-style catalog: title → services + runtime minutes + deep links
STREAMING_CATALOG: dict[str, dict[str, Any]] = {
    "the night agent": {
        "services": {"netflix"},
        "runtime_min": 45,
        "kind": "series",
        "links": {"netflix": "https://www.netflix.com/search?q=The%20Night%20Agent"},
    },
    "wednesday": {
        "services": {"netflix"},
        "runtime_min": 50,
        "kind": "series",
        "links": {"netflix": "https://www.netflix.com/search?q=Wednesday"},
    },
    "dune": {
        "services": {"hbo_max", "prime"},
        "runtime_min": 155,
        "kind": "film",
        "links": {
            "hbo_max": "https://www.max.com/search?q=Dune",
            "prime": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase=Dune",
        },
    },
    "the bear": {
        "services": {"disney_plus"},
        "runtime_min": 35,
        "kind": "series",
        "links": {"disney_plus": "https://www.disneyplus.com/search?q=The%20Bear"},
    },
    "vänner": {
        "services": {"hbo_max", "tv4_play"},
        "runtime_min": 22,
        "kind": "series",
        "links": {
            "hbo_max": "https://www.max.com/search?q=Friends",
            "tv4_play": "https://www.tv4play.se/search?query=v%C3%A4nner",
        },
    },
    "friends": {
        "services": {"hbo_max", "tv4_play"},
        "runtime_min": 22,
        "kind": "series",
        "links": {
            "hbo_max": "https://www.max.com/search?q=Friends",
            "tv4_play": "https://www.tv4play.se/search?query=friends",
        },
    },
    "det sista kapitlet": {
        "services": {"svt_play"},
        "runtime_min": 45,
        "kind": "series",
        "links": {"svt_play": "https://www.svtplay.se/sok?q=det%20sista%20kapitlet"},
    },
    "beck": {
        "services": {"svt_play"},
        "runtime_min": 90,
        "kind": "film",
        "links": {"svt_play": "https://www.svtplay.se/sok?q=bonusfamiljen"},
    },
    "top gun maverick": {
        "services": {"paramount", "prime"},
        "runtime_min": 131,
        "kind": "film",
        "links": {"prime": "https://www.primevideo.com/search/ref=atv_nb_sr?phrase=Top%20Gun"},
        "rent_only": True,
        "rent_price_sek": 49,
    },
    "seinfeld": {
        "services": {"netflix"},
        "runtime_min": 22,
        "kind": "series",
        "links": {"netflix": "https://www.netflix.com/search?q=Seinfeld"},
    },
    " Succession": {
        "services": {"hbo_max"},
        "runtime_min": 60,
        "kind": "series",
        "links": {"hbo_max": "https://www.max.com/search?q=Succession"},
    },
    "succession": {
        "services": {"hbo_max"},
        "runtime_min": 60,
        "kind": "series",
        "links": {"hbo_max": "https://www.max.com/search?q=Succession"},
    },
    "andor": {
        "services": {"disney_plus"},
        "runtime_min": 45,
        "kind": "series",
        "links": {"disney_plus": "https://www.disneyplus.com/search?q=Andor"},
    },
    "our planet": {
        "services": {"netflix"},
        "runtime_min": 50,
        "kind": "series",
        "links": {"netflix": "https://www.netflix.com/search?q=Our%20Planet"},
    },
    "my octopus teacher": {
        "services": {"netflix"},
        "runtime_min": 85,
        "kind": "film",
        "links": {"netflix": "https://www.netflix.com/search?q=My%20Octopus%20Teacher"},
    },
    "hilda": {
        "services": {"netflix"},
        "runtime_min": 24,
        "kind": "series",
        "links": {"netflix": "https://www.netflix.com/search?q=Hilda"},
    },
    "kung fu panda": {
        "services": {"netflix"},
        "runtime_min": 92,
        "kind": "film",
        "links": {"netflix": "https://www.netflix.com/search?q=Kung%20Fu%20Panda"},
    },
    "explained": {
        "services": {"netflix"},
        "runtime_min": 20,
        "kind": "series",
        "links": {"netflix": "https://www.netflix.com/search?q=Explained"},
    },
}

SERVICE_ALIASES = {
    "netflix": "netflix",
    "viaplay": "viaplay",
    "hbo": "hbo_max",
    "hbo max": "hbo_max",
    "hbo_max": "hbo_max",
    "max": "hbo_max",
    "disney": "disney_plus",
    "disney+": "disney_plus",
    "disney_plus": "disney_plus",
    "svt": "svt_play",
    "svt play": "svt_play",
    "svt_play": "svt_play",
    "prime": "prime",
    "prime video": "prime",
    "amazon": "prime",
    "tv4": "tv4_play",
    "tv4 play": "tv4_play",
    "tv4_play": "tv4_play",
}


def normalize_service(name: str) -> str:
    return SERVICE_ALIASES.get(name.strip().lower(), name.strip().lower().replace(" ", "_"))


def clothing_in_stock(
    item_key: str,
    *,
    size: str | None,
    section: str,
    season: str | None = None,
) -> dict[str, Any] | None:
    """Return catalog row if item is in stock for section+size, else None."""
    key = item_key.strip().lower()
    row = CLOTHING_CATALOG.get(key)
    if not row:
        # fuzzy: substring match
        for k, v in CLOTHING_CATALOG.items():
            if k in key or key in k:
                row = v
                key = k
                break
    if not row:
        return None
    row_section = row["section"]
    if section != "båda" and row_section not in (section, "båda"):
        return None
    if size and size.upper() not in {s.upper() for s in row["sizes"]}:
        return None
    if season and row.get("season") not in ("all", None) and row["season"] != season:
        return None
    return {"key": key, **row}


def streaming_availability(
    title: str,
    *,
    user_services: list[str],
    max_minutes: int | None,
    allow_rentals: bool = False,
) -> dict[str, Any] | None:
    """Return match if title is on a subscribed service within time window."""
    key = title.strip().lower()
    row = STREAMING_CATALOG.get(key)
    if not row:
        for k, v in STREAMING_CATALOG.items():
            if k in key or key in k:
                row = v
                key = k
                break
    if not row:
        return None
    if row.get("rent_only") and not allow_rentals:
        return None
    user = {normalize_service(s) for s in user_services}
    overlap = user & set(row["services"])
    if not overlap:
        return None
    runtime = int(row.get("runtime_min") or 0)
    if max_minutes is not None and runtime > int(max_minutes) + 5:
        return None
    service = sorted(overlap)[0]
    return {
        "title": key,
        "service": service,
        "runtime_min": runtime,
        "kind": row.get("kind"),
        "url": (row.get("links") or {}).get(service),
        "rent_only": bool(row.get("rent_only")),
    }
