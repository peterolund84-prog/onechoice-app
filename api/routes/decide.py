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
    out = ds.run_decide(
        sess,
        question=sess.last_question or "",
        domain_hint=sess.last_domain_hint,
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
