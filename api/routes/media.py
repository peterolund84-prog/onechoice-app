# -*- coding: utf-8 -*-
"""Serve dish images through the API (works even if StaticFiles mount is missed)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response

import dish_images as dimg

router = APIRouter(prefix="/api/media", tags=["media"])


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
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})
