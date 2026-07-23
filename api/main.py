# -*- coding: utf-8 -*-
"""FastAPI entry — production UI is React (`web/`). Streamlit `app.py` is legacy."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from api.deps import apply_auth_tokens, boot_db_guest, ensure_guest_user
from api.home import infer_home_hero

app = FastAPI(title="OneChoice API", version="0.3.0")

_DEFAULT_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://192.168.1.114:5173,"
    "http://localhost:5174,"
    "http://127.0.0.1:5174,"
    "http://192.168.1.114:5174"
)

class _SupabaseAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        apply_auth_tokens(
            request.headers.get("X-Access-Token"),
            request.headers.get("X-Refresh-Token"),
        )
        return await call_next(request)


# Auth first (inner), CORS last (outer) so preflight always gets headers.
app.add_middleware(_SupabaseAuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv("OC_CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
        if o.strip()
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _uid(
    body_user_id: str | None = None,
    x_user_id: str | None = None,
) -> str:
    uid = (body_user_id or x_user_id or "").strip()
    return uid or f"guest-{uuid.uuid4().hex[:12]}"


# ── health / home ────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "build": "dish-embed-v2"}


@app.get("/v1/media/dish")
def dish_media(
    title: str = Query(..., min_length=1, max_length=200),
    hint: str | None = Query(default=None),
) -> FileResponse:
    """Serve a resolved dish JPEG from assets/dishes (or 404 → client placeholder)."""
    import dish_images as dimg

    path = dimg.resolve_dish_image(title, hint)
    if not path:
        raise HTTPException(status_code=404, detail="no dish image")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/v1/home")
def home(language: str = "sv") -> dict[str, Any]:
    if language not in ("sv", "en"):
        language = "sv"
    return infer_home_hero(language=language)


# ── decide ───────────────────────────────────────────────────────────────────


class DecideBody(BaseModel):
    question: str = ""
    domain_hint: str | None = None
    meal_type: str | None = None
    format: str | None = None
    mood: str | None = None
    in_progress_series: str | None = None
    occasion: str | None = None
    intent: str | None = None
    source: str | None = None
    available_ingredients: list[str] | None = None
    language: str = "sv"
    user_id: str | None = None
    reroll: bool = False
    reroll_index: int = 0
    previous_decision_id: int | None = None


@app.post("/v1/decide")
def decide(
    body: DecideBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Run the existing Python decision pipeline (guest user if none provided)."""
    import food_domain as fd
    import pipeline

    user_id = _uid(body.user_id, x_user_id)
    ensure_guest_user(user_id, language=body.language)

    context_extra: dict[str, Any] = {}
    if body.meal_type and body.meal_type in getattr(fd, "MEAL_TYPES", ()):
        context_extra["meal_type"] = body.meal_type
    if body.format:
        context_extra["format"] = body.format
    if body.mood:
        context_extra["mood"] = body.mood
    if body.in_progress_series:
        context_extra["in_progress_series"] = body.in_progress_series
    if body.occasion:
        context_extra["occasion"] = body.occasion
    if body.intent:
        context_extra["intent"] = body.intent
    if body.source:
        context_extra["source"] = body.source
    if body.available_ingredients:
        context_extra["available_ingredients"] = [
            str(x).strip() for x in body.available_ingredients if str(x).strip()
        ]

    try:
        result = pipeline.decide(
            user_id,
            body.question or "",
            domain_hint=body.domain_hint,
            language=body.language,
            reroll=body.reroll,
            reroll_index=body.reroll_index,
            previous_decision_id=body.previous_decision_id,
            context_extra=context_extra or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    payload["user_id"] = user_id

    # Embed dish image so mobile Resultat never depends on a second media fetch.
    if payload.get("domain") == "food":
        try:
            import dish_images as dimg

            ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}
            hint = ctx.get("dish_category") or ctx.get("category")
            b64 = dimg.resolve_dish_image_b64(
                str(payload.get("suggestion") or ""),
                str(hint) if hint else None,
            )
            if b64:
                payload["image_data_url"] = f"data:image/jpeg;base64,{b64}"
        except Exception:
            pass

    return payload


