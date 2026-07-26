# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
from api.deps import SessionDep, apply_auth

router = APIRouter(prefix="/api/lista", tags=["lista"])


class AddBody(BaseModel):
    name: str = Field(min_length=1)
    category: str = ""


class PatchBody(BaseModel):
    checked: bool


@router.get("")
def list_items(sess: SessionDep) -> dict:
    apply_auth(sess)
    try:
        items = db.list_shopping_items(sess.user_id)
    except Exception:
        items = []
    rows = []
    unchecked = 0
    for it in items or []:
        if isinstance(it, dict):
            row = dict(it)
        else:
            row = {
                "id": getattr(it, "id", None),
                "name": getattr(it, "name", str(it)),
                "category": getattr(it, "category", ""),
                "checked": bool(getattr(it, "checked", False)),
            }
        if not row.get("checked"):
            unchecked += 1
        rows.append(row)
    return {
        "items": rows,
        "unchecked_count": unchecked,
        "guest_mode": sess.guest_mode,
        "session": sess.public(),
    }


@router.post("/items")
def add_item(body: AddBody, sess: SessionDep) -> dict:
    apply_auth(sess)
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tomt namn.")
    try:
        if hasattr(db, "upsert_shopping_item"):
            db.upsert_shopping_item(sess.user_id, name, body.category or None)
        else:
            raise HTTPException(status_code=501, detail="Saknar upsert_shopping_item")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}


@router.patch("/items/{item_id}")
def patch_item(item_id: int, body: PatchBody, sess: SessionDep) -> dict:
    apply_auth(sess)
    try:
        db.toggle_shopping_item(sess.user_id, item_id, body.checked)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "checked": body.checked}
