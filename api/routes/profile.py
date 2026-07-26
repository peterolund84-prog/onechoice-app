# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter

from api.deps import SessionDep
from api.secrets import grok_api_key

router = APIRouter(prefix="/api/profile", tags=["profile"])

BUILD_ID = "html-spark-positions-v3-20260726"


@router.get("")
def profile(sess: SessionDep) -> dict:
    key = grok_api_key()
    if not key:
        ai = "offline — API-nyckel saknas"
    elif key.lower().startswith("xai-") and "din_" not in key.lower():
        ai = "online"
    else:
        ai = "offline — ogiltig nyckel"
    return {
        "email": sess.email,
        "guest_mode": sess.guest_mode,
        "language": sess.language,
        "is_pro": False,
        "ai_status": ai,
        "build": BUILD_ID,
        "stack": "html+fastapi",
        "session": sess.public(),
    }
