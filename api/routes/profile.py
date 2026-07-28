# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

import db
import food_budget as fbud
from api.deps import SessionDep, apply_auth
from api.secrets import grok_api_key, secrets_status, supabase_configured, tmdb_api_key
from api.session_store import STORE

router = APIRouter(prefix="/api/profile", tags=["profile"])

BUILD_ID = "html-quality-pwa-v21-20260726"


def _load_profile_json(user: dict[str, Any]) -> dict[str, Any]:
    raw = user.get("profile_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return dict(raw) if isinstance(raw, dict) else {}


def _food_prefs(user: dict[str, Any]) -> dict[str, Any]:
    food = dict(_load_profile_json(user).get("food") or {})
    show_nutrition = bool(food["show_nutrition"]) if "show_nutrition" in food else True
    meal_budget = fbud.normalize_meal_budget(food.get("meal_budget", fbud.BUDGET_ANY))
    return {
        "show_nutrition": show_nutrition,
        "meal_budget": meal_budget,
        "meal_budget_label": fbud.budget_label(meal_budget, "sv"),
        "meal_budget_options": [
            {"id": fbud.BUDGET_ANY, "label": fbud.budget_label(fbud.BUDGET_ANY, "sv")},
            {
                "id": fbud.BUDGET_BILLIGT,
                "label": fbud.budget_label(fbud.BUDGET_BILLIGT, "sv"),
                "ceiling_sek": fbud.CEILING_SEK[fbud.BUDGET_BILLIGT],
            },
            {
                "id": fbud.BUDGET_SNALT,
                "label": fbud.budget_label(fbud.BUDGET_SNALT, "sv"),
                "ceiling_sek": fbud.CEILING_SEK[fbud.BUDGET_SNALT],
            },
        ],
    }


class ProfilePatch(BaseModel):
    show_nutrition: bool | None = None
    meal_budget: str | None = Field(default=None, max_length=40)


@router.get("")
def profile(sess: SessionDep) -> dict:
    apply_auth(sess)
    st = secrets_status()
    key = grok_api_key()
    if not key:
        ai = "offline — API-nyckel saknas"
    elif key.lower().startswith("xai-") and "din_" not in key.lower():
        ai = "online"
    else:
        ai = "offline — ogiltig nyckel"
    tmdb = bool(tmdb_api_key()) or bool(st.get("tmdb_configured"))
    sb = supabase_configured() or bool(st.get("supabase_configured"))
    user = db.ensure_user(sess.user_id, language=sess.language or "sv")
    food = _food_prefs(user)
    return {
        "email": sess.email,
        "guest_mode": sess.guest_mode,
        "language": sess.language,
        "is_pro": False,
        "ai_status": ai,
        "supabase_configured": sb,
        "tmdb_configured": tmdb,
        "secrets": st,
        "food": food,
        "show_nutrition": food["show_nutrition"],
        "meal_budget": food["meal_budget"],
        "integrations": {
            "supabase": (
                "ok"
                if sb
                else (
                    "saknas — ingen secrets.toml lokalt"
                    if not st.get("secrets_file_found")
                    else "saknas — SUPABASE_URL/KEY i secrets.toml"
                )
            ),
            "tmdb": (
                "ok"
                if tmdb
                else "saknas — valfritt; posters funkar via TVMaze utan nyckel"
            ),
            "grok": ai,
            "secrets_file": st.get("secrets_file") or "ej hittad",
        },
        "build": BUILD_ID,
        "stack": "html+fastapi",
        "session": sess.public(),
    }


@router.patch("")
def patch_profile(body: ProfilePatch, sess: SessionDep) -> dict:
    """Update food prefs: show_nutrition + meal_budget (grouped)."""
    apply_auth(sess)
    user = db.ensure_user(sess.user_id, language=sess.language or "sv")
    raw = _load_profile_json(user)
    food = dict(raw.get("food") or {})
    if body.show_nutrition is not None:
        food["show_nutrition"] = bool(body.show_nutrition)
    if body.meal_budget is not None:
        food["meal_budget"] = fbud.normalize_meal_budget(body.meal_budget)
    raw["food"] = food
    db.update_user(sess.user_id, profile_json=raw)
    STORE.save(sess)
    prefs = _food_prefs(db.ensure_user(sess.user_id, language=sess.language or "sv"))
    return {"ok": True, "food": prefs, **prefs}