class FreeTextBody(BaseModel):
    question: str = Field(..., min_length=1, max_length=200)
    language: str = "sv"
    user_id: str | None = None


@app.post("/v1/decide/free-text")
def decide_free_text(
    body: FreeTextBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    return decide(
        DecideBody(
            question=body.question.strip(),
            domain_hint=None,
            language=body.language,
            user_id=body.user_id or x_user_id,
        ),
        x_user_id=x_user_id,
    )


# ── decisions / historik / resultat actions ──────────────────────────────────


class AcceptBody(BaseModel):
    user_id: str | None = None
    route_log_id: int | None = None


@app.post("/v1/decisions/{decision_id}/accept")
def accept_decision(
    decision_id: int,
    body: AcceptBody | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import pipeline

    body = body or AcceptBody()
    user_id = _uid(body.user_id, x_user_id)
    ensure_guest_user(user_id)
    out = pipeline.try_accept_decision(
        decision_id, route_log_id=body.route_log_id
    )
    if out is None:
        return {"ok": False, "decision_id": decision_id, "accepted": False}
    return {"ok": True, "accepted": True, "decision": out, "user_id": user_id}


class FavoriteBody(BaseModel):
    favorite: bool
    user_id: str | None = None


@app.post("/v1/decisions/{decision_id}/favorite")
def favorite_decision(
    decision_id: int,
    body: FavoriteBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    user_id = _uid(body.user_id, x_user_id)
    ensure_guest_user(user_id)
    try:
        row = db.set_decision_favorite(decision_id, body.favorite)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "decision": row, "user_id": user_id}


@app.get("/v1/decisions")
def list_decisions(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    favorite: bool | None = None,
    domain: str | None = None,
    status: str | None = None,
    limit: int = Query(default=80, ge=1, le=200),
) -> dict[str, Any]:
    import db

    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    ensure_guest_user(uid)
    rows = db.list_decisions(
        uid,
        domain=domain,
        status=status,
        favorite=favorite,
        limit=limit,
    )
    return {"items": rows, "user_id": uid}


@app.get("/v1/decisions/{decision_id}")
def get_decision(
    decision_id: int,
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    ensure_guest_user(uid)
    rows = db.list_decisions(uid, limit=200)
    for row in rows:
        if int(row.get("id") or 0) == int(decision_id):
            return {"decision": row, "user_id": uid}
    raise HTTPException(status_code=404, detail="decision not found")


# ── shopping / lista ─────────────────────────────────────────────────────────


@app.get("/v1/shopping")
def get_shopping(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    ensure_guest_user(uid)
    try:
        db.purge_stale_checked_shopping_items(uid, hours=24)
    except Exception:
        pass
    items = db.list_shopping_items(uid)
    return {"items": items, "user_id": uid}


class AddShoppingBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    user_id: str | None = None


@app.post("/v1/shopping")
def add_shopping(
    body: AddShoppingBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    uid = _uid(body.user_id, x_user_id)
    ensure_guest_user(uid)
    row = db.add_manual_shopping_item(uid, body.name)
    if row is None:
        raise HTTPException(status_code=400, detail="invalid name")
    return {"item": row, "user_id": uid}


class ToggleShoppingBody(BaseModel):
    checked: bool
    user_id: str | None = None


@app.patch("/v1/shopping/{item_id}")
def toggle_shopping(
    item_id: int,
    body: ToggleShoppingBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    uid = _uid(body.user_id, x_user_id)
    ensure_guest_user(uid)
    row = db.toggle_shopping_item(uid, item_id, body.checked)
    if row is None:
        raise HTTPException(status_code=404, detail="item not found")
    return {"item": row, "user_id": uid}


class ClearCheckedBody(BaseModel):
    user_id: str | None = None
    item_ids: list[int] | None = None


@app.delete("/v1/shopping/checked")
def clear_checked_shopping(
    body: ClearCheckedBody | None = None,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    body = body or ClearCheckedBody()
    uid = _uid(body.user_id, x_user_id)
    ensure_guest_user(uid)
    deleted = 0
    if body.item_ids:
        deleted = db.delete_shopping_items(uid, body.item_ids)
    deleted += db.clear_checked_shopping_items(uid)
    return {"deleted": deleted, "user_id": uid}


class MergeShoppingBody(BaseModel):
    user_id: str | None = None
    decision_id: int | None = None
    to_buy: dict[str, Any] | None = None


@app.post("/v1/shopping/merge")
def merge_shopping(
    body: MergeShoppingBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    uid = _uid(body.user_id, x_user_id)
    ensure_guest_user(uid)
    added = db.merge_shopping_from_decision(uid, body.decision_id, body.to_buy)
    return {"added": added, "count": len(added), "user_id": uid}


@app.get("/v1/shopping/share-text", response_class=PlainTextResponse)
def shopping_share_text(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    language: str = "sv",
) -> str:
    import db
    import share_domain

    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    ensure_guest_user(uid)
    items = db.list_shopping_items(uid)
    return share_domain.format_list_share_text(items, language=language)


# ── auth (Supabase) ──────────────────────────────────────────────────────────


class AuthBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=200)
    language: str = "sv"
    privacy_consent: bool = False


class RefreshBody(BaseModel):
    refresh_token: str = Field(..., min_length=10)


@app.get("/v1/auth/status")
def auth_status() -> dict[str, Any]:
    import supabase_client as sb

    return {"configured": bool(sb.is_configured())}


@app.post("/v1/auth/login")
def auth_login(body: AuthBody) -> dict[str, Any]:
    import supabase_client as sb

    if not sb.is_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    try:
        sess = sb.sign_in(body.email.strip(), body.password)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    uid = str(sess.get("user_id") or "")
    if uid:
        apply_auth_tokens(sess.get("access_token"), sess.get("refresh_token"))
        ensure_guest_user(uid, language=body.language)
    return {"ok": True, **sess}


@app.post("/v1/auth/signup")
def auth_signup(body: AuthBody) -> dict[str, Any]:
    import supabase_client as sb

    if not sb.is_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    if not body.privacy_consent:
        raise HTTPException(status_code=400, detail="privacy consent required")
    try:
        sess = sb.sign_up(body.email.strip(), body.password, language=body.language)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    uid = str(sess.get("user_id") or "")
    if uid and sess.get("access_token") and sess.get("refresh_token"):
        apply_auth_tokens(sess.get("access_token"), sess.get("refresh_token"))
        ensure_guest_user(uid, language=body.language)
    return {"ok": True, **sess}


@app.post("/v1/auth/refresh")
def auth_refresh(body: RefreshBody) -> dict[str, Any]:
    import supabase_client as sb

    if not sb.is_configured():
        raise HTTPException(status_code=503, detail="Supabase is not configured")
    try:
        sess = sb.refresh_session(body.refresh_token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    uid = str(sess.get("user_id") or "")
    if uid:
        apply_auth_tokens(sess.get("access_token"), sess.get("refresh_token"))
        ensure_guest_user(uid)
    return {"ok": True, **sess}


@app.post("/v1/auth/logout")
def auth_logout(
    x_access_token: str | None = Header(default=None, alias="X-Access-Token"),
    x_refresh_token: str | None = Header(default=None, alias="X-Refresh-Token"),
) -> dict[str, Any]:
    import supabase_client as sb

    try:
        sb.sign_out(x_access_token, x_refresh_token)
    except Exception:
        pass
    boot_db_guest()
    return {"ok": True}


# ── domain options / execute heal ────────────────────────────────────────────


@app.get("/v1/meta/domains")
def domain_meta(language: str = "sv") -> dict[str, Any]:
    import clothes_domain as cd
    import food_domain as fd
    import movie_domain as md

    if language not in ("sv", "en"):
        language = "sv"
    meals = [
        {"id": m, "label": fd.meal_type_label(m, language) if hasattr(fd, "meal_type_label") else m}
        for m in getattr(fd, "MEAL_TYPES", ("frukost", "lunch", "middag", "kvallsmal"))
    ]
    # Fallback Swedish labels if helper missing
    meal_labels = {
        "frukost": "Frukost",
        "lunch": "Lunch",
        "middag": "Middag",
        "kvallsmal": "Kvällsmål",
    }
    meals = [{"id": m["id"], "label": meal_labels.get(m["id"], m["label"])} for m in meals]
    formats = [
        {"id": k, "label": md.format_label(k, language)} for k in md.FORMAT_ORDER
    ]
    moods = [{"id": k, "label": md.mood_label(k, language)} for k in md.MOOD_ORDER]
    occasions = [
        {"id": k, "label": cd.occasion_label(k, language)} for k in cd.OCCASION_ORDER
    ]
    return {
        "meals": meals,
        "formats": formats,
        "moods": moods,
        "occasions": occasions,
        "default_occasion": cd.default_occasion(__import__("datetime").datetime.now().hour),
    }


class ExecuteFoodBody(BaseModel):
    user_id: str | None = None
    suggestion: str = ""
    meal_type: str | None = "middag"
    context: dict[str, Any] | None = None


@app.post("/v1/execute/food")
def execute_food(
    body: ExecuteFoodBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Heal/materialize recipe + shopping for the execute surface (local catalog)."""
    import shopping as shopping_mod
    import shopping_compat as shop_compat

    uid = _uid(body.user_id, x_user_id)
    ensure_guest_user(uid)
    ctx = dict(body.context or {})
    suggestion = str(body.suggestion or ctx.get("title") or "").strip()
    meal_type = str(body.meal_type or ctx.get("meal_type") or "middag")
    recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
    shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
    if not recipe and shop and isinstance(shop.get("recipe"), dict):
        recipe = shop.get("recipe")

    seed_ings: list[str] = []
    if isinstance(recipe, dict):
        seed_ings = [
            str(x)
            for x in (recipe.get("ingredient_lines") or recipe.get("ingredients") or [])
        ]
    try:
        bundled_recipe, bundled_shop = shop_compat.resolve_meal_bundle(
            suggestion,
            meta={"meal_type": meal_type, "ingredients": seed_ings},
            meal_type=meal_type,
            language="sv",
            grok_api_key="",
            include_shopping=True,
        )
        if bundled_recipe and (
            not isinstance(recipe, dict) or not recipe.get("steps")
        ):
            recipe = bundled_recipe
        if bundled_shop and not shop:
            shop = bundled_shop
    except Exception:
        pass

    if isinstance(recipe, dict):
        try:
            recipe = shopping_mod.ensure_recipe_nutrition(
                recipe, suggestion=suggestion, allow_estimate=True
            )
        except Exception:
            pass

    return {
        "ok": True,
        "suggestion": suggestion,
        "meal_type": meal_type,
        "recipe": recipe,
        "shopping": shop,
        "user_id": uid,
    }


# ── profile ──────────────────────────────────────────────────────────────────


@app.get("/v1/me")
def get_me(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    language: str = "sv",
) -> dict[str, Any]:
    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    user = ensure_guest_user(uid, language=language)
    # Parse JSON fields for clients
    out = dict(user)
    for key in ("profile_json", "dietary_json", "wardrobe_json"):
        raw = out.get(key)
        if isinstance(raw, str):
            try:
                out[key] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    out["guest"] = str(uid).startswith("guest-")
    return {"user": out, "user_id": uid}


class PatchMeBody(BaseModel):
    user_id: str | None = None
    language: str | None = None
    is_pro: int | None = None
    profile_json: dict[str, Any] | None = None


@app.patch("/v1/me")
def patch_me(
    body: PatchMeBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import db

    uid = _uid(body.user_id, x_user_id)
    ensure_guest_user(uid)
    fields: dict[str, Any] = {}
    if body.language is not None:
        fields["language"] = body.language
    if body.is_pro is not None:
        fields["is_pro"] = int(body.is_pro)
    if body.profile_json is not None:
        fields["profile_json"] = json.dumps(body.profile_json, ensure_ascii=False)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")
    user = db.update_user(uid, **fields)
    return {"user": user, "user_id": uid}


@app.get("/v1/me/export")
def export_me(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> JSONResponse:
    import gdpr

    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    ensure_guest_user(uid)
    data = gdpr.export_user_data(uid)
    return JSONResponse(content=data)


@app.delete("/v1/me")
def delete_me(
    user_id: str | None = Query(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    import gdpr

    uid = (user_id or x_user_id or "").strip()
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    boot_db_guest()
    gdpr.delete_user_account(uid)
    return {"ok": True, "deleted_user_id": uid}
