# -*- coding: utf-8 -*-
"""
OneChoice decision pipeline.

Single entry point: decide(...)
  question → classify domain → context + history → candidates → rank → ONE result
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

log = logging.getLogger("onechoice.pipeline")

MAX_REROLLS = 3
REPEAT_DAYS = 14
SAFE_RATIO = 0.80  # bandit: 80% safe / 20% explore

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
    "sv": "Onechoice handles everyday decisions. This one is yours.",
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
        "weather": (extra or {}).get("weather", "unknown"),
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
    reroll: bool = False,
    reroll_index: int = 0,
    previous_decision_id: int | None = None,
    context_extra: dict[str, Any] | None = None,
    grok_api_key: str = "",
    db_path: str | None = None,
) -> DecisionResult:
    """
    Full decision pipeline. Returns exactly ONE decision (or a hard refusal).

    On reroll: previous decision is marked rejected (negative signal).
    After MAX_REROLLS, result is locked.
    """
    db.init_db(db_path)
    user = db.ensure_user(user_id, path=db_path)
    language = user.get("language") or "sv"
    q = (question or "").strip()
    if not q and domain_hint:
        q = _default_question(domain_hint, language)

    domain = classify_domain(q, domain_hint)
    if domain == "refused" or domain is None and _looks_high_stakes(q):
        return DecisionResult(
            ok=False,
            domain=None,
            suggestion="",
            justification="",
            refused=True,
            refusal_message=REFUSAL_COPY.get(language, REFUSAL_COPY["en"]),
        )
    if domain is None:
        domain = "food"  # soft default only for empty/ambiguous everyday prompts
        # If clearly out of scope without keywords, refuse
        if q and not _looks_everyday(q):
            return DecisionResult(
                ok=False,
                domain=None,
                suggestion="",
                justification="",
                refused=True,
                refusal_message=REFUSAL_COPY.get(language, REFUSAL_COPY["en"]),
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
    history = db.list_decisions(user_id, domain=domain, limit=40, path=db_path)
    prefs = db.get_preferences(user_id, domain, path=db_path)
    recent = db.recent_suggestions(user_id, domain, days=REPEAT_DAYS, path=db_path)

    explore = (not locked) and (random.random() > SAFE_RATIO)
    candidates = _generate_candidates(
        question=q,
        domain=domain,
        context=ctx,
        history=history,
        preferences=prefs,
        recent=recent,
        language=language,
        grok_api_key=grok_api_key,
    )
    ranked = _rank_candidates(
        candidates,
        preferences=prefs,
        recent=recent,
        explore=explore,
    )
    top = ranked[0] if ranked else _fallback_candidate(domain, language, recent)

    execution = _execution_for(domain, top["suggestion"], language, user)
    status = "locked" if locked else "shown"

    decision = db.create_decision(
        user_id=user_id,
        domain=domain,
        question=q,
        suggestion=top["suggestion"],
        justification=top["justification"],
        status=status,
        reroll_index=effective_reroll,
        context={**ctx, "explore": explore, "candidates_n": len(candidates)},
        execution_type=execution["type"],
        execution_label=execution["label"],
        execution_url=execution["url"],
        path=db_path,
    )

    if locked:
        # Positive lock signal — this is the one
        db.upsert_preference(
            user_id,
            domain,
            "suggestion",
            top["suggestion"].strip().lower(),
            1.5,
            path=db_path,
        )

    return DecisionResult(
        ok=True,
        domain=domain,
        suggestion=top["suggestion"],
        justification=top["justification"],
        execution_type=execution["type"],
        execution_label=execution["label"],
        execution_url=execution["url"],
        decision_id=decision["id"],
        reroll_index=effective_reroll,
        locked=locked,
        refused=False,
        context=decision.get("context") or ctx,
        explore=explore,
    )


def accept_decision(decision_id: int, *, db_path: str | None = None) -> dict[str, Any]:
    return db.record_feedback(decision_id, accepted=True, path=db_path)


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
    }
    en = {
        "food": "What should I eat?",
        "clothes": "What should I wear today?",
        "movie": "What should I watch?",
        "workout": "What workout should I do?",
        "weekend": "What should I do this weekend?",
    }
    return (sv if language == "sv" else en).get(domain, sv["food"])


def _generate_candidates(
    *,
    question: str,
    domain: str,
    context: dict[str, Any],
    history: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    recent: list[str],
    language: str,
    grok_api_key: str,
) -> list[dict[str, str]]:
    if grok_api_key and not grok_api_key.startswith("din_"):
        try:
            return _grok_candidates(
                question, domain, context, history, preferences, recent, language, grok_api_key
            )
        except Exception as exc:
            log.exception("Grok candidates failed: %s", exc)
    return _local_candidates(domain, language, recent, context)


def _grok_candidates(
    question: str,
    domain: str,
    context: dict[str, Any],
    history: list[dict[str, Any]],
    preferences: list[dict[str, Any]],
    recent: list[str],
    language: str,
    api_key: str,
) -> list[dict[str, str]]:
    lang = "Swedish" if language == "sv" else "English"
    accepted = [h["suggestion"] for h in history if h.get("status") in ("accepted", "locked")][:8]
    rejected = [h["suggestion"] for h in history if h.get("status") == "rejected"][:8]
    pos = [p for p in preferences if p.get("score", 0) > 0][:8]
    neg = [p for p in preferences if p.get("score", 0) < 0][:8]

    system = (
        "You are OneChoice. You make exactly one everyday decision. "
        "Reason internally. Never hedge. Never offer alternatives to the user. "
        "Output valid JSON only."
    )
    user = f"""
