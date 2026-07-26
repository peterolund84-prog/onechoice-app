# -*- coding: utf-8 -*-
"""
TMDB lookup for movie/series titles + SE watch providers.

Architecture: the LLM may invent titles freely; TMDB is the source of truth
for whether a title exists and which Swedish streaming services carry it.
`STREAMING_CATALOG` (mocks) is fallback-only for offline/local packs.

When `TMDB_API_KEY` is present, we query TMDB; otherwise we fall back to a
small offline mapping for known demo titles (tests / local dev).
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import requests

log = logging.getLogger("onechoice.tmdb")

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
PROVIDERS_CACHE_TTL_SEC = 24 * 60 * 60
DEFAULT_WATCH_REGION = "SE"

# TMDB provider_id → OneChoice service id (Sweden-focused).
TMDB_PROVIDER_TO_SERVICE: dict[int, str] = {
    8: "netflix",
    9: "prime",
    119: "prime",
    337: "disney_plus",
    384: "hbo_max",  # legacy HBO Max
    1899: "hbo_max",  # Max
    76: "viaplay",
    496: "svt_play",
    283: "svt_play",
    39: "tv4_play",
    323: "tv4_play",
}

_PROVIDER_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("netflix", "netflix"),
    ("disney", "disney_plus"),
    ("hbo", "hbo_max"),
    ("max", "hbo_max"),
    ("viaplay", "viaplay"),
    ("prime", "prime"),
    ("amazon", "prime"),
    ("svt", "svt_play"),
    ("tv4", "tv4_play"),
)

# Optional test injection: (tmdb_id, kind, region) -> provider result dict | None
_PROVIDERS_OVERRIDE: Callable[[int, str, str], dict[str, Any] | None] | None = None


def _norm_title(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _get_api_key() -> str | None:
    # Prefer Streamlit secrets, then api.secrets / env (uvicorn-friendly).
    try:
        import streamlit as st  # type: ignore

        key = st.secrets.get("TMDB_API_KEY")
        if key:
            return str(key)
    except Exception:
        pass
    try:
        from api.secrets import tmdb_api_key

        key = tmdb_api_key()
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("TMDB_API_KEY") or None


# Minimal offline mapping for unit tests and local dev.
# Values are intentionally stable and do not claim real TMDB ratings.
_OFFLINE_TMDB: dict[str, dict[str, Any]] = {
    # series
    "wednesday": {"tmdb_id": 1, "title": "Wednesday", "year": 2022, "vote_average": 7.8, "poster_path": "/wednesday.jpg"},
    "seinfeld": {"tmdb_id": 2, "title": "Seinfeld", "year": 1989, "vote_average": 8.6, "poster_path": "/seinfeld.jpg"},
    "vänner": {"tmdb_id": 3, "title": "Vänner", "year": 1994, "vote_average": 8.4, "poster_path": "/vanner.jpg"},
    "friends": {"tmdb_id": 3, "title": "Friends", "year": 1994, "vote_average": 8.4, "poster_path": "/vanner.jpg"},
    "the night agent": {"tmdb_id": 4, "title": "The Night Agent", "year": 2023, "vote_average": 7.2, "poster_path": "/night-agent.jpg"},
    "andor": {"tmdb_id": 5, "title": "Andor", "year": 2022, "vote_average": 8.0, "poster_path": "/andor.jpg"},
    "the bear": {"tmdb_id": 6, "title": "The Bear", "year": 2022, "vote_average": 8.7, "poster_path": "/the-bear.jpg"},
    "succession": {"tmdb_id": 7, "title": "Succession", "year": 2018, "vote_average": 8.9, "poster_path": "/succession.jpg"},
    " Succession": {"tmdb_id": 7, "title": "Succession", "year": 2018, "vote_average": 8.9, "poster_path": "/succession.jpg"},
    "the office": {"tmdb_id": 8, "title": "The Office", "year": 2005, "vote_average": 8.5, "poster_path": "/the-office.jpg"},
    "brooklyn nine-nine": {"tmdb_id": 9, "title": "Brooklyn Nine-Nine", "year": 2013, "vote_average": 8.1, "poster_path": "/b99.jpg"},
    # films
    "dune": {"tmdb_id": 101, "title": "Dune", "year": 2021, "vote_average": 8.2, "poster_path": "/dune.jpg"},
    "det sista kapitlet": {"tmdb_id": 102, "title": "Det sista kapitlet", "year": 2020, "vote_average": 6.8, "poster_path": "/det-sista-kapitlet.jpg"},
    "top gun maverick": {"tmdb_id": 103, "title": "Top Gun Maverick", "year": 2022, "vote_average": 7.7, "poster_path": "/top-gun-maverick.jpg"},
    "bonusfamiljen": {"tmdb_id": 104, "title": "Bonusfamiljen", "year": 2015, "vote_average": 7.1, "poster_path": "/bonus.jpg"},
    "our planet": {"tmdb_id": 201, "title": "Our Planet", "year": 2019, "vote_average": 8.5, "poster_path": "/our-planet.jpg"},
    "my octopus teacher": {"tmdb_id": 202, "title": "My Octopus Teacher", "year": 2020, "vote_average": 8.1, "poster_path": "/octopus.jpg"},
    "hilda": {"tmdb_id": 203, "title": "Hilda", "year": 2018, "vote_average": 8.0, "poster_path": "/hilda.jpg"},
    "kung fu panda": {"tmdb_id": 204, "title": "Kung Fu Panda", "year": 2008, "vote_average": 7.6, "poster_path": "/kfp.jpg"},
    "explained": {"tmdb_id": 205, "title": "Explained", "year": 2018, "vote_average": 7.9, "poster_path": "/explained.jpg"},
    "the intern": {"tmdb_id": 206, "title": "The Intern", "year": 2015, "vote_average": 7.1, "poster_path": "/the-intern.jpg"},
    "chef": {"tmdb_id": 207, "title": "Chef", "year": 2014, "vote_average": 7.3, "poster_path": "/chef.jpg"},
    "about time": {"tmdb_id": 208, "title": "About Time", "year": 2013, "vote_average": 7.8, "poster_path": "/about-time.jpg"},
    "extraction": {"tmdb_id": 209, "title": "Extraction", "year": 2020, "vote_average": 6.8, "poster_path": "/extraction.jpg"},
    "the gray man": {"tmdb_id": 210, "title": "The Gray Man", "year": 2022, "vote_average": 6.9, "poster_path": "/gray-man.jpg"},
    "red notice": {"tmdb_id": 211, "title": "Red Notice", "year": 2021, "vote_average": 6.8, "poster_path": "/red-notice.jpg"},
    "murder mystery": {"tmdb_id": 212, "title": "Murder Mystery", "year": 2019, "vote_average": 6.3, "poster_path": "/murder-mystery.jpg"},
    "the nice guys": {"tmdb_id": 213, "title": "The Nice Guys", "year": 2016, "vote_average": 7.2, "poster_path": "/nice-guys.jpg"},
    "crazy rich asians": {"tmdb_id": 214, "title": "Crazy Rich Asians", "year": 2018, "vote_average": 7.0, "poster_path": "/cra.jpg"},
    "free solo": {"tmdb_id": 215, "title": "Free Solo", "year": 2018, "vote_average": 8.0, "poster_path": "/free-solo.jpg"},
    "13th": {"tmdb_id": 216, "title": "13th", "year": 2016, "vote_average": 8.2, "poster_path": "/13th.jpg"},
    "luca": {"tmdb_id": 217, "title": "Luca", "year": 2021, "vote_average": 7.5, "poster_path": "/luca.jpg"},
    "the mitchells vs the machines": {
        "tmdb_id": 218,
        "title": "The Mitchells vs. the Machines",
        "year": 2021,
        "vote_average": 7.6,
        "poster_path": "/mitchells.jpg",
    },
}


@functools.lru_cache(maxsize=512)
def lookup_title(title: str, kind: str = "series") -> dict[str, Any] | None:
    """
    Lookup TMDB metadata for a title.

    Args:
        title: Catalog title to search for.
        kind: "series" or "film".
    Returns:
        {tmdb_id, title, year, poster_url, vote_average} or None.
    """
    title_n = _norm_title(title)
    if not title_n:
        return None

    kind_n = (kind or "").strip().lower()
    if kind_n not in ("series", "film"):
        # Best-effort: treat unknown as series to match our app’s usage.
        kind_n = "series"

    api_key = _get_api_key()
    if not api_key:
        row = _OFFLINE_TMDB.get(title_n)
        if not row:
            return None
        # Offline stubs have fake poster_path values — do not invent broken CDN URLs.
        return {
            "tmdb_id": row.get("tmdb_id"),
            "title": row.get("title") or title,
            "year": row.get("year"),
            "poster_url": None,
            "vote_average": row.get("vote_average"),
        }

    endpoint = "/search/tv" if kind_n == "series" else "/search/movie"
    params = {"api_key": api_key, "query": title, "include_adult": "false"}
    resp = requests.get(f"{TMDB_BASE}{endpoint}", params=params, timeout=10)
    resp.raise_for_status()
    payload = resp.json() or {}
    results = payload.get("results") or []
    if not results:
        return None

    # Pick the best-looking match: prefer exact title, then first result.
    best = None
    for r in results:
        r_title = str(r.get("name") or r.get("title") or "").strip().lower()
        if r_title and r_title == title_n:
            best = r
            break
    best = best or results[0]

    tmdb_id = best.get("id")
    vote_average = best.get("vote_average")
    poster_path = best.get("poster_path")
    poster_url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None

    date_s = (
        best.get("first_air_date")
        or best.get("release_date")
        or best.get("air_date")
        or ""
    )
    year = None
    if isinstance(date_s, str) and len(date_s) >= 4 and date_s[:4].isdigit():
        year = int(date_s[:4])

    return {
        "tmdb_id": tmdb_id,
        "title": str(best.get("name") or best.get("title") or title),
        "year": year,
        "poster_url": poster_url,
        "vote_average": vote_average,
    }


# Offline SE flatrate services keyed by offline stub tmdb_id (tests / no API key).
_OFFLINE_SE_PROVIDERS: dict[int, list[str]] = {
    1: ["netflix"],  # Wednesday
    2: ["netflix"],  # Seinfeld
    3: ["hbo_max", "tv4_play"],  # Friends / Vänner
    4: ["netflix"],  # The Night Agent
    5: ["disney_plus"],  # Andor
    6: ["disney_plus"],  # The Bear
    7: ["hbo_max"],  # Succession
    8: ["netflix", "prime"],  # The Office
    9: ["netflix", "disney_plus"],  # Brooklyn Nine-Nine
    101: ["hbo_max", "prime"],  # Dune
    102: ["svt_play"],  # Det sista kapitlet
    103: [],  # Top Gun — rent-only in catalog; no flatrate offline
    104: ["svt_play"],  # Bonusfamiljen
    201: ["netflix"],  # Our Planet
    202: ["netflix"],  # My Octopus Teacher
    203: ["netflix"],  # Hilda
    204: ["netflix"],  # Kung Fu Panda
    205: ["netflix"],  # Explained
    206: ["netflix"],  # The Intern
    207: ["netflix"],  # Chef
    208: ["netflix"],  # About Time
    209: ["netflix"],  # Extraction
    210: ["netflix"],  # The Gray Man
    211: ["netflix"],  # Red Notice
    212: ["netflix"],  # Murder Mystery
    213: ["netflix"],  # The Nice Guys
    214: ["netflix"],  # Crazy Rich Asians
    215: ["netflix"],  # Free Solo
    216: ["netflix"],  # 13th
    217: ["netflix"],  # Luca
    218: ["netflix"],  # Mitchells
}


def _providers_cache_path() -> Path:
    return Path(tempfile.gettempdir()) / "onechoice_tmdb_providers_cache.json"


def _load_providers_cache() -> dict[str, Any]:
    path = _providers_cache_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_providers_cache(data: dict[str, Any]) -> None:
    try:
        _providers_cache_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
    except Exception as exc:
        log.debug("tmdb providers cache write failed: %s", exc)


def map_provider_to_service(provider: dict[str, Any]) -> str | None:
    """Map a TMDB provider row to an internal service id."""
    try:
        pid = int(provider.get("provider_id"))
    except (TypeError, ValueError):
        pid = 0
    if pid and pid in TMDB_PROVIDER_TO_SERVICE:
        return TMDB_PROVIDER_TO_SERVICE[pid]
    name = str(provider.get("provider_name") or "").strip().lower()
    if not name:
        return None
    for hint, svc in _PROVIDER_NAME_HINTS:
        if hint in name:
            # Avoid mapping plain "max" inside unrelated names without word sense —
            # TMDB uses "Max" / "HBO Max" which contain these hints cleanly.
            if hint == "max" and "hbo" not in name and name.strip() != "max":
                continue
            return svc
    return None


def _parse_region_providers(region_row: dict[str, Any] | None) -> dict[str, Any]:
    row = region_row if isinstance(region_row, dict) else {}
    flatrate = list(row.get("flatrate") or [])
    services: list[str] = []
    seen: set[str] = set()
    for p in flatrate:
        if not isinstance(p, dict):
            continue
        svc = map_provider_to_service(p)
        if svc and svc not in seen:
            seen.add(svc)
            services.append(svc)
    return {
        "services": services,
        "flatrate": flatrate,
        "link": row.get("link"),
        "rent": list(row.get("rent") or []),
        "buy": list(row.get("buy") or []),
    }


def set_providers_override(
    fn: Callable[[int, str, str], dict[str, Any] | None] | None,
) -> None:
    """Tests inject SE provider results; pass None to restore default."""
    global _PROVIDERS_OVERRIDE
    _PROVIDERS_OVERRIDE = fn
    watch_providers.cache_clear()


@functools.lru_cache(maxsize=512)
def watch_providers(
    tmdb_id: int,
    kind: str = "series",
    region: str = DEFAULT_WATCH_REGION,
) -> dict[str, Any] | None:
    """
    SE (or other region) watch providers for a TMDB id.

    Returns:
        {region, services, flatrate, link, source} or None when unknown.
    Cache: process lru + 24h file cache for live API responses.
    """
    try:
        tid = int(tmdb_id)
    except (TypeError, ValueError):
        return None
    if tid <= 0:
        return None

    kind_n = (kind or "series").strip().lower()
    if kind_n not in ("series", "film"):
        kind_n = "series"
    region_n = (region or DEFAULT_WATCH_REGION).strip().upper() or DEFAULT_WATCH_REGION

    if _PROVIDERS_OVERRIDE is not None:
        try:
            overr = _PROVIDERS_OVERRIDE(tid, kind_n, region_n)
        except Exception as exc:
            log.debug("providers override failed: %s", exc)
            overr = None
        if overr is None:
            return None
        out = dict(overr)
        out.setdefault("region", region_n)
        out.setdefault("source", "override")
        out.setdefault("services", list(out.get("services") or []))
        return out

    cache_key = f"{kind_n}:{tid}:{region_n}"
    cached = _load_providers_cache()
    hit = cached.get(cache_key) if isinstance(cached, dict) else None
    if isinstance(hit, dict) and (time.time() - float(hit.get("ts") or 0)) < PROVIDERS_CACHE_TTL_SEC:
        body = hit.get("body")
        if isinstance(body, dict):
            return dict(body)

    api_key = _get_api_key()
    if not api_key:
        services = list(_OFFLINE_SE_PROVIDERS.get(tid) or [])
        return {
            "region": region_n,
            "services": services,
            "flatrate": [],
            "link": None,
            "source": "offline",
        }

    media = "tv" if kind_n == "series" else "movie"
    try:
        resp = requests.get(
            f"{TMDB_BASE}/{media}/{tid}/watch/providers",
            params={"api_key": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
    except Exception as exc:
        log.debug("watch_providers fetch failed id=%s: %s", tid, exc)
        return None

    results = payload.get("results") if isinstance(payload, dict) else None
    region_row = (results or {}).get(region_n) if isinstance(results, dict) else None
    parsed = _parse_region_providers(region_row if isinstance(region_row, dict) else None)
    out = {
        "region": region_n,
        "services": parsed["services"],
        "flatrate": parsed["flatrate"],
        "link": parsed.get("link"),
        "rent": parsed.get("rent") or [],
        "buy": parsed.get("buy") or [],
        "source": "tmdb",
    }
    cached = cached if isinstance(cached, dict) else {}
    cached[cache_key] = {"ts": time.time(), "body": out}
    _save_providers_cache(cached)
    return out


def se_services_for_title(
    title: str,
    *,
    kind: str = "series",
    region: str = DEFAULT_WATCH_REGION,
) -> dict[str, Any] | None:
    """Lookup title on TMDB then return regional watch-provider summary."""
    row = lookup_title(title, kind=kind)
    if not row or not row.get("tmdb_id"):
        return None
    providers = watch_providers(int(row["tmdb_id"]), kind=kind, region=region)
    if not providers:
        return None
    return {
        **providers,
        "tmdb_id": row.get("tmdb_id"),
        "title": row.get("title"),
        "year": row.get("year"),
        "poster_url": row.get("poster_url"),
        "vote_average": row.get("vote_average"),
    }

