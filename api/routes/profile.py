# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter

from api.deps import SessionDep
from api.secrets import grok_api_key, supabase_configured, tmdb_api_key

router = APIRouter(prefix="/api/profile", tags=["profile"])

BUILD_ID = "html-share-fav-images-v5-20260726"


@router.get("")
def profile(sess: SessionDep) -> dict:
    key = grok_api_key()
    if not key:
        ai = "offline — API-nyckel saknas"
    elif key.lower().startswith("xai-") and "din_" not in key.lower():
        ai = "online"
    else:
        ai = "offline — ogiltig nyckel"
    tmdb = bool(tmdb_api_key())
    sb = supabase_configured()
    return {
        "email": sess.email,
        "guest_mode": sess.guest_mode,
        "language": sess.language,
        "is_pro": False,
        "ai_status": ai,
        "supabase_configured": sb,
        "tmdb_configured": tmdb,
        "integrations": {
            "supabase": "ok" if sb else "saknas — lägg SUPABASE_URL/KEY i secrets",
            "tmdb": "ok" if tmdb else "saknas — lägg TMDB_API_KEY (poster + betyg live)",
            "grok": ai,
        },
        "build": BUILD_ID,
        "stack": "html+fastapi",
        "session": sess.public(),
    }