Domain: {domain}
Question: {question}
Language: {lang}
Context: {json.dumps(context, ensure_ascii=False)}
Recently shown/accepted (avoid repeats): {json.dumps(recent[:12], ensure_ascii=False)}
Accepted before: {json.dumps(accepted, ensure_ascii=False)}
Rejected before: {json.dumps(rejected, ensure_ascii=False)}
Positive prefs: {json.dumps(pos, ensure_ascii=False)}
Negative prefs: {json.dumps(neg, ensure_ascii=False)}

Internally invent 5 strong candidate decisions for this domain.
Rank them yourself. Return ONLY JSON:
{{
  "candidates": [
    {{"suggestion":"...","justification":"one confident line"}},
    ... exactly 5 items ...
  ]
}}
Rules:
- suggestion is the decision itself (short, decisive)
- justification is ONE line, personal, no hedging, no "you could also"
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
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", raw)
    if brace:
        raw = brace.group(0)
    data = json.loads(raw)
    out = []
    for c in data.get("candidates", []):
        s = str(c.get("suggestion", "")).strip()
        j = str(c.get("justification", "")).strip()
        if s and j:
            out.append({"suggestion": s, "justification": j})
    if len(out) < 3:
        raise ValueError("not enough candidates from grok")
    return out[:5]


def _local_candidates(
    domain: str,
    language: str,
    recent: list[str],
    context: dict[str, Any],
) -> list[dict[str, str]]:
    sv = language == "sv"
    packs: dict[str, list[dict[str, str]]] = {
        "food": [
            {"suggestion": "Pad thai", "justification": "Snabb, mättande och du har inte ätit asiatiskt på ett tag." if sv else "Fast, filling — you haven’t had Asian food in a while."},
            {"suggestion": "Salmon poke bowl", "justification": "Lätt men rikt — perfekt till lunch." if sv else "Light but rich — perfect for lunch."},
            {"suggestion": "Classic burger", "justification": "Komfort utan krångel. Beställ och ät." if sv else "Comfort without friction. Order it."},
            {"suggestion": "Creamy tomato pasta", "justification": "Varmt, enkelt och klart på 20 minuter." if sv else "Warm, simple, done in 20 minutes."},
            {"suggestion": "Mezze plate", "justification": "Varierat utan att du behöver välja tre saker." if sv else "Variety without making three choices."},
        ],
        "clothes": [
            {"suggestion": "Dark jeans + white tee + sneakers", "justification": "Rent, säkert och funkar hela dagen." if sv else "Clean, safe, works all day."},
            {"suggestion": "Neutrals: beige trousers + knit", "justification": "Mjukt och premium — noll stylingångest." if sv else "Soft and premium — zero styling stress."},
            {"suggestion": "Black trousers + crisp shirt", "justification": "Smart casual som ser medvetet ut." if sv else "Smart casual that looks intentional."},
            {"suggestion": "Hoodie + cargo pants", "justification": "Bekvämt när dagen ska flyta." if sv else "Comfort when the day should flow."},
            {"suggestion": "All-black capsule", "justification": "Ett beslut. Ser alltid skärpt ut." if sv else "One decision. Always sharp."},
        ],
        "movie": [
            {"suggestion": "Watch a tight thriller tonight", "justification": "Hög tempo, noll beslutströtthet." if sv else "High pace, zero decision fatigue."},
            {"suggestion": "A warm comedy series episode", "justification": "Lätt efter en lång dag." if sv else "Easy after a long day."},
            {"suggestion": "A visually rich sci-fi film", "justification": "Något nytt utan att kräva research." if sv else "Something fresh without research."},
            {"suggestion": "A short documentary (under 90 min)", "justification": "Känns produktivt men är fortfarande avkoppling." if sv else "Feels productive, still rest."},
            {"suggestion": "Rewatch a comfort favorite", "justification": "Du vet redan att det funkar." if sv else "You already know it works."},
        ],
        "workout": [
            {"suggestion": "30-min full-body strength", "justification": "Effektivt och klart innan motivationen sviktar." if sv else "Efficient — done before motivation dips."},
            {"suggestion": "Zone-2 walk for 40 minutes", "justification": "Låg tröskel, hög utdelning idag." if sv else "Low barrier, high payoff today."},
            {"suggestion": "20-min HIIT", "justification": "Kort, hårt, sedan vidare med dagen." if sv else "Short, hard, then move on."},
            {"suggestion": "Yoga flow (25 min)", "justification": "Mobilitet och lugn i ett pass." if sv else "Mobility and calm in one session."},
            {"suggestion": "Push-ups + squats ladder", "justification": "Ingen utrustning. Inga ursäkter." if sv else "No equipment. No excuses."},
        ],
        "weekend": [
            {"suggestion": "Coffee walk + one bookstore", "justification": "Enkelt, socialt nog, noll planeringskaos." if sv else "Simple, social enough, zero planning chaos."},
            {"suggestion": "Cook a longer weekend lunch", "justification": "Helgkänsla utan biljetter eller köer." if sv else "Weekend energy without tickets or queues."},
            {"suggestion": "Museum or gallery for 90 minutes", "justification": "Lagom stort äventyr." if sv else "A right-sized adventure."},
            {"suggestion": "Park picnic with one friend", "justification": "Ute, enkelt, minnesvärt." if sv else "Outside, easy, memorable."},
            {"suggestion": "Deep-clean one room, then reward café", "justification": "Framåtanda plus belöning." if sv else "Progress plus a reward."},
        ],
    }
    items = list(packs.get(domain, packs["food"]))
    recent_l = {r.strip().lower() for r in recent}
    filtered = [c for c in items if c["suggestion"].strip().lower() not in recent_l]
    pool = filtered or items
    random.shuffle(pool)
    # Light context nudge for food time-of-day
    if domain == "food" and context.get("time_of_day") == "morning" and sv:
        pool.insert(0, {"suggestion": "Protein omelette + fruit", "justification": "Snabb frukost som håller dig till lunch."})
    return pool[:5]


