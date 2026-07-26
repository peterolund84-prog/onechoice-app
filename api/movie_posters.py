# -*- coding: utf-8 -*-
"""Resolve movie/series poster URLs (TMDB when keyed, free fallbacks — no key)."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

import requests

log = logging.getLogger("onechoice.movie_posters")

_TVMAZE_HOSTS = ("static.tvmaze.com", "api.tvmaze.com")
_ITUNES_HOSTS = ("mzstatic.com",)

# Swedish / alternate catalog titles → search-friendly names
_TITLE_ALIASES: dict[str, str] = {
    "vänner": "Friends",
    "vanner": "Friends",
    "friends": "Friends",
    "seinfeld": "Seinfeld",
    "the night agent": "The Night Agent",
    "the bear": "The Bear",
    "our planet": "Our Planet",
    "my octopus teacher": "My Octopus Teacher",
    "det sista kapitlet": "Det sista kapitlet",
    "bonusfamiljen": "Bonusfamiljen",
    "kung fu panda": "Kung Fu Panda",
    "the office": "The Office",
    "brooklyn nine-nine": "Brooklyn Nine-Nine",
    "brooklyn 99": "Brooklyn Nine-Nine",
}


def _proxy(url: str | None) -> str | None:
    if not url or not str(url).startswith("http"):
        return None
    return f"/api/media/poster?{urlencode({'url': str(url)})}"


def _norm(title: str) -> str:
    t = (title or "").strip().lower()
    t = t.replace("å", "a").replace("ä", "a").replace("ö", "o")
    return re.sub(r"\s+", " ", t)


def _search_names(title: str) -> list[str]:
    raw = (title or "").strip()
    if not raw:
        return []
    names: list[str] = []
    alias = _TITLE_ALIASES.get(_norm(raw)) or _TITLE_ALIASES.get(raw.lower())
    if alias:
        names.append(alias)
    names.append(raw)
    # Capitalize bare offline stubs like "seinfeld"
    if raw.islower() and " " not in raw:
        names.append(raw.title())
    # de-dupe preserve order
    out: list[str] = []
    seen: set[str] = set()
    for n in names:
        k = n.strip().lower()
        if k and k not in seen:
            seen.add(k)
            out.append(n.strip())
    return out


def _tmdb_poster(title: str, kind: str) -> str | None:
    try:
        import tmdb as tmdb_mod
        from api.secrets import tmdb_api_key

        if not tmdb_api_key():
            return None
        try:
            tmdb_mod.lookup_title.cache_clear()
        except Exception:
            pass
        for q in _search_names(title):
            meta = tmdb_mod.lookup_title(q, kind=kind) or {}
            url = meta.get("poster_url") if isinstance(meta, dict) else None
            if url and "image.tmdb.org" in str(url):
                stem = str(url).rsplit("/", 1)[-1].split(".", 1)[0]
                if stem.isalpha() and len(stem) < 24:
                    continue  # offline stub path
                return _proxy(str(url))
    except Exception as exc:
        log.debug("tmdb poster failed: %s", exc)
    return None


def _tvmaze_poster(title: str) -> str | None:
    for q in _search_names(title):
        try:
            resp = requests.get(
                "https://api.tvmaze.com/singlesearch/shows",
                params={"q": q},
                timeout=8,
                headers={"User-Agent": "OneChoice/1.0"},
            )
            if resp.status_code == 200:
                payload = resp.json() or {}
                image = payload.get("image") if isinstance(payload, dict) else None
                if isinstance(image, dict):
                    url = image.get("medium") or image.get("original")
                    if url and any(h in str(url) for h in _TVMAZE_HOSTS):
                        return _proxy(str(url))
            # Broader search
            resp2 = requests.get(
                "https://api.tvmaze.com/search/shows",
                params={"q": q},
                timeout=8,
                headers={"User-Agent": "OneChoice/1.0"},
            )
            if resp2.status_code == 200:
                rows = resp2.json() or []
                if isinstance(rows, list):
                    for row in rows[:5]:
                        show = (row or {}).get("show") if isinstance(row, dict) else None
                        if not isinstance(show, dict):
                            continue
                        image = show.get("image")
                        if not isinstance(image, dict):
                            continue
                        url = image.get("medium") or image.get("original")
                        if url and any(h in str(url) for h in _TVMAZE_HOSTS):
                            return _proxy(str(url))
        except Exception as exc:
            log.debug("tvmaze poster failed for %s: %s", q, exc)
    return None


def _itunes_poster(title: str) -> str | None:
    for q in _search_names(title):
        try:
            resp = requests.get(
                "https://itunes.apple.com/search",
                params={
                    "term": q,
                    "country": "se",
                    "media": "all",
                    "entity": "movie,tvSeason,tvShow",
                    "limit": 5,
                },
                timeout=8,
                headers={"User-Agent": "OneChoice/1.0"},
            )
            if resp.status_code != 200:
                continue
            results = (resp.json() or {}).get("results") or []
            if not isinstance(results, list):
                continue
            q_l = q.lower()
            for row in results:
                if not isinstance(row, dict):
                    continue
                name = str(
                    row.get("trackName")
                    or row.get("collectionName")
                    or row.get("artistName")
                    or ""
                ).lower()
                art = row.get("artworkUrl100") or row.get("artworkUrl60")
                if not art:
                    continue
                if q_l.split()[0] not in name and q_l not in name:
                    continue
                # Bump thumbnail to a usable poster size
                url = re.sub(r"/\d+x\d+bb\.", "/600x600bb.", str(art))
                if any(h in url for h in _ITUNES_HOSTS):
                    return _proxy(url)
        except Exception as exc:
            log.debug("itunes poster failed for %s: %s", q, exc)
    return None


def resolve_poster_url(
    title: str,
    *,
    kind: str = "series",
    existing: Any = None,
) -> str | None:
    """Return a same-origin proxied poster URL, or None.

    Always resolve by *title* first so rerolls never keep a stale poster.
    ``existing`` is only a last-resort fallback when every lookup fails.
    """
    kind_n = (kind or "series").strip().lower()
    if kind_n not in ("series", "film"):
        kind_n = "series"

    via_tmdb = _tmdb_poster(title, kind_n)
    if via_tmdb:
        return via_tmdb
    via_tv = _tvmaze_poster(title)
    if via_tv:
        return via_tv
    via_itunes = _itunes_poster(title)
    if via_itunes:
        return via_itunes

    if existing and str(existing).startswith("/api/media/poster"):
        return str(existing)
    if existing and str(existing).startswith("http") and "image.tmdb.org" in str(existing):
        stem = str(existing).rsplit("/", 1)[-1].split(".", 1)[0]
        if not (stem.isalpha() and len(stem) < 24):
            return _proxy(str(existing))
    return None
