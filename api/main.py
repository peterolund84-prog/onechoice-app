# -*- coding: utf-8 -*-
"""FastAPI entry — production UI is React (`web/`). Streamlit `app.py` is legacy."""

from __future__ import annotations

import os
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from api.home import infer_home_hero

app = FastAPI(title="OneChoice API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("OC_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DecideBody(BaseModel):
    question: str = ""
    domain_hint: str | None = None
    meal_type: str | None = None
    language: str = "sv"
    user_id: str | None = None
    reroll: bool = False


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/home")
def home(language: str = "sv") -> dict[str, Any]:
    if language not in ("sv", "en"):
        language = "sv"
    return infer_home_hero(language=language)


@app.post("/v1/decide")
def decide(body: DecideBody) -> dict[str, Any]:
    """Run the existing Python decision pipeline (guest user if none provided)."""
    import db
    import food_domain as fd
    import pipeline

    user_id = (body.user_id or "").strip() or f"guest-{uuid.uuid4().hex[:12]}"
    try:
        db.init_db()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"db init failed: {exc}") from exc

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
def decide_free_text(body: FreeTextBody) -> dict[str, Any]:
    return decide(
        DecideBody(
            question=body.question.strip(),
            domain_hint=None,
            language=body.language,
            user_id=body.user_id,
        )
    )
