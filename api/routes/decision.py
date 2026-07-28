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
            recipe = fbud.ensure_recipe_cost(
                recipe,
                meta=meta,
                allow_estimate=True,
                meal_type=ctx.get("meal_type"),
            )
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
            cost = fbud.cost_stat(
                recipe,
                language=sess.language or "sv",
                meal_type=ctx.get("meal_type"),
            )
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


@router.post("/dish-image")
def resolve_dish_image(sess: SessionDep) -> dict:
    """Lazy AI dish image — must never break the decision.

    Fallback chain: AI → local keyword → placeholder. On any failure returns
    placeholder with ok=True so the card keeps working.
    """
    apply_auth(sess)
    if not sess.current:
        raise HTTPException(status_code=404, detail="Ingen aktiv beslut.")
    cur = dict(sess.current)
    if str(cur.get("domain") or "") != "food":
        # Soft no-op — don't 400-crash the client upgrade path
        return {
            "ok": True,
            "url": None,
            "source": "placeholder",
            "pending": False,
        }
    ctx = dict(cur.get("context") or {})
    suggestion = str(cur.get("suggestion") or "")
    if not suggestion:
        return {
            "ok": True,
            "url": None,
            "source": "placeholder",
            "pending": False,
        }
    # Already have a validated AI (or display) URL — no need to search again.
    existing_display = ctx.get("dish_image_url") or ctx.get("image_display_url")
    existing_source = ctx.get("dish_image_source") or ctx.get("image_source")
    if (
        existing_source == "ai"
        and isinstance(existing_display, str)
        and existing_display.startswith("/api/media/")
    ):
        return {
            "ok": True,
            "url": existing_display,
            "source": "ai",
            "pending": False,
        }

    url = None
    source = "placeholder"
    remote = None
    try:
        import food_image_search as fis
        from api.secrets import grok_api_key

        key = (grok_api_key() or "").strip()
        # If AI search was disabled for this process, skip it entirely.
        prefer_ai = bool(key) and fis.ai_image_search_enabled()
        hint = ctx.get("dish_category") or ctx.get("category")
        recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else {}
        existing_remote = (
            (recipe.get("image_url") if isinstance(recipe, dict) else None)
            or ctx.get("image_url")
        )
        resolved = fis.resolve_food_image(
            suggestion,
            str(hint) if hint else None,
            api_key=key if prefer_ai else "",
            recipe_image_url=str(existing_remote).strip()
            if isinstance(existing_remote, str) and existing_remote.strip()
            else None,
            prefer_ai=prefer_ai,
        )
        if isinstance(resolved, dict):
            url = resolved.get("url")
            source = str(resolved.get("source") or "placeholder")
            remote = resolved.get("remote_url")
    except Exception as exc:
        import logging

        logging.getLogger("onechoice.decision").warning(
            "dish-image resolve failed: %s", exc
        )
        url = None
        source = "placeholder"
        remote = None

    try:
        # Persist onto session decision so execute/share reuse it.
        recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else {}
        ctx["dish_image_url"] = url
        ctx["dish_image_source"] = source
        ctx["image_display_url"] = url
        ctx["image_source"] = source
        ctx["image_pending"] = False
        if remote:
            ctx["image_url"] = remote
        if isinstance(recipe, dict):
            recipe = dict(recipe)
            if remote:
                recipe["image_url"] = remote
            recipe["image_source"] = source
            recipe["image_display_url"] = url
            recipe["image_pending"] = False
            ctx["recipe"] = recipe
            shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
            if shop is not None:
                shop = dict(shop)
                shop["recipe"] = recipe
                ctx["shopping"] = shop
        cur["context"] = ctx
        sess.current = cur
        STORE.save(sess)
        did = sess.decision_id or cur.get("decision_id")
        if did:
            try:
                update = getattr(db, "update_decision_context", None)
                if callable(update):
                    update(int(did), ctx)
            except Exception:
                pass
    except Exception:
        pass

    return {
        "ok": True,
        "url": url,
        "source": source,
        "pending": False,
        "presentation": {
            "dish_image_url": url,
            "dish_image_source": source,
            "image_pending": False,
        },
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
