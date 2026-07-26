# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from api.deps import SessionDep
from api.services import decide_service as ds
from api.session_store import STORE

router = APIRouter(prefix="/api", tags=["home"])


class SuggestionBody(BaseModel):
    text: str = Field(default="", max_length=500)


@router.get("/home")
def home(sess: SessionDep) -> dict:
    # Hem always shows chooser unless client asks to resume
    hero = ds.infer_hero(sess.language or "sv")
    resume = None
    if (
        not sess.force_chooser
        and sess.accepted
        and sess.current
        and (sess.current.get("domain") == "food")
    ):
        resume = "execute"
    return {
        "hero": hero,
        "domains": ds.DOMAIN_CARDS,
        "tip": {
            "text": "Saknar du en kategori? Tipsa oss",
            "placeholder": "T.ex. podcast, inredning, spelkväll…",
            "submit_label": "Skicka förslag",
            "help": "Här samlar vi idéer till nya kategorier — det startar inget beslut.",
        },
        "session": sess.public(),
        "resume": resume,
    }


@router.post("/home/chooser")
def force_chooser(sess: SessionDep) -> dict:
    sess.force_chooser = True
    STORE.save(sess)
    return {"ok": True, "session": sess.public()}


@router.post("/home/suggestion")
def product_suggestion(body: SuggestionBody, sess: SessionDep) -> dict:
    """Home suggestion box — stores ideas; does NOT run decide/router."""
    text = (body.text or "").strip()
    if len(text) < 2:
        raise HTTPException(status_code=400, detail="Skriv ett kort förslag först.")
    try:
        db.init_db()
        row = db.save_product_suggestion(text, user_id=sess.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Skriv ett kort förslag först.") from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Kunde inte spara förslaget.") from exc
    return {
        "ok": True,
        "saved": True,
        "id": row.get("id"),
        "message": "Tack! Vi tar med förslaget när vi bygger vidare.",
    }