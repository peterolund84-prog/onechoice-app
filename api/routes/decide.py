# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.deps import SessionDep
from api.services import decide_service as ds
from api.session_store import STORE

router = APIRouter(prefix="/api", tags=["decide"])


class DecideBody(BaseModel):
    question: str = ""
    domain_hint: str | None = None
    via_router: bool = False
    reroll: bool = False
    context_extra: dict[str, Any] = Field(default_factory=dict)


class MealBody(BaseModel):
    meal_type: str


class OccasionBody(BaseModel):
    occasion: str
    question: str = ""


class MovieChipsBody(BaseModel):
    format: str | None = None
    mood: str | None = None
    mode: str | None = None


@router.post("/decide")
def decide(body: DecideBody, sess: SessionDep) -> dict:
    out = ds.run_decide(
        sess,
        question=body.question,
        domain_hint=body.domain_hint,
        via_router=body.via_router,
        reroll=body.reroll,
        context_extra=body.context_extra,
    )
    STORE.save(sess)
    return out


@router.post("/decide/reroll")
def reroll(sess: SessionDep) -> dict:
    cur = sess.current if isinstance(sess.current, dict) else {}
    domain = sess.last_domain_hint or cur.get("domain")
    out = ds.run_decide(
        sess,
        question=sess.last_question or "",
        domain_hint=domain,
        via_router=False,
        reroll=True,
        context_extra={},
    )
    STORE.save(sess)
    return out


@router.post("/decide/meal-type")
def meal_type(body: MealBody, sess: SessionDep) -> dict:
    sess.food_meal_type = body.meal_type
    out = ds.run_decide(
        sess,
        question="",
        domain_hint="food",
        via_router=False,
        reroll=False,
        context_extra={"meal_type": body.meal_type},
    )
    STORE.save(sess)
    return out


@router.post("/decide/clothes-occasion")
def clothes_occasion(body: OccasionBody, sess: SessionDep) -> dict:
    sess.clothes_occasion = body.occasion
    out = ds.run_decide(
        sess,
        question=body.question or sess.last_question or "",
        domain_hint="clothes",
        via_router=False,
        reroll=False,
        context_extra={"occasion": body.occasion},
    )
    STORE.save(sess)
    return out


@router.post("/decide/movie-chips")
def movie_chips(body: MovieChipsBody, sess: SessionDep) -> dict:
    """Update format / mood / Trendar-nu mode and re-decide."""
    import movie_domain as md

    extra: dict[str, Any] = {}
    if body.format:
        sess.movie_format = md.normalize_format(body.format)
        extra["format"] = sess.movie_format
    if body.mood:
        sess.movie_mood = md.normalize_mood(body.mood)
        extra["mood"] = sess.movie_mood
        # Picking a mood returns to mood-matching unless mode is explicitly set.
        if body.mode is None:
            sess.movie_mode = "mood"
            extra["mode"] = "mood"
    if body.mode is not None:
        sess.movie_mode = md.normalize_mode(body.mode)
        extra["mode"] = sess.movie_mode
    if sess.movie_format and "format" not in extra:
        extra["format"] = sess.movie_format
    if sess.movie_mood and "mood" not in extra:
        extra["mood"] = sess.movie_mood
    if sess.movie_mode and "mode" not in extra:
        extra["mode"] = sess.movie_mode
    out = ds.run_decide(
        sess,
        question=sess.last_question or "",
        domain_hint="movie",
        via_router=False,
        reroll=False,
        context_extra=extra,
    )
    STORE.save(sess)
    return out
