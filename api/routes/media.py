# -*- coding: utf-8 -*-
"""Serve dish images + proxy TMDB posters through the API."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

import dish_images as dimg

router = APIRouter(prefix="/api/media", tags=["media"])

_ALLOWED_POSTER_HOSTS = {
    "image.tmdb.org",
    "www.themoviedb.org",
}


@router.get("/dish")
def dish_image(
    title: str = Query("", max_length=200),
    category: str = Query("", max_length=80),
) -> Response:
    path = dimg.resolve_dish_image(title, category or None)
    if not path:
        raise HTTPException(status_code=404, detail="Ingen bild.")
    p = Path(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Ingen bild.")
    # Stay inside dishes dir
    try:
        p.resolve().relative_to(dimg.DISHES_DIR.resolve())
    except Exception as exc:
        raise HTTPException(status_code=404, detail="Ingen bild.") from exc
    return FileResponse(
        p,
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/poster")
def poster_proxy(url: str = Query(..., max_length=500)) -> Response:
    """Proxy TMDB CDN images so phones on LAN always get a same-origin image."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Ogiltig poster-URL.")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_POSTER_HOSTS:
        raise HTTPException(status_code=400, detail="Poster-host ej tillåten.")
    try:
        resp = requests.get(url, timeout=12, headers={"User-Agent": "OneChoice/1.0"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Kunde inte hämta poster.") from exc
    if resp.status_code != 200 or not resp.content:
        raise HTTPException(status_code=404, detail="Poster saknas.")
    ctype = resp.headers.get("content-type") or "image/jpeg"
    if not ctype.startswith("image/"):
        ctype = "image/jpeg"
    return Response(
        content=resp.content,
        media_type=ctype,
        headers={"Cache-Control": "public, max-age=86400"},
    )