def _rank_candidates(
    candidates: list[dict[str, str]],
    *,
    preferences: list[dict[str, Any]],
    recent: list[str],
    explore: bool,
) -> list[dict[str, str]]:
    if not candidates:
        return []
    recent_l = {r.strip().lower() for r in recent}
    pref_map = {
        (p.get("value") or "").strip().lower(): float(p.get("score") or 0)
        for p in preferences
        if p.get("key") == "suggestion"
    }

    scored: list[tuple[float, dict[str, str]]] = []
    for c in candidates:
        key = c["suggestion"].strip().lower()
        score = pref_map.get(key, 0.0)
        if key in recent_l:
            score -= 5.0
        # Soft boost for positive prefs substring match
        for pref_val, pref_score in pref_map.items():
            if pref_val and pref_val in key:
                score += pref_score * 0.25
        scored.append((score, c))

    scored.sort(key=lambda x: x[0], reverse=True)

    if explore and len(scored) > 1:
        # Pick from lower half occasionally
        explore_pool = scored[len(scored) // 2 :]
        pick = random.choice(explore_pool)
        rest = [c for s, c in scored if c is not pick[1]]
        return [pick[1]] + rest
    return [c for _, c in scored]


def _fallback_candidate(
    domain: str, language: str, recent: list[str]
) -> dict[str, str]:
    return _local_candidates(domain, language, recent, {})[0]


def _execution_for(
    domain: str,
    suggestion: str,
    language: str,
    user: dict[str, Any],
) -> dict[str, str | None]:
    q = quote_plus(suggestion)
    sv = language == "sv"
    if domain == "food":
        # Heuristic: words that imply eating out vs home cook
        out_words = ("restaurang", "beställ", "bestall", "burger", "sushi", "thai", "order", "takeout")
        if any(w in suggestion.lower() for w in out_words):
            return {
                "type": "map",
                "label": "Öppna karta" if sv else "Open map",
                "url": f"https://www.google.com/maps/search/{q}",
            }
        return {
            "type": "recipe",
            "label": "Se recept" if sv else "See recipe",
            "url": f"https://www.google.com/search?q={quote_plus(suggestion + ' recept' if sv else suggestion + ' recipe')}",
        }
    if domain == "clothes":
        return {
            "type": "wardrobe",
            "label": "Visa outfit-tips" if sv else "Show outfit tips",
            "url": f"https://www.google.com/search?q={quote_plus(suggestion + ' outfit')}",
        }
    if domain == "movie":
        return {
            "type": "stream",
            "label": "Hitta var den streamas" if sv else "Find where to stream",
            "url": f"https://www.google.com/search?q={quote_plus(suggestion + ' stream')}",
        }
    if domain == "workout":
        return {
            "type": "workout",
            "label": "Öppna passet" if sv else "Open workout",
            "url": f"https://www.google.com/search?q={quote_plus(suggestion + ' workout')}",
        }
    return {
        "type": "activity",
        "label": "Planera nu" if sv else "Plan it now",
        "url": f"https://www.google.com/search?q={q}",
    }
