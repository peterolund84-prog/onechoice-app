# -*- coding: utf-8 -*-
"""
OneChoice decision pipeline.

Shared flow (all domains):
  question → classify domain → profile + context + history
  → LLM/local generates ~5 candidates
  → feasibility_check (domain validator) — discard failures, never show broken decisions
  → rank survivors (80% close to accepted history, 20% wildcard/"Vildkort")
  → display ONE + one-line justification + execution step

Repetition guard: 7 days per domain. Max 3 rerolls, then lock.
"""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import requests

import db
import feasibility

log = logging.getLogger("onechoice.pipeline")

MAX_REROLLS = 3
REPEAT_DAYS = 7
SAFE_RATIO = 0.80  # bandit: 80% safe / 20% explore (wildcard)

ALLOWED_DOMAINS = db.DOMAINS  # food, clothes, movie, workout, weekend

HIGH_STAKES_KEYWORDS = (
    "jobb", "karriär", "karriar", "career", "anställ", "anstall", "säga upp", "saga upp",
    "relation", "dejt", "dejta", "relationship", "breakup", "göra slut", "gora slut",
    "gift", "äktenskap", "aktenskap", "money", "pengar", "investera", "aktie", "krypto",
    "lån", "lan", "skuld", "hälsa", "halsa", "health", "diagnos", "läkare", "lakare",
    "medicin", "operation", "suicid", "depression",
)

DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "food": (
        "äta", "ata", "mat", "lunch", "middag", "frukost", "hungrig", "restaurang",
        "recept", "matlag", "eat", "food", "dinner", "breakfast", "cook", "thai", "sushi",
    ),
    "clothes": (
        "kläd", "klad", "outfit", "skor", "på mig", "pa mig", "ha på", "ha pa",
        "clothes", "wear", "fashion", "tröja", "troja", "jeans",
    ),
    "movie": (
        "film", "serie", "netflix", "movie", "watch", "streaming", "bio", "series",
        "tv-show", "tv show",
    ),
    "workout": (
        "träna", "trana", "workout", "gym", "löpa", "lopa", "yoga", "pass", "exercise",
        "styrka", "cardio",
    ),
    "weekend": (
        "helg", "weekend", "lördag", "lordag", "söndag", "sondag", "utflykt", "aktivitet",
        "saturday", "sunday", "planera helgen",
    ),
}

REFUSAL_COPY = {
    "sv": "Onechoice tar vardagsbesluten. Det här beslutet är ditt.",
    "en": "Onechoice handles everyday decisions. This one is yours.",
}


@dataclass
class DecisionResult:
    ok: bool
    domain: str | None
    suggestion: str
    justification: str
    execution_type: str | None = None
    execution_label: str | None = None
    execution_url: str | None = None
    decision_id: int | None = None
    reroll_index: int = 0
    locked: bool = False
    refused: bool = False
    refusal_message: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    explore: bool = False
    # Router outcome (free-text path)
    route: str | None = None
    route_log_id: int | None = None
    ui_message: str | None = None  # NOT_A_DECISION copy etc.
    needs_domain_pick: bool = False  # AMBIGUOUS

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_domain(question: str, hint: str | None = None) -> str | None:
    """Return allowed domain, 'refused' for high-stakes, or None if unknown."""
    if hint in ALLOWED_DOMAINS:
        return hint
    q = (question or "").lower()
    if any(k in q for k in HIGH_STAKES_KEYWORDS):
        return "refused"
    for domain, words in DOMAIN_KEYWORDS.items():
        if any(w in q for w in words):
            return domain
    return None


