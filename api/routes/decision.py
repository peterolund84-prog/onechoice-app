# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import pipeline
from api.deps import SessionDep, apply_auth
from api.presentation import enrich_decision, nutrition_stats
from api.session_store import STORE

router = APIRouter(prefix="/api/decision", tags=["decision"])


class AcceptBody(BaseModel):
    open_execute: bool = True


class MergeBody(BaseModel):
    item_names: list[str] = Field(default_factory=list)


@router.get("/current")
def current(sess: SessionDep) -> dict:
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    return {
        "decision": enrich_decision(sess.current),
        "accepted": sess.accepted,
        "session": sess.public(),
    }


@router.post("/accept")
def accept(body: AcceptBody, sess: SessionDep) -> dict:
    apply_auth(sess)
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    did = sess.decision_id or sess.current.get("decision_id")
    if did:
        try:
            pipeline.try_accept_decision(
                int(did),
                route_log_id=sess.route_log_id,
            )
        except Exception:
            # Soft-lock even if DB accept fails (same as Streamlit app)
            pass
    sess.accepted = True
    cur = dict(sess.current)
    cur["accepted"] = True
    cur["locked"] = True
    sess.current = cur
    STORE.save(sess)
    page = "execute" if body.open_execute else "result"
    return {
        "ok": True,
        "accepted": True,
        "page": page,
        "decision": enrich_decision(sess.current),
        "session": sess.public(),
    }


@router.get("/execute")
def execute(sess: SessionDep) -> dict:
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    cur = sess.current
    ctx = cur.get("context") or {}
    shopping = ctx.get("shopping") or {}
    recipe = ctx.get("recipe") or shopping.get("recipe") or {}
    if isinstance(recipe, dict):
        try:
            import shopping as shopping_mod

            ensure = getattr(shopping_mod, "ensure_recipe_nutrition", None)
            if callable(ensure):
                recipe = ensure(
                    recipe,
                    suggestion=str(cur.get("suggestion") or recipe.get("title") or ""),
                    allow_estimate=True,
                )
        except Exception:
            pass
    enriched = enrich_decision(cur) or {}
    presentation = enriched.get("presentation") or {}
    nut = nutrition_stats(
        recipe if isinstance(recipe, dict) else None,
        suggestion=str(cur.get("suggestion") or ""),
    )
    if nut:
        presentation = dict(presentation)
        presentation["nutrition"] = nut
    return {
        "suggestion": cur.get("suggestion"),
        "justification": cur.get("justification"),
        "decision_id": cur.get("decision_id") or sess.decision_id,
        "domain": cur.get("domain"),
        "meal_type": ctx.get("meal_type") or sess.food_meal_type,
        "fridge_mode": ctx.get("source") == "fridge_photo",
        "shopping": shopping,
        "recipe": recipe,
        "presentation": presentation,
        "nutrition": nut,
        "accepted": sess.accepted,
        "session": sess.public(),
    }


@router.post("/execute/merge-list")
def merge_list(body: MergeBody, sess: SessionDep) -> dict:
    import db

    apply_auth(sess)
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    did = sess.decision_id or sess.current.get("decision_id")
    if not did:
        raise HTTPException(status_code=400, detail="Saknar decision_id.")
    ctx = sess.current.get("context") or {}
    shopping = ctx.get("shopping") or {}
    to_buy = shopping.get("to_buy") or {}
    # Optional filter by names
    if body.item_names:
        filtered: dict[str, list[str]] = {}
        want = {n.lower() for n in body.item_names}
        for sec, items in to_buy.items():
            keep = [i for i in items if str(i).lower() in want]
            if keep:
                filtered[sec] = keep
        to_buy = filtered
    try:
        added = db.merge_shopping_from_decision(
            sess.user_id,
            int(did),
            to_buy,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "added": len(added or [])}
