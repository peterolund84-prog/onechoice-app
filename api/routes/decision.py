# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import db
import pipeline
import share_domain as sd
from api.deps import SessionDep, apply_auth
from api.presentation import enrich_decision, nutrition_stats, share_text_for
from api.session_store import STORE

router = APIRouter(prefix="/api/decision", tags=["decision"])


class AcceptBody(BaseModel):
    open_execute: bool = True


class MergeBody(BaseModel):
    item_names: list[str] = Field(default_factory=list)


def _enriched(sess: SessionDep) -> dict | None:
    return enrich_decision(sess.current, language=sess.language or "sv")


@router.get("/current")
def current(sess: SessionDep) -> dict:
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    return {
        "decision": _enriched(sess),
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
        "decision": _enriched(sess),
        "session": sess.public(),
    }


@router.post("/favorite")
def toggle_favorite(sess: SessionDep) -> dict:
    apply_auth(sess)
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    did = sess.decision_id or sess.current.get("decision_id")
    if not did:
        raise HTTPException(status_code=400, detail="Saknar decision_id.")
    currently = bool(sess.current.get("favorite"))
    try:
        row = db.set_decision_favorite(int(did), not currently)
        fav = bool(row.get("favorite"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    cur = dict(sess.current)
    cur["favorite"] = fav
    sess.current = cur
    STORE.save(sess)
    return {
        "ok": True,
        "favorite": fav,
        "decision_id": int(did),
        "decision": _enriched(sess),
    }


@router.get("/share")
def share_bundle(sess: SessionDep) -> dict:
    """Native-share payload (text + absolute-ish URL) for the active decision."""
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    cur = dict(sess.current)
    if cur.get("decision_id") is None and sess.decision_id is not None:
        cur["decision_id"] = sess.decision_id
    if cur.get("user_id") is None:
        cur["user_id"] = sess.user_id
    try:
        share = db.ensure_public_share(cur, language=sess.language or "sv")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    token = str(share.get("token") or "")
    did = share.get("decision_id")
    text = share_text_for(cur, language=sess.language or "sv")
    url = sd.share_path(token=token, decision_id=did)
    # Prefer /share?token=… for the HTML stack landing page
    if token:
        url = f"/share?token={token}"
        if did is not None:
            url += f"&decision_id={did}"
    return {
        "ok": True,
        "title": "OneChoice",
        "text": text,
        "url": url,
        "token": token,
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
        try:
            import food_budget as fbud

            meta = cur.get("meta") if isinstance(cur.get("meta"), dict) else {}
            recipe = fbud.ensure_recipe_cost(recipe, meta=meta, allow_estimate=True)
        except Exception:
            pass
    enriched = _enriched(sess) or {}
    presentation = enriched.get("presentation") or {}
    nut = nutrition_stats(
        recipe if isinstance(recipe, dict) else None,
        suggestion=str(cur.get("suggestion") or ""),
    )
    # Cost / nutrition stats: recipe view only — never feed the pre-lock card.
    cost = None
    show_cost = False
    try:
        import food_budget as fbud

        level = fbud.normalize_meal_budget(ctx.get("meal_budget"))
        show_cost = fbud.budget_active(level)
        if show_cost and isinstance(recipe, dict):
            cost = fbud.cost_stat(recipe, language=sess.language or "sv")
            if cost is None and ctx.get("cost_per_portion_sek") is not None:
                cost = {
                    "sek": fbud.round_cost_sek(ctx.get("cost_per_portion_sek")),
                    "label": fbud.format_cost_label(
                        ctx.get("cost_per_portion_sek"), language=sess.language or "sv"
                    ),
                    "unit": "portion",
                    "approx": True,
                }
    except Exception:
        cost = None
        show_cost = False
    if nut or cost:
        presentation = dict(presentation)
        if nut:
            presentation["nutrition"] = nut
        # Intentionally omit cost from presentation used by result cards.
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
        "cost": cost if show_cost else None,
        "show_cost": bool(show_cost and cost),
        "meal_budget": ctx.get("meal_budget"),
        "accepted": sess.accepted,
        "session": sess.public(),
    }


@router.post("/execute/merge-list")
def merge_list(body: MergeBody, sess: SessionDep) -> dict:
    apply_auth(sess)
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    did = sess.decision_id or sess.current.get("decision_id")
    if not did:
        raise HTTPException(status_code=400, detail="Saknar decision_id.")
    ctx = sess.current.get("context") or {}
    shopping = ctx.get("shopping") or {}
    to_buy = shopping.get("to_buy") or {}
    # Always filter by checked names. Empty list must add nothing (not everything).
    want = {str(n).lower() for n in (body.item_names or [])}
    filtered: dict[str, list[str]] = {}
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
