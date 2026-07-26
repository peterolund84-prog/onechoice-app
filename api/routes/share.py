# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException

import db
from api.presentation import enrich_decision

router = APIRouter(prefix="/api/share", tags=["share"])


@router.get("/{token}")
def public_share(token: str) -> dict:
    row = db.get_public_share(token)
    if not row:
        raise HTTPException(status_code=404, detail="Delningen hittades inte.")
    try:
        db.log_share_open(token, decision_id=row.get("decision_id"), ref="share")
    except Exception:
        pass
    payload = row.get("payload") or row.get("payload_json") or {}
    if isinstance(payload, str):
        import json

        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    decision = {
        "ok": True,
        "domain": payload.get("domain") or row.get("domain"),
        "suggestion": payload.get("suggestion") or row.get("suggestion"),
        "justification": payload.get("justification") or "",
        "decision_id": payload.get("decision_id") or row.get("decision_id"),
        "context": payload.get("context") if isinstance(payload.get("context"), dict) else {},
    }
    return {
        "ok": True,
        "token": token,
        "decision": enrich_decision(decision, language=str(row.get("language") or "sv")),
    }
