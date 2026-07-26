# -*- coding: utf-8 -*-
"""Port of app.run_decision — no Streamlit."""

from __future__ import annotations

from typing import Any

import food_domain as fd
import pipeline
from api.presentation import enrich_decision
from api.secrets import grok_api_key
from api.session_store import Session


def infer_hero(language: str = "sv") -> dict[str, Any]:
    now = fd.local_now() if hasattr(fd, "local_now") else None
    meal_type = fd.default_meal_type(now=now) if now else fd.default_meal_type()
    meal_name = fd.meal_headline(meal_type, language)
    is_weekend = False
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        local = now or datetime.now(ZoneInfo("Europe/Stockholm"))
        is_weekend = local.weekday() >= 5
    except Exception:
        pass
    return {
        "headline": "Vad ska vi bestämma idag?",
        "meal_headline": f"{meal_name}?",
        "domain": "food",
        "meal_type": meal_type,
        "weekend_alternate": is_weekend,
        "weekend_headline": "Resor?",
    }


DOMAIN_CARDS = [
    {
        "id": "food",
        "label": "Mat",
        "sub": "Frukost, lunch, middag & mer",
        "icon": "utensils",
    },
    {
        "id": "clothes",
        "label": "Kläder",
        "sub": "Outfit, skor & accessoarer",
        "icon": "hanger",
    },
    {
        "id": "movie",
        "label": "Film & serier",
        "sub": "Hitta något värt att se",
        "icon": "clapper",
    },
    {
        "id": "workout",
        "label": "Träning",
        "sub": "Pass, övningar & motivation",
        "icon": "dumbbell",
    },
    {
        "id": "weekend",
        "label": "Resor",
        "sub": "Weekend, destination & aktiviteter",
        "icon": "suitcase",
    },
    {
        "id": "gifts",
        "label": "Presenter",
        "sub": "Till någon du bryr dig om",
        "icon": "gift",
    },
]


def run_decide(
    sess: Session,
    *,
    question: str = "",
    domain_hint: str | None = None,
    via_router: bool = False,
    reroll: bool = False,
    context_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import db

    db.init_db()
    if sess.guest_mode:
        db.clear_auth()
    else:
        db.set_auth(sess.access_token, sess.refresh_token)

    lang = sess.language or "sv"
    ctx = dict(context_extra or {})

    # Session defaults into context
    if domain_hint == "food" or ctx.get("meal_type"):
        meal = ctx.get("meal_type") or sess.food_meal_type or fd.default_meal_type()
        if meal in fd.MEAL_TYPES:
            sess.food_meal_type = meal
            ctx["meal_type"] = meal
    if domain_hint == "clothes" and sess.clothes_occasion:
        ctx.setdefault("occasion", sess.clothes_occasion)
    if domain_hint == "movie":
        if sess.movie_format:
            ctx.setdefault("format", sess.movie_format)
        if sess.movie_mood:
            ctx.setdefault("mood", sess.movie_mood)

    if domain_hint == "gifts":
        domain_hint = "other"
        via_router = False
        if not question:
            question = "Vilken present ska jag ge?" if lang == "sv" else "What gift should I get?"

    # Clothes needs occasion first
    if domain_hint == "clothes" and not sess.clothes_occasion and not ctx.get("occasion"):
        sess.last_domain_hint = "clothes"
        sess.last_question = question or pipeline._default_question("clothes", lang)
        sess.force_chooser = False
        return {
            "ok": True,
            "page": "clothes_occasion",
            "decision": None,
            "session": sess.public(),
            "occasions": ["jobb", "vardag", "träning", "dejt", "fest"],
        }

    q = (question or "").strip()
    if not q and domain_hint and domain_hint not in (None, "other"):
        q = pipeline._default_question(domain_hint, lang)
    if not q and domain_hint == "other":
        q = pipeline._default_question("other", lang)

    key = grok_api_key()
    prev_id = sess.decision_id if reroll else None
    reroll_index = sess.reroll_index if reroll else 0
    if reroll:
        reroll_index = int(sess.reroll_index or 0)
        if sess.current and sess.current.get("suggestion"):
            ctx.setdefault("previous_suggestion", sess.current.get("suggestion"))

    skip_feasibility = domain_hint == "other"

    if via_router:
        result = pipeline.handle_free_text(
            sess.user_id,
            q,
            language=lang,
            grok_api_key=key,
            forced_domain=sess.force_route_domain,
            context_extra=ctx or None,
            reroll=reroll,
            reroll_index=reroll_index,
            previous_decision_id=prev_id,
        )
        sess.force_route_domain = None
    else:
        result = pipeline.decide(
            sess.user_id,
            q,
            domain_hint=domain_hint,
            language=lang,
            reroll=reroll,
            reroll_index=reroll_index,
            previous_decision_id=prev_id,
            context_extra=ctx or None,
            grok_api_key=key,
            skip_feasibility=skip_feasibility,
        )

    data = result.to_dict() if hasattr(result, "to_dict") else dict(result)

    # Navigation
    if getattr(result, "needs_domain_pick", False) or data.get("needs_domain_pick"):
        page = "ambiguous"
    elif getattr(result, "refused", False) or data.get("refused"):
        page = "refused"
    elif data.get("ui_message") and not data.get("ok", True):
        page = "not_a_decision"
    else:
        page = "result"

    sess.current = data
    sess.decision_id = data.get("decision_id")
    sess.accepted = False
    sess.reroll_index = int(data.get("reroll_index") or 0)
    sess.last_question = q
    sess.last_domain_hint = data.get("domain") or domain_hint
    sess.route_log_id = data.get("route_log_id")
    sess.force_chooser = False

    return {
        "ok": bool(data.get("ok", True)),
        "page": page,
        "decision": enrich_decision(data),
        "session": sess.public(),
    }