def collect_context(
    user: dict[str, Any],
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now().astimezone()
    dietary = user.get("dietary_json") or "[]"
    if isinstance(dietary, str):
        try:
            dietary = json.loads(dietary)
        except json.JSONDecodeError:
            dietary = []
    ctx = {
        "time_of_day": _time_of_day(now.hour),
        "weekday": now.strftime("%A"),
        "hour": now.hour,
        "is_weekend": now.weekday() >= 5,
        "weather": (extra or {}).get("weather", "unknown"),
        "temp_c": (extra or {}).get("temp_c"),
        "location": user.get("location") or (extra or {}).get("location") or "unknown",
        "budget": user.get("budget") or (extra or {}).get("budget") or "medium",
        "dietary": dietary,
        "language": user.get("language") or "sv",
    }
    if extra:
        ctx.update({k: v for k, v in extra.items() if v is not None})
    return ctx


def decide(
    user_id: str,
    question: str,
    *,
    domain_hint: str | None = None,
    language: str | None = None,
    reroll: bool = False,
    reroll_index: int = 0,
    previous_decision_id: int | None = None,
    context_extra: dict[str, Any] | None = None,
    grok_api_key: str = "",
    db_path: str | None = None,
    skip_feasibility: bool = False,
    route_meta: dict[str, Any] | None = None,
) -> DecisionResult:
    """
    Full decision pipeline. Returns exactly ONE decision (or a hard refusal).

    On reroll: previous decision is marked rejected (negative signal).
    After MAX_REROLLS, result is locked.

    skip_feasibility: used for NEAR_DOMAIN (generic engine, no domain validators).
    """
    db.init_db(db_path)
    if not user_id:
        raise ValueError("user_id is required")
    user = db.ensure_user(str(user_id), path=db_path)
    language = language if language in ("sv", "en") else (user.get("language") or "sv")
    if user.get("language") != language:
        try:
            db.update_user(str(user_id), language=language, path=db_path)
            user = db.ensure_user(str(user_id), path=db_path)
        except Exception as exc:
            log.warning("language update failed: %s", exc)
    q = (question or "").strip()
    if not q and domain_hint:
        q = _default_question(str(domain_hint), language)

    # Explicit near-domain / other
    if domain_hint == db.NEAR_DOMAIN or domain_hint == "other":
        domain = db.NEAR_DOMAIN
        skip_feasibility = True
    else:
        domain = classify_domain(q, domain_hint)
        if domain == "refused" or domain is None and _looks_high_stakes(q):
            return DecisionResult(
                ok=False,
                domain=None,
                suggestion="",
                justification="",
                refused=True,
                refusal_message=REFUSAL_COPY.get(language, REFUSAL_COPY["en"]),
                route=(route_meta or {}).get("route"),
                route_log_id=(route_meta or {}).get("route_log_id"),
            )
        if domain is None:
            domain = "food"  # soft default only for empty/ambiguous everyday prompts
            if q and not _looks_everyday(q) and not skip_feasibility:
                return DecisionResult(
                    ok=False,
                    domain=None,
                    suggestion="",
                    justification="",
                    refused=True,
                    refusal_message=REFUSAL_COPY.get(language, REFUSAL_COPY["en"]),
                    route=(route_meta or {}).get("route"),
                    route_log_id=(route_meta or {}).get("route_log_id"),
                )

    # Negative signal from previous shown decision
    if reroll and previous_decision_id:
        try:
            db.record_feedback(previous_decision_id, accepted=False, path=db_path)
        except Exception as exc:
            log.warning("failed to record rejection: %s", exc)

    locked = reroll_index >= MAX_REROLLS
    effective_reroll = min(reroll_index, MAX_REROLLS)

    ctx = collect_context(user, extra=context_extra)
    if domain == "clothes" and "intent" not in ctx:
        ql = q.lower()
        ctx["intent"] = "buy" if any(w in ql for w in ("köp", "beställ", "handla", "buy")) else "wear"
    if route_meta:
        ctx["route"] = route_meta.get("route")
        ctx["category_guess"] = route_meta.get("category_guess")
        ctx["normalized_question"] = route_meta.get("normalized_question")

    profile = feasibility.parse_profile(user, ctx)
    history = db.list_decisions(user_id, domain=domain, limit=40, path=db_path)
    prefs = db.get_preferences(user_id, domain, path=db_path)
    recent = db.recent_suggestions(user_id, domain, days=REPEAT_DAYS, path=db_path)

    explore = (not locked) and (random.random() > SAFE_RATIO)
    candidates = _generate_candidates(
        question=q,
        domain=domain,
        context=ctx,
        profile=profile,
        history=history,
        preferences=prefs,
        recent=recent,
        language=language,
        grok_api_key=grok_api_key,
    )

    if skip_feasibility or domain == db.NEAR_DOMAIN:
        survivors = list(candidates) or _local_candidates(
            domain, language, recent, ctx, profile
        )
    else:
        survivors = feasibility.filter_feasible(
            candidates, domain=domain, profile=profile, context=ctx
        )
        if not survivors:
            survivors = feasibility.filter_feasible(
                _local_candidates(domain, language, recent, ctx, profile),
                domain=domain,
                profile=profile,
                context=ctx,
            )
        if not survivors:
            survivors = [_guaranteed_feasible(domain, language, profile, ctx)]

    ranked = _rank_candidates(
        survivors,
        preferences=prefs,
        recent=recent,
        explore=explore,
    )
    top = ranked[0] if ranked else survivors[0]
    if explore or top.get("wildcard"):
        top = dict(top)
        top["wildcard"] = True

    justification = str(top.get("justification") or "")
    execution = top.get("execution") if isinstance(top.get("execution"), dict) else None
    if not execution:
        execution = _execution_for(
            domain, str(top.get("suggestion") or ""), language, user
        )
    suggestion = str(top.get("suggestion") or "")
    status = "locked" if locked else "shown"

    decision = db.create_decision(
        user_id=user_id,
        domain=domain,
        question=q,
        suggestion=suggestion,
        justification=justification,
        status=status,
        reroll_index=effective_reroll,
        context={
            **ctx,
            "explore": explore,
            "wildcard": bool(top.get("wildcard")),
            "candidates_n": len(candidates),
            "feasible_n": len(survivors),
            "skip_feasibility": skip_feasibility,
            "execution_detail": execution.get("detail"),
            "route_log_id": (route_meta or {}).get("route_log_id"),
        },
        execution_type=execution.get("type"),
        execution_label=execution.get("label"),
        execution_url=execution.get("url"),
        path=db_path,
    )

    if locked:
        db.upsert_preference(
            user_id,
            domain,
            "suggestion",
            suggestion.strip().lower(),
            1.5,
            path=db_path,
        )

    return DecisionResult(
        ok=True,
        domain=domain,
        suggestion=suggestion,
        justification=justification,
        execution_type=execution.get("type"),
        execution_label=execution.get("label"),
        execution_url=execution.get("url"),
        decision_id=decision["id"],
        reroll_index=effective_reroll,
        locked=locked,
        refused=False,
        context=decision.get("context") or ctx,
        explore=explore or bool(top.get("wildcard")),
        route=(route_meta or {}).get("route"),
        route_log_id=(route_meta or {}).get("route_log_id"),
    )


def handle_free_text(
    user_id: str,
    question: str,
    *,
    language: str = "sv",
    grok_api_key: str = "",
    db_path: str | None = None,
    reroll: bool = False,
    reroll_index: int = 0,
    previous_decision_id: int | None = None,
    forced_domain: str | None = None,
    prior_route_log_id: int | None = None,
) -> DecisionResult:
    """
    Gatekeeper entry for EVERY free-text input.

    forced_domain: when user picked a chip after AMBIGUOUS (incl. 'other'/annat).
    """
    import router as rt

    db.init_db(db_path)
    q = (question or "").strip()[: rt.MAX_INPUT_CHARS]
    language = language if language in ("sv", "en") else "sv"

    # Reroll of an already-routed decision: do not re-classify
    if reroll and forced_domain:
        return decide(
            user_id,
            q,
            domain_hint=forced_domain,
            language=language,
            reroll=True,
            reroll_index=reroll_index,
            previous_decision_id=previous_decision_id,
            grok_api_key=grok_api_key,
            db_path=db_path,
            skip_feasibility=(forced_domain == db.NEAR_DOMAIN),
            route_meta={
                "route": "NEAR_DOMAIN" if forced_domain == db.NEAR_DOMAIN else "IN_DOMAIN",
                "route_log_id": prior_route_log_id,
            },
        )

    if forced_domain in ALLOWED_DOMAINS or forced_domain == db.NEAR_DOMAIN:
        # User resolved AMBIGUOUS via chip / "annat"
        classification = rt.RouteResult(
            route="NEAR_DOMAIN" if forced_domain == db.NEAR_DOMAIN else "IN_DOMAIN",
            domain=forced_domain,
            confidence=1.0,
            category_guess=forced_domain,
            normalized_question=rt._strip_personal(q) if q else None,
            raw_text=q,
        )
    else:
        classification = rt.route_question(
            q, language=language, grok_api_key=grok_api_key
        )

    log_row = db.log_routed_query(
        user_id,
        route=classification.route,
        domain=classification.domain,
        confidence=classification.confidence,
        category_guess=classification.category_guess,
        normalized_question=classification.normalized_question,
        raw_text=classification.raw_text,
        path=db_path,
    )
    log_id = log_row.get("id")
    meta = {
        "route": classification.route,
        "route_log_id": log_id,
        "category_guess": classification.category_guess,
        "normalized_question": classification.normalized_question,
        "confidence": classification.confidence,
    }

    if classification.route == "HIGH_STAKES":
        return DecisionResult(
            ok=False,
            domain=None,
            suggestion="",
            justification="",
            refused=True,
            refusal_message=rt.REFUSAL_SV if language == "sv" else REFUSAL_COPY["en"],
            route="HIGH_STAKES",
            route_log_id=log_id,
        )

    if classification.route == "NOT_A_DECISION":
        return DecisionResult(
            ok=False,
            domain=None,
            suggestion="",
            justification="",
            refused=False,
            ui_message=rt.NOT_A_DECISION_SV if language == "sv" else rt.NOT_A_DECISION_EN,
            route="NOT_A_DECISION",
            route_log_id=log_id,
        )

    if classification.route == "AMBIGUOUS":
        return DecisionResult(
            ok=False,
            domain=None,
            suggestion="",
            justification="",
            needs_domain_pick=True,
            route="AMBIGUOUS",
            route_log_id=log_id,
            context={"raw_question": q},
        )

    # IN_DOMAIN or NEAR_DOMAIN → decision pipeline
    domain_hint = classification.domain
    if classification.route == "NEAR_DOMAIN":
        domain_hint = db.NEAR_DOMAIN
    question_for_pipeline = classification.normalized_question or q

    result = decide(
        user_id,
        question_for_pipeline,
        domain_hint=domain_hint,
        language=language,
        reroll=False,
        reroll_index=0,
        grok_api_key=grok_api_key,
        db_path=db_path,
        skip_feasibility=(classification.route == "NEAR_DOMAIN"),
        route_meta=meta,
    )
    if result.ok and log_id is not None:
        try:
            db.update_routed_query(int(log_id), decision_shown=True, path=db_path)
        except Exception as exc:
            log.warning("failed to mark decision_shown: %s", exc)
    return result


def accept_decision(
    decision_id: int,
    *,
    db_path: str | None = None,
    route_log_id: int | None = None,
) -> dict[str, Any]:
    out = db.record_feedback(decision_id, accepted=True, path=db_path)
    rid = route_log_id
    if rid is None and isinstance(out, dict):
        rid = (out.get("context") or {}).get("route_log_id")
    if rid is not None:
        try:
            db.update_routed_query(int(rid), accepted=True, path=db_path)
        except Exception as exc:
            log.warning("failed to mark routed accept: %s", exc)
    return out



# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------
def _time_of_day(hour: int) -> str:
    if hour < 5:
        return "night"
    if hour < 11:
        return "morning"
    if hour < 14:
        return "lunch"
    if hour < 17:
        return "afternoon"
    if hour < 21:
        return "evening"
    return "night"


def _looks_high_stakes(q: str) -> bool:
    return any(k in q.lower() for k in HIGH_STAKES_KEYWORDS)


def _looks_everyday(q: str) -> bool:
    return any(any(w in q.lower() for w in words) for words in DOMAIN_KEYWORDS.values())


def _default_question(domain: str, language: str) -> str:
    sv = {
        "food": "Vad ska jag äta?",
        "clothes": "Vad ska jag ha på mig idag?",
        "movie": "Vad ska jag titta på?",
        "workout": "Vad ska jag träna idag?",
        "weekend": "Vad ska jag göra i helgen?",
        "other": "Vad ska jag välja?",
    }
    en = {
        "food": "What should I eat?",
        "clothes": "What should I wear today?",
        "movie": "What should I watch?",
        "workout": "What workout should I do?",
        "weekend": "What should I do this weekend?",
        "other": "What should I pick?",
    }
    return (sv if language == "sv" else en).get(domain, sv["food"])


def _usable_grok_key(key: str) -> bool:
    k = str(key or "").strip()
    if len(k) < 8:
        return False
    low = k.lower()
    if low.startswith("din_") or "your_" in low or low.endswith("_här") or low.endswith("_har"):
        return False
    return True


def _generate_candidates(
    *,
    question: str,
    domain: str,
    context: dict[str, Any],
    profile: dict[str, Any],
    history: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    recent: list[str],
    language: str,
    grok_api_key: str,
) -> list[dict[str, Any]]:
    if _usable_grok_key(grok_api_key):
        try:
            return _grok_candidates(
                question,
                domain,
                context,
                profile,
                history,
                preferences,
                recent,
                language,
                grok_api_key,
            )
        except Exception as exc:
            log.exception("Grok candidates failed: %s", exc)
    return _local_candidates(domain, language, recent, context, profile)


def _grok_candidates(
    question: str,
    domain: str,
    context: dict[str, Any],
    profile: dict[str, Any],
    history: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    recent: list[str],
    language: str,
    api_key: str,
) -> list[dict[str, Any]]:
    lang = "Swedish" if language == "sv" else "English"
    accepted = [h["suggestion"] for h in history if h.get("status") in ("accepted", "locked")][:8]
    rejected = [h["suggestion"] for h in history if h.get("status") == "rejected"][:8]
    pos = [p for p in preferences if p.get("score", 0) > 0][:8]
    neg = [p for p in preferences if p.get("score", 0) < 0][:8]

    system = (
        "You are OneChoice. You make exactly one everyday decision the user can execute TODAY. "
        "If a candidate would hit any obstacle, discard it before returning. "
        "Never hedge. Never offer alternatives. Never show substitution notes. "
        f"Write BOTH suggestion and justification entirely in {lang}. "
        "Output valid JSON only."
    )
    domain_rules = _domain_prompt_rules(domain, profile)
    user = f"""
Domain: {domain}
Question: {question}
Output language (STRICT): {lang}
Context: {json.dumps(context, ensure_ascii=False)}
User profile: {json.dumps(profile, ensure_ascii=False)}
Recently shown/accepted (avoid repeats within 7 days): {json.dumps(recent[:12], ensure_ascii=False)}
Accepted before: {json.dumps(accepted, ensure_ascii=False)}
Rejected before: {json.dumps(rejected, ensure_ascii=False)}
Positive prefs: {json.dumps(pos, ensure_ascii=False)}
Negative prefs: {json.dumps(neg, ensure_ascii=False)}

Domain feasibility rules:
{domain_rules}

Internally invent 5 strong candidate decisions. Mark ~1 as wildcard=true (adventure in flavor/genre, NEVER in sourcing or unavailable services).
Return ONLY JSON:
{{
  "candidates": [
    {{
      "suggestion":"...",
      "justification":"one confident line",
      "wildcard": false,
      "meta": {{}}
    }},
    ... exactly 5 items ...
  ]
}}
Rules:
- suggestion is the decision itself (short, decisive), fully in {lang}
- justification is ONE line in {lang}, personal, no hedging, no "you could also"
- every candidate must already pass the domain feasibility rules above
- avoid anything in the recent/rejected lists when possible
"""
    resp = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": "grok-2-latest",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.7,
        },
        timeout=45,
    )
    resp.raise_for_status()
    payload = resp.json()
    choices = payload.get("choices") or []
    if not choices:
        raise ValueError("empty grok choices")
    content = (choices[0].get("message") or {}).get("content") or ""
    raw = str(content).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", raw)
    if brace:
        raw = brace.group(0)
    data = json.loads(raw)
    out: list[dict[str, Any]] = []
    for c in data.get("candidates") or []:
        if not isinstance(c, dict):
            continue
        s = str(c.get("suggestion") or "").strip()
        j = str(c.get("justification") or "").strip()
        if s and j:
            out.append(
                {
                    "suggestion": s,
                    "justification": j,
                    "wildcard": bool(c.get("wildcard")),
                    "meta": c.get("meta") if isinstance(c.get("meta"), dict) else {},
                }
            )
    if len(out) < 3:
        raise ValueError("not enough candidates from grok")
    return out[:5]


