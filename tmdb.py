# -*- coding: utf-8 -*-
"""
TMDB lookup for movie/series titles.

The app primarily uses Streamlit + deterministic offline behavior for tests.
When `TMDB_API_KEY` is present, we query TMDB; otherwise we fall back to a
small offline mapping for known demo titles.
"""

from __future__ import annotations

import functools
import os
import re
from typing import Any

import requests


TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


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

