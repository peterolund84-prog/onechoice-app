# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter

from api.deps import SessionDep
from api.secrets import grok_api_key, secrets_status, supabase_configured, tmdb_api_key

router = APIRouter(prefix="/api/profile", tags=["profile"])

BUILD_ID = "html-movie-reroll-v10-20260726"


@router.get("")
def profile(sess: SessionDep) -> dict:
    st = secrets_status()
    key = grok_api_key()
    if not key:
        ai = "offline — API-nyckel saknas"
    elif key.lower().startswith("xai-") and "din_" not in key.lower():
        ai = "online"
    else:
        ai = "offline — ogiltig nyckel"
    tmdb = bool(tmdb_api_key()) or bool(st.get("tmdb_configured"))
    sb = supabase_configured() or bool(st.get("supabase_configured"))
    return {
        "email": sess.email,
        "guest_mode": sess.guest_mode,
        "language": sess.language,
        "is_pro": False,
        "ai_status": ai,
        "supabase_configured": sb,
        "tmdb_configured": tmdb,
        "secrets": st,
        "integrations": {
            "supabase": (
                "ok"
                if sb
                else (
                    "saknas — ingen secrets.toml lokalt"
                    if not st.get("secrets_file_found")
                    else "saknas — SUPABASE_URL/KEY i secrets.toml"
                )
            ),
            "tmdb": (
                "ok"
                if tmdb
                else "saknas — valfritt; posters funkar via TVMaze utan nyckel"
            ),
            "grok": ai,
            "secrets_file": st.get("secrets_file") or "ej hittad",
        },
        "build": BUILD_ID,
        "stack": "html+fastapi",
        "session": sess.public(),
    }
