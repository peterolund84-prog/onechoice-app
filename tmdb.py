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
    # Prefer Streamlit secrets, but keep it test-friendly.
    try:
        import streamlit as st  # type: ignore

        key = st.secrets.get("TMDB_API_KEY")
        if key:
            return str(key)
    except Exception:
        pass
    return os.environ.get("TMDB_API_KEY")


# Minimal offline mapping for unit tests and local dev (no TMDB_API_KEY).
# poster_path values are real TMDB CDN paths so posters load without an API key.
_OFFLINE_TMDB: dict[str, dict[str, Any]] = {
    # series
    "wednesday": {
        "tmdb_id": 119051,
        "year": 2022,
        "vote_average": 7.8,
        "poster_path": "/36xXlhEpQqVVPuiZhfoQuaY4OlA.jpg",
    },
    "seinfeld": {
        "tmdb_id": 1400,
        "year": 1989,
        "vote_average": 8.6,
        "poster_path": "/aCw8ONfyz3AhngVQa1E2Ss4KSUQ.jpg",
    },
    "vänner": {
        "tmdb_id": 1668,
        "year": 1994,
        "vote_average": 8.4,
        "poster_path": "/2koX1xLkpTQM4IZebYvKysFW1Nh.jpg",
    },
    "friends": {
        "tmdb_id": 1668,
        "year": 1994,
        "vote_average": 8.4,
        "poster_path": "/2koX1xLkpTQM4IZebYvKysFW1Nh.jpg",
    },
    "the night agent": {
        "tmdb_id": 124364,
        "year": 2023,
        "vote_average": 7.2,
        "poster_path": "/pRtJagIxpfODzzb0T0NAvZSzErC.jpg",
    },
    "andor": {
        "tmdb_id": 83867,
        "year": 2022,
        "vote_average": 8.0,
        "poster_path": "/khZqmwHQicTYoS7Flreb9EddFZC.jpg",
    },
    "the bear": {
        "tmdb_id": 136315,
        "year": 2022,
        "vote_average": 8.7,
        "poster_path": "/eKfVzzEazSIjJMrw9ADa2x8ksLz.jpg",
    },
    "succession": {
        "tmdb_id": 76331,
        "year": 2018,
        "vote_average": 8.9,
        "poster_path": "/z0XiwdrCQ9yVIr4O0pxzaAYRxdW.jpg",
    },
    " Succession": {
        "tmdb_id": 76331,
        "year": 2018,
        "vote_average": 8.9,
        "poster_path": "/z0XiwdrCQ9yVIr4O0pxzaAYRxdW.jpg",
    },
    # films
    "dune": {
        "tmdb_id": 438631,
        "year": 2021,
        "vote_average": 8.2,
        "poster_path": "/gDzOcq0pfeCeqMBwKIJlSmQpjkZ.jpg",
    },
    "det sista kapitlet": {
        "tmdb_id": 211088,
        "year": 2020,
        "vote_average": 6.8,
        "poster_path": "/kmlzoUI8Jj0UuVeAP1Hb8cYtx6G.jpg",
    },
    "top gun maverick": {
        "tmdb_id": 361743,
        "year": 2022,
        "vote_average": 7.7,
        "poster_path": "/n0YuM4f5lvGAP6MAW2kBIzugXnc.jpg",
    },
    "bonusfamiljen": {
        "tmdb_id": 67760,
        "year": 2015,
        "vote_average": 7.1,
        "poster_path": "/8FevKpYnnKSYLwTbpBgXmrHuTP0.jpg",
    },
    "our planet": {
        "tmdb_id": 85852,
        "year": 2019,
        "vote_average": 8.5,
        "poster_path": "/5ETY99uYe6O5h8WXRPA8G7FbmZr.jpg",
    },
    "my octopus teacher": {
        "tmdb_id": 653651,
        "year": 2020,
        "vote_average": 8.1,
        "poster_path": "/vmda3T7hT1kpCugE8oUpTxkZCQU.jpg",
    },
    "hilda": {
        "tmdb_id": 86331,
        "year": 2018,
        "vote_average": 8.0,
        "poster_path": "/5dwUlKkKHTv5VJ3llxWFS2B00Aj.jpg",
    },
    "kung fu panda": {
        "tmdb_id": 9502,
        "year": 2008,
        "vote_average": 7.6,
        "poster_path": "/wWt4JYXTg5Wr3xBW2phBrMKgp3x.jpg",
    },
    "explained": {
        "tmdb_id": 81356,
        "year": 2018,
        "vote_average": 7.9,
        "poster_path": "/bc3bmTdnoKcRuO9xdQKgAbB7Y9Z.jpg",
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
        poster_path = row.get("poster_path")
        poster_url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None
        return {
            "tmdb_id": row.get("tmdb_id"),
            "title": row.get("title") or title,
            "year": row.get("year"),
            "poster_url": poster_url,
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
