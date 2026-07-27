# -*- coding: utf-8 -*-
"""Serve dish images + proxy TMDB posters / remote food photos through the API."""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

import dish_images as dimg
import food_image_search as fis

router = APIRouter(prefix="/api/media", tags=["media"])

_ALLOWED_POSTER_HOSTS = {
    "image.tmdb.org",
    "www.themoviedb.org",
    "static.tvmaze.com",
    "api.tvmaze.com",
    "is1-ssl.mzstatic.com",
    "is2-ssl.mzstatic.com",
    "is3-ssl.mzstatic.com",
    "is4-ssl.mzstatic.com",
    "is5-ssl.mzstatic.com",
}

_PRIVATE_HOST = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|0\.|::1$)",
    re.I,
)


def _host_allowed(host: str) -> bool:
    h = (host or "").lower()
    if h in _ALLOWED_POSTER_HOSTS:
        return True
    # iTunes CDN uses isN-ssl.mzstatic.com
    return h.endswith(".mzstatic.com")


def _food_host_ok(host: str) -> bool:
    h = (host or "").lower().strip()
    if not h or _PRIVATE_HOST.match(h):
        return False
    if fis._host_allowed(h):
        return True
    # Allow other public hosts when the URL already passed image validation upstream;
    # still block obvious local/metadata names.
    try:
        infos = socket.getaddrinfo(h, None)
    except OSError:
        return False
    for info in infos:
        ip_s = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_s)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        ):
            return False
    return True

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
    if not _host_allowed(host):
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


@router.get("/food")
def food_image_proxy(url: str = Query(..., max_length=800)) -> Response:
    """Proxy a validated remote dish photo (AI image_search) same-origin for LAN."""
    raw = (url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Ogiltig bild-URL.")
    host = (parsed.hostname or "").lower()
    if not _food_host_ok(host):
        raise HTTPException(status_code=400, detail="Bild-host ej tillåten.")
    try:
        resp = requests.get(
            raw,
            timeout=12,
            headers={"User-Agent": "OneChoice/1.0"},
            stream=True,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Kunde inte hämta bild.") from exc
    content = resp.content
    if resp.status_code >= 400 or not content:
        raise HTTPException(status_code=404, detail="Bild saknas.")
    ctype = (resp.headers.get("content-type") or "").lower()
    if not ctype.startswith("image/"):
        raise HTTPException(status_code=400, detail="URL är inte en bild.")
    return Response(
        content=content,
        media_type=ctype.split(";")[0].strip() or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )