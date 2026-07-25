# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException

import db
from api.deps import SessionDep, apply_auth
from api.session_store import STORE

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
def history(sess: SessionDep) -> dict:
    apply_auth(sess)
    try:
        rows = db.list_decisions(sess.user_id, limit=50)
    except TypeError:
        rows = db.list_decisions(sess.user_id)
    except Exception:
        rows = []
    out = []
    for r in rows or []:
        out.append(dict(r) if isinstance(r, dict) else dict(r))
    return {"rows": out, "session": sess.public()}


@router.post("/{decision_id}/open")
def open_decision(decision_id: int, sess: SessionDep) -> dict:
    apply_auth(sess)
    try:
        rows = db.list_decisions(sess.user_id, limit=200)
    except Exception:
        rows = []
    found = None
    for r in rows or []:
        row = dict(r) if isinstance(r, dict) else dict(r)
        if int(row.get("id") or 0) == int(decision_id):
            found = row
            break
    if not found:
        raise HTTPException(status_code=404, detail="Beslutet hittades inte.")
    # Rebuild a minimal current decision for the UI
    ctx = found.get("context_json") or found.get("context") or {}
    if isinstance(ctx, str):
        import json

        try:
            ctx = json.loads(ctx)
        except Exception:
            ctx = {}
    sess.current = {
        "ok": True,
        "domain": found.get("domain"),
        "suggestion": found.get("suggestion"),
        "justification": found.get("justification") or "",
        "decision_id": found.get("id"),
        "accepted": True,
        "locked": True,
        "context": ctx if isinstance(ctx, dict) else {},
    }
    sess.decision_id = int(found.get("id"))
    sess.accepted = True
    sess.force_chooser = False
    STORE.save(sess)
    page = "execute" if found.get("domain") == "food" else "result"
    return {"ok": True, "page": page, "decision": sess.current}
