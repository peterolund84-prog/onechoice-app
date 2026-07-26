# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter

from api.deps import SessionDep
from api.services import decide_service as ds
from api.session_store import STORE

router = APIRouter(prefix="/api", tags=["home"])


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
            "text": "Har du ett eget förslag? Tipsa oss om ny kategori så kan vi lägga till den."
        },
        "session": sess.public(),
        "resume": resume,
        "fridge_label": "Fota kylen",
    }


@router.post("/home/chooser")
def force_chooser(sess: SessionDep) -> dict:
    sess.force_chooser = True
    STORE.save(sess)
    return {"ok": True, "session": sess.public()}