def _domain_prompt_rules(domain: str, profile: dict[str, Any]) -> str:
    rules = {
        "food": (
            "Only Swedish supermarket basic assortment (ICA/Coop/Willys/Lidl/Hemköp). "
            "No teff, fresh lemongrass, specialty imports. Max 30 min weekday / 60 min weekend. "
            "Wildcard = flavor adventure, never sourcing. Eating out only if open + near user."
        ),
        "clothes": (
            f"Section={profile.get('clothes', {}).get('section')}. "
            "Wear: wardrobe only if registered, else category outfit. "
            "Buy: Swedish retailers in stock + size. Respect weather/temp."
        ),
        "movie": (
            f"Services={profile.get('movie', {}).get('services')}. "
            f"Max minutes={profile.get('movie', {}).get('available_minutes')}. "
            "Must be on a subscribed service. No rentals unless allow_rentals. Include deep link target in meta.title."
        ),
        "workout": (
            f"Context={profile.get('workout', {}).get('context')}, "
            f"equipment={profile.get('workout', {}).get('equipment')}, "
            f"minutes={profile.get('workout', {}).get('default_minutes')}, "
            f"limitations={profile.get('workout', {}).get('limitations')!r}. "
            "Home users never 'go to gym'. Outdoor respects weather/dark. Write workout plan in meta.plan."
        ),
        "weekend": (
            f"Car={profile.get('weekend', {}).get('has_car')}, "
            f"budget={profile.get('weekend', {}).get('budget')}, "
            f"household={profile.get('weekend', {}).get('household')}. "
            "Must be open/season-possible, age-appropriate, within travel range."
        ),
    }
    return rules.get(domain, "")


