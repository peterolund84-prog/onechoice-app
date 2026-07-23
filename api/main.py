# -*- coding: utf-8 -*-
"""FastAPI entry — production UI is React (`web/`). Streamlit `app.py` is legacy."""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from api.deps import boot_db_guest, ensure_guest_user
from api.home import infer_home_hero

app = FastAPI(title="OneChoice API", version="0.2.0")

_DEFAULT_ORIGINS = (
    "http://localhost:5173,"
    "http://127.0.0.1:5173,"
    "http://192.168.1.114:5173"
)

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
    return {"status": "ok"}


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