def _local_candidates(
    domain: str,
    language: str,
    recent: list[str],
    context: dict[str, Any],
    profile: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    profile = profile or {}
    packs_sv: dict[str, list[dict[str, Any]]] = {
        "food": [
            {
                "suggestion": "Krämig tomatsås-pasta",
                "justification": "Varmt, enkelt och klart på 20 minuter.",
                "meta": {"active_minutes": 20},
            },
            {
                "suggestion": "Etiopisk-inspirerad linsgryta",
                "justification": "Varm krydda från hyllorna du redan har — äventyr utan specialbutik.",
                "wildcard": True,
                "meta": {"active_minutes": 30, "shopping_list": {
                    "frukt & grönt": ["gul lök", "vitlök", "spenat"],
                    "mejeri": [],
                    "kött/fisk": [],
                    "skafferi": ["röda linser", "curry", "paprika", "kokosmjölk", "ris"],
                    "fryst": [],
                }},
            },
            {
                "suggestion": "Proteinomelett med grönt",
                "justification": "Snabb, mättande och håller dig till nästa mål.",
                "meta": {"active_minutes": 15},
            },
            {
                "suggestion": "Kycklingwok med ris",
                "justification": "Vardagsfavorit med det som alltid finns i kylen.",
                "meta": {"active_minutes": 25},
            },
            {
                "suggestion": "Klassisk burgare hemma",
                "justification": "Komfort utan krångel — du vet redan att det funkar.",
                "meta": {"active_minutes": 25},
            },
        ],
        "clothes": [
            {"suggestion": "Mörka jeans + vit t-shirt + sneakers", "justification": "Rent, säkert och funkar hela dagen."},
            {"suggestion": "Beiga byxor + stickad tröja", "justification": "Mjukt och premium — noll stylingångest."},
            {"suggestion": "Hoodie + cargobyxor", "justification": "Bekvämt när dagen ska flyta."},
            {"suggestion": "Svarta byxor + skarp skjorta", "justification": "Smart casual som ser medvetet ut."},
            {"suggestion": "Helsvart outfit", "justification": "Ett beslut. Ser alltid skärpt ut.", "wildcard": True},
        ],
        "movie": [
            {
                "suggestion": "Wednesday",
                "justification": "Mörk humor i lagom dos — ett avsnitt och du är klar.",
                "meta": {"title": "wednesday"},
            },
            {
                "suggestion": "Seinfeld",
                "justification": "Lätt efter en lång dag — 22 minuter, noll ångest.",
                "meta": {"title": "seinfeld"},
            },
            {
                "suggestion": "The Night Agent",
                "justification": "Högt tempo när du vill bli uppslukad.",
                "meta": {"title": "the night agent"},
                "wildcard": True,
            },
            {
                "suggestion": "Det sista kapitlet",
                "justification": "Svenskt och bra — öppna SVT Play och tryck play.",
                "meta": {"title": "det sista kapitlet"},
            },
            {
                "suggestion": "Ett avsnitt av en varm komediserie",
                "justification": "Lätt efter en lång dag.",
            },
        ],
        "workout": [
            {
                "suggestion": "30 minuters helkroppsstyrka hemma",
                "justification": "Effektivt och klart innan motivationen sviktar.",
                "meta": {"minutes": 30},
            },
            {
                "suggestion": "Zon-2-promenad i 30 minuter",
                "justification": "Låg tröskel, hög utdelning idag.",
                "meta": {"minutes": 30},
            },
            {
                "suggestion": "20 minuters HIIT",
                "justification": "Kort, hårt, sedan vidare med dagen.",
                "meta": {"minutes": 20},
            },
            {
                "suggestion": "Yogaflöde i 25 minuter",
                "justification": "Mobilitet och lugn i ett pass.",
                "meta": {"minutes": 25},
            },
            {
                "suggestion": "Armhävningar + knäböj-stege",
                "justification": "Ingen utrustning. Inga ursäkter.",
                "meta": {"minutes": 20},
                "wildcard": True,
            },
        ],
        "weekend": [
            {"suggestion": "Kaffepromenad + en bokhandel", "justification": "Enkelt, lagom socialt, noll planeringskaos."},
            {"suggestion": "Laga en längre helglunch", "justification": "Helgkänsla utan biljetter eller köer."},
            {"suggestion": "Picknick i parken", "justification": "Ute, enkelt, minnesvärt."},
            {"suggestion": "Museum eller galleri i 90 minuter", "justification": "Lagom stort äventyr."},
            {"suggestion": "Städa ett rum, sen belöning på café", "justification": "Framåtanda plus belöning.", "wildcard": True},
        ],
        "other": [
            {"suggestion": "En upplevelse istället för pryl", "justification": "Minns längre — och du slipper gissningsleken."},
            {"suggestion": "Något personligt och enkelt", "justification": "Varmt utan att bli överdrivet."},
            {"suggestion": "Ett kort handskrivet kort + en liten grej", "justification": "Insatsen syns mer än prislappen."},
            {"suggestion": "Fråga vad de saknar — sen bestäm en sak", "justification": "Ett beslut, noll gissningar.", "wildcard": True},
            {"suggestion": "Ge tid: en planerad fika eller promenad", "justification": "Närvaro vinner oftast."},
        ],
    }
    packs_en: dict[str, list[dict[str, Any]]] = {
        "food": [
            {"suggestion": "Creamy tomato pasta", "justification": "Warm, simple, done in 20 minutes.", "meta": {"active_minutes": 20}},
            {"suggestion": "Ethiopian-inspired lentil stew", "justification": "Shelf spices only — adventure without specialty shops.", "wildcard": True, "meta": {"active_minutes": 30}},
            {"suggestion": "Protein omelette with greens", "justification": "Fast, filling, carries you to the next meal.", "meta": {"active_minutes": 15}},
            {"suggestion": "Chicken stir-fry with rice", "justification": "Weeknight classic from what you already have.", "meta": {"active_minutes": 25}},
            {"suggestion": "Classic burger at home", "justification": "Comfort without friction.", "meta": {"active_minutes": 25}},
        ],
        "clothes": [
            {"suggestion": "Dark jeans + white tee + sneakers", "justification": "Clean, safe, works all day."},
            {"suggestion": "Beige trousers + knit sweater", "justification": "Soft and premium — zero styling stress."},
            {"suggestion": "Hoodie + cargo pants", "justification": "Comfort when the day should flow."},
            {"suggestion": "Black trousers + crisp shirt", "justification": "Smart casual that looks intentional."},
            {"suggestion": "All-black outfit", "justification": "One decision. Always sharp.", "wildcard": True},
        ],
        "movie": [
            {"suggestion": "Wednesday", "justification": "Dark humor in a right-sized dose.", "meta": {"title": "wednesday"}},
            {"suggestion": "Seinfeld", "justification": "Easy after a long day — 22 minutes.", "meta": {"title": "seinfeld"}},
            {"suggestion": "The Night Agent", "justification": "High pace when you want to disappear into a story.", "meta": {"title": "the night agent"}, "wildcard": True},
            {"suggestion": "One episode of a warm comedy series", "justification": "Easy after a long day."},
            {"suggestion": "A short documentary under 90 minutes", "justification": "Feels productive, still rest."},
        ],
        "workout": [
            {"suggestion": "30-minute full-body strength at home", "justification": "Efficient — done before motivation dips.", "meta": {"minutes": 30}},
            {"suggestion": "Zone-2 walk for 30 minutes", "justification": "Low barrier, high payoff today.", "meta": {"minutes": 30}},
            {"suggestion": "20-minute HIIT", "justification": "Short, hard, then move on.", "meta": {"minutes": 20}},
            {"suggestion": "25-minute yoga flow", "justification": "Mobility and calm in one session.", "meta": {"minutes": 25}},
            {"suggestion": "Push-ups + squats ladder", "justification": "No equipment. No excuses.", "meta": {"minutes": 20}, "wildcard": True},
        ],
        "weekend": [
            {"suggestion": "Coffee walk + one bookstore", "justification": "Simple, social enough, zero planning chaos."},
            {"suggestion": "Cook a longer weekend lunch", "justification": "Weekend energy without tickets or queues."},
            {"suggestion": "Park picnic", "justification": "Outside, easy, memorable."},
            {"suggestion": "Museum or gallery for 90 minutes", "justification": "A right-sized adventure."},
            {"suggestion": "Deep-clean one room, then a café reward", "justification": "Progress plus a reward.", "wildcard": True},
        ],
        "other": [
            {"suggestion": "An experience instead of a thing", "justification": "Lasts longer — and ends the guessing."},
            {"suggestion": "Something personal and simple", "justification": "Warm without overdoing it."},
            {"suggestion": "A short handwritten note + one small item", "justification": "Effort beats price."},
            {"suggestion": "Ask what they need — then pick one thing", "justification": "One decision, zero guessing.", "wildcard": True},
            {"suggestion": "Give time: plan a coffee or a walk", "justification": "Presence usually wins."},
        ],
    }
    packs = packs_sv if language == "sv" else packs_en
    # Near-domain: bias pack by category_guess when present
    cat = str((context or {}).get("category_guess") or "").lower()
    if domain in ("other", db.NEAR_DOMAIN) and cat:
        items = _near_domain_pack(cat, language)
    else:
        items = list(packs.get(domain, packs["other"] if domain == db.NEAR_DOMAIN else packs["food"]))
    recent_l = {str(r).strip().lower() for r in recent if r}
    filtered = [c for c in items if c["suggestion"].strip().lower() not in recent_l]
    pool = filtered or items
    random.shuffle(pool)
    if domain == "food" and context.get("time_of_day") == "morning":
        if language == "sv":
            pool.insert(0, {
                "suggestion": "Proteinomelett med frukt",
                "justification": "Snabb frukost som håller dig till lunch.",
                "meta": {"active_minutes": 15},
            })
        else:
            pool.insert(0, {
                "suggestion": "Protein omelette with fruit",
                "justification": "A quick breakfast that carries you to lunch.",
                "meta": {"active_minutes": 15},
            })
    # Mark one wildcard if none flagged
    if pool and not any(c.get("wildcard") for c in pool):
        pool[-1] = dict(pool[-1], wildcard=True)
    return pool[:5]


def _guaranteed_feasible(
    domain: str,
    language: str,
    profile: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """Last-resort candidate known to pass validators for default profiles."""
    sv = language == "sv"
    if domain == "food":
        c = {
            "suggestion": "Krämig tomatsås-pasta" if sv else "Creamy tomato pasta",
            "justification": "Varmt, enkelt och klart på 20 minuter." if sv else "Warm, simple, done in 20 minutes.",
            "meta": {"active_minutes": 20},
        }
    elif domain == "clothes":
        c = {
            "suggestion": "Mörka jeans + vit t-shirt + sneakers" if sv else "Dark jeans + white tee + sneakers",
            "justification": "Rent, säkert och funkar hela dagen." if sv else "Clean, safe, works all day.",
        }
    elif domain == "movie":
        c = {
            "suggestion": "Seinfeld",
            "justification": "Lätt efter en lång dag." if sv else "Easy after a long day.",
            "meta": {"title": "seinfeld"},
        }
    elif domain == "workout":
        c = {
            "suggestion": "Armhävningar + knäböj-stege" if sv else "Push-ups + squats ladder",
            "justification": "Ingen utrustning. Inga ursäkter." if sv else "No equipment. No excuses.",
            "meta": {"minutes": 20},
        }
    else:
        c = {
            "suggestion": "Kaffepromenad + en bokhandel" if sv else "Coffee walk + one bookstore",
            "justification": "Enkelt, lagom socialt, noll planeringskaos." if sv else "Simple, social enough, zero planning chaos.",
        }
        if domain in ("other", db.NEAR_DOMAIN):
            c = {
                "suggestion": "Något personligt och enkelt" if sv else "Something personal and simple",
                "justification": "Varmt utan att bli överdrivet." if sv else "Warm without overdoing it.",
            }
    survivors = feasibility.filter_feasible([c], domain=domain, profile=profile, context=context)
    return survivors[0] if survivors else c


def _near_domain_pack(category: str, language: str) -> list[dict[str, Any]]:
    sv = language == "sv"
    if "present" in category or "jul" in category or "gift" in category:
        return [
            {"suggestion": "En upplevelse istället för pryl" if sv else "An experience instead of a thing",
             "justification": "Minns längre." if sv else "Lasts longer."},
            {"suggestion": "En bra bok + handskrivet kort" if sv else "A good book + handwritten note",
             "justification": "Personligt utan stress." if sv else "Personal without stress."},
            {"suggestion": "Premiumchoklad och något de nämnt" if sv else "Nice chocolate plus something they mentioned",
             "justification": "Enkelt och säkert." if sv else "Simple and safe."},
            {"suggestion": "Ett presentkort till deras favoritställe" if sv else "A gift card to their favorite place",
             "justification": "De väljer — du har bestämt." if sv else "They choose — you decided."},
            {"suggestion": "Planera en gemensam grej" if sv else "Plan one shared activity",
             "justification": "Tid slår pryl." if sv else "Time beats stuff.", "wildcard": True},
        ]
    if "husdjur" in category or "namn" in category or "pet" in category:
        return [
            {"suggestion": "Maja" if sv else "Maja", "justification": "Kort, mjukt, lätt att ropa." if sv else "Short, soft, easy to call."},
            {"suggestion": "Bosse" if sv else "Bosse", "justification": "Varmt och jordnära." if sv else "Warm and grounded."},
            {"suggestion": "Nimbus" if sv else "Nimbus", "justification": "Lite lekfullt utan att bli knepigt." if sv else "Playful without being weird.", "wildcard": True},
            {"suggestion": "Saga" if sv else "Saga", "justification": "Fint och enkelt." if sv else "Pretty and simple."},
            {"suggestion": "Kalle" if sv else "Kalle", "justification": "Klassiskt — funkar i vardagen." if sv else "Classic — works every day."},
        ]
    if "inred" in category or "färg" in category or "color" in category:
        return [
            {"suggestion": "Varm off-white" if sv else "Warm off-white", "justification": "Lugnt och tidlöst." if sv else "Calm and timeless."},
            {"suggestion": "Mjuk sagegrön" if sv else "Soft sage green", "justification": "Fräscht utan att skrika." if sv else "Fresh without shouting."},
            {"suggestion": "Dämpad sandbeige" if sv else "Muted sand beige", "justification": "Varmt och tryggt." if sv else "Warm and safe."},
            {"suggestion": "Matt blågrå" if sv else "Matte blue-gray", "justification": "Ser medvetet ut." if sv else "Looks intentional.", "wildcard": True},
            {"suggestion": "Ljus lera / terracotta-ton" if sv else "Light clay / terracotta tone", "justification": "Mysfaktor utan kaos." if sv else "Cozy without chaos."},
        ]
    # generic other
    return [
        {"suggestion": "Välj det enklare alternativet" if sv else "Pick the simpler option",
         "justification": "Mindre friktion idag." if sv else "Less friction today."},
        {"suggestion": "Gör det i 20 minuter — sen stopp" if sv else "Do it for 20 minutes — then stop",
         "justification": "Ett beslut, tydlig gräns." if sv else "One decision, clear boundary."},
        {"suggestion": "Ta det du redan lutar åt" if sv else "Take the one you’re already leaning toward",
         "justification": "Du vet redan." if sv else "You already know."},
        {"suggestion": "Skjut upp tills imorgon bitti — sen bestäm" if sv else "Park it until morning — then decide",
         "justification": "När det inte är bråttom." if sv else "When it isn’t urgent.", "wildcard": True},
        {"suggestion": "Fråga en person du litar på — en mening" if sv else "Ask one trusted person — one sentence",
         "justification": "Sen kör." if sv else "Then go."},
    ]


def _rank_candidates(
    candidates: list[dict[str, Any]],
    *,
    preferences: list[dict[str, Any]],
    recent: list[str],
    explore: bool,
) -> list[dict[str, Any]]:
    if not candidates:
        return []
    recent_l = {str(r).strip().lower() for r in recent if r}
    pref_map = {
        (p.get("value") or "").strip().lower(): float(p.get("score") or 0)
        for p in preferences
        if p.get("key") == "suggestion"
    }

    scored: list[tuple[float, dict[str, Any]]] = []
    for c in candidates:
        key = str(c.get("suggestion") or "").strip().lower()
        if not key:
            continue
        score = float(pref_map.get(key, 0.0))
        if key in recent_l:
            score -= 5.0
        for pref_val, pref_score in pref_map.items():
            if pref_val and pref_val in key:
                score += float(pref_score) * 0.25
        # Safe bias: non-wildcards rank slightly higher unless exploring
        if c.get("wildcard"):
            score -= 0.15
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)

    if explore and len(scored) > 1:
        wild = [pair for pair in scored if pair[1].get("wildcard")]
        explore_pool = wild or scored[len(scored) // 2 :]
        pick = random.choice(explore_pool)
        rest = [c for s, c in scored if c is not pick[1]]
        return [pick[1]] + rest
    return [c for _, c in scored]


def _fallback_candidate(
    domain: str, language: str, recent: list[str]
) -> dict[str, Any]:
    return _local_candidates(domain, language, recent, {})[0]


def _execution_for(
    domain: str,
    suggestion: str,
    language: str,
    user: dict[str, Any],
) -> dict[str, Any]:
    suggestion = str(suggestion or "")
    q = quote_plus(suggestion)
    sv = language == "sv"
    if domain == "food":
        out_words = ("restaurang", "beställ", "bestall", "burger", "sushi", "thai", "order", "takeout")
        if any(w in suggestion.lower() for w in out_words):
            return {
                "type": "map",
                "label": "Öppna karta" if sv else "Open map",
                "url": f"https://www.google.com/maps/search/{q}",
            }
        return {
            "type": "recipe",
            "label": "Handla & laga" if sv else "Shop & cook",
            "url": f"https://www.google.com/search?q={quote_plus(suggestion + ' recept' if sv else suggestion + ' recipe')}",
        }
    if domain == "clothes":
        return {
            "type": "wardrobe",
            "label": "Bygg outfiten" if sv else "Build the outfit",
            "url": f"https://www.google.com/search?q={quote_plus(suggestion + ' outfit')}",
        }
    if domain == "movie":
        return {
            "type": "stream",
            "label": "Öppna streaming" if sv else "Open streaming",
            "url": f"https://www.justwatch.com/se/search?q={q}",
        }
    if domain == "workout":
        return {
            "type": "workout",
            "label": "Starta passet" if sv else "Start workout",
            "url": None,
            "detail": suggestion,
        }
    return {
        "type": "activity",
        "label": "Öppna karta" if sv else "Open map",
        "url": f"https://www.google.com/maps/search/{q}",
    }
