# -*- coding: utf-8 -*-
"""Structured workouts — structure first, display text derived."""

from __future__ import annotations

from typing import Any

Block = dict[str, Any]
Workout = dict[str, Any]

# Seconds assumed per rep when estimating duration for rep-based blocks
SEC_PER_REP = 3


def compute_total_seconds(blocks: list[Block]) -> int:
    total = 0
    for b in blocks:
        sets = max(1, int(b.get("sets") or 1))
        rest = max(0, int(b.get("rest_seconds") or 0))
        if (b.get("type") or "reps") == "time":
            work = max(0, int(b.get("seconds") or 0)) * sets
        else:
            reps = max(1, int(b.get("reps") or 10))
            work = sets * reps * SEC_PER_REP
        rests = rest * max(0, sets - 1)
        total += work + rests
    return total


def compute_total_minutes(blocks: list[Block]) -> int:
    import math

    return max(1, int(math.ceil(compute_total_seconds(blocks) / 60)))


def finalize_workout(workout: dict[str, Any] | None, *, language: str = "sv") -> Workout:
    """Normalize blocks and set total_minutes from structure (single source of truth)."""
    raw = dict(workout or {})
    title = str(raw.get("title") or ("Pass" if language == "sv" else "Workout")).strip()
    blocks: list[Block] = []
    for b in raw.get("blocks") or []:
        if not isinstance(b, dict):
            continue
        name = str(b.get("name") or "").strip()
        if not name:
            continue
        btype = b.get("type") if b.get("type") in ("reps", "time") else "reps"
        block: Block = {
            "name": name,
            "type": btype,
            "sets": max(1, int(b.get("sets") or 1)),
            "reps": int(b["reps"]) if b.get("reps") is not None else None,
            "seconds": int(b["seconds"]) if b.get("seconds") is not None else None,
            "rest_seconds": max(0, int(b.get("rest_seconds") or 0)),
            "cue": str(b.get("cue") or "").strip(),
        }
        if btype == "time" and not block["seconds"]:
            block["seconds"] = 30
        if btype == "reps" and not block["reps"]:
            block["reps"] = 10
        blocks.append(block)
    if not blocks:
        blocks = _fallback_blocks(language)
    total_minutes = compute_total_minutes(blocks)
    return {
        "title": title,
        "total_minutes": total_minutes,
        "blocks": blocks,
    }


def suggestion_from_workout(workout: Workout, language: str = "sv") -> str:
    w = finalize_workout(workout, language=language)
    mins = w["total_minutes"]
    title = w["title"]
    if title:
        title = title[:1].upper() + title[1:]
    # Avoid "25 minuters 25 minuters …" if title already embeds duration
    low = title.lower()
    if any(x in low for x in ("minut", " min", "min ")):
        return title
    if language == "en":
        return f"{mins}-minute {title}"
    return f"{mins} minuters {title}"


def justification_from_workout(workout: Workout, language: str = "sv") -> str:
    w = finalize_workout(workout, language=language)
    n = len(w["blocks"])
    mins = w["total_minutes"]
    if language == "en":
        return f"{n} blocks · {mins} min total — structure first, then move."
    return f"{n} block · {mins} min totalt — ett pass, klart."


def detail_from_workout(workout: Workout, language: str = "sv") -> str:
    """One-line card summary derived from blocks (never a separate free-text plan)."""
    w = finalize_workout(workout, language=language)
    parts: list[str] = []
    for b in w["blocks"][:6]:
        parts.append(_block_short(b, language))
    more = len(w["blocks"]) - len(parts)
    line = " → ".join(parts)
    if more > 0:
        line += f" (+{more})"
    return f"{w['total_minutes']} min: {line}"


def execution_from_workout(workout: Workout, language: str = "sv") -> dict[str, Any]:
    w = finalize_workout(workout, language=language)
    return {
        "type": "workout",
        "label": "Starta passet" if language == "sv" else "Start workout",
        "url": None,
        "detail": detail_from_workout(w, language),
        "workout": w,
    }


def block_duration_label(block: Block, language: str = "sv") -> str:
    sets = max(1, int(block.get("sets") or 1))
    rest = int(block.get("rest_seconds") or 0)
    if (block.get("type") or "reps") == "time":
        sec = int(block.get("seconds") or 0)
        if language == "en":
            base = f"{sec}s" if sets == 1 else f"{sets}×{sec}s"
        else:
            base = f"{sec}s" if sets == 1 else f"{sets}×{sec}s"
    else:
        reps = int(block.get("reps") or 0)
        if language == "en":
            base = f"{sets}×{reps}"
        else:
            base = f"{sets}×{reps}"
    if rest > 0 and sets > 1:
        base += f" · vila {rest}s" if language == "sv" else f" · rest {rest}s"
    return base


def _block_short(block: Block, language: str) -> str:
    return f"{block.get('name')} ({block_duration_label(block, language)})"


def _fallback_blocks(language: str) -> list[Block]:
    if language == "en":
        return [
            {"name": "Warm-up", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Easy pace, open the joints."},
            {"name": "Squats", "type": "reps", "sets": 3, "reps": 12, "rest_seconds": 45, "cue": "Chest up, knees track over toes."},
            {"name": "Push-ups", "type": "reps", "sets": 3, "reps": 8, "rest_seconds": 45, "cue": "Body in one line."},
            {"name": "Plank", "type": "time", "sets": 3, "seconds": 30, "rest_seconds": 30, "cue": "Brace the core."},
            {"name": "Cooldownoldown", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Breathe out slowly."},
        ]
    return [
        {"name": "Uppvärmning", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Lugn takt, mjuka leder."},
        {"name": "Knäböj", "type": "reps", "sets": 3, "reps": 12, "rest_seconds": 45, "cue": "Rak rygg, knäna över tårna."},
        {"name": "Armhävningar", "type": "reps", "sets": 3, "reps": 8, "rest_seconds": 45, "cue": "Kroppen i en linje."},
        {"name": "Plankan", "type": "time", "sets": 3, "seconds": 30, "rest_seconds": 30, "cue": "Spänn bålen, höften stilla."},
        {"name": "Avslutning", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Andas ut långsamt."},
    ]


def workout_templates(language: str = "sv") -> list[Workout]:
    """Canonical local pack — each entry is structure-only; text is derived later."""
    if language == "en":
        return [
            finalize_workout(
                {
                    "title": "full-body strength at home",
                    "blocks": [
                        {"name": "Warm-up", "type": "time", "sets": 1, "seconds": 180, "rest_seconds": 0, "cue": "March in place, arm circles."},
                        {"name": "Squats", "type": "reps", "sets": 3, "reps": 12, "rest_seconds": 45, "cue": "Chest up, knees over toes."},
                        {"name": "Push-ups", "type": "reps", "sets": 3, "reps": 8, "rest_seconds": 45, "cue": "Elbows ~45°."},
                        {"name": "Glute bridge", "type": "reps", "sets": 3, "reps": 12, "rest_seconds": 40, "cue": "Squeeze at the top."},
                        {"name": "Plank", "type": "time", "sets": 3, "seconds": 30, "rest_seconds": 30, "cue": "Neutral spine."},
                        {"name": "Cooldownoldown", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Slow nasal breaths."},
                    ],
                },
                language=language,
            ),
            finalize_workout(
                {
                    "title": "Zone-2 walk",
                    "blocks": [
                        {"name": "Easy start", "type": "time", "sets": 1, "seconds": 300, "rest_seconds": 0, "cue": "Talking pace."},
                        {"name": "Steady Zone-2", "type": "time", "sets": 1, "seconds": 1200, "rest_seconds": 0, "cue": "Even breathing, no sprint."},
                        {"name": "Cool walk", "type": "time", "sets": 1, "seconds": 300, "rest_seconds": 0, "cue": "Slow down gradually."},
                    ],
                },
                language=language,
            ),
            finalize_workout(
                {
                    "title": "HIIT",
                    "blocks": [
                        {"name": "Warm-up", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Light jog in place."},
                        {"name": "Squat pulses", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Stay low."},
                        {"name": "Push-up hold / reps", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Quality over speed."},
                        {"name": "Mountain climbers", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Hips steady."},
                        {"name": "Jumping jacks", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Soft landings."},
                        {"name": "Cooldownoldown", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Walk and breathe."},
                    ],
                },
                language=language,
            ),
            finalize_workout(
                {
                    "title": "yoga flow",
                    "blocks": [
                        {"name": "Breathing", "type": "time", "sets": 1, "seconds": 180, "rest_seconds": 0, "cue": "In through nose, long exhale."},
                        {"name": "Sun salutations", "type": "reps", "sets": 1, "reps": 5, "rest_seconds": 0, "cue": "Move with the breath."},
                        {"name": "Warrior II", "type": "time", "sets": 2, "seconds": 30, "rest_seconds": 15, "cue": "Front knee over ankle."},
                        {"name": "Cat-cow", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Slow spinal waves."},
                        {"name": "Child's pose", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Forehead down, soft jaw."},
                    ],
                },
                language=language,
            ),
            finalize_workout(
                {
                    "title": "push-up + squat ladder",
                    "blocks": [
                        {"name": "Warm-up", "type": "time", "sets": 1, "seconds": 90, "rest_seconds": 0, "cue": "Arm swings, bodyweight squats."},
                        {"name": "Push-ups", "type": "reps", "sets": 3, "reps": 10, "rest_seconds": 60, "cue": "Knees ok if needed."},
                        {"name": "Squats", "type": "reps", "sets": 3, "reps": 15, "rest_seconds": 60, "cue": "Heels down."},
                        {"name": "Cooldownoldown stretch", "type": "time", "sets": 1, "seconds": 90, "rest_seconds": 0, "cue": "Hip flexors and chest."},
                    ],
                },
                language=language,
            ),
        ]

    return [
        finalize_workout(
            {
                "title": "helkroppsstyrka hemma",
                "blocks": [
                    {"name": "Uppvärmning", "type": "time", "sets": 1, "seconds": 180, "rest_seconds": 0, "cue": "Marsch på stället, arma cirklar."},
                    {"name": "Knäböj", "type": "reps", "sets": 3, "reps": 12, "rest_seconds": 45, "cue": "Rak rygg, knäna över tårna."},
                    {"name": "Armhävningar", "type": "reps", "sets": 3, "reps": 8, "rest_seconds": 45, "cue": "Kroppen i en linje."},
                    {"name": "Höftlyft", "type": "reps", "sets": 3, "reps": 12, "rest_seconds": 40, "cue": "Kläm ihop rumpan i toppen."},
                    {"name": "Plankan", "type": "time", "sets": 3, "seconds": 30, "rest_seconds": 30, "cue": "Spänn bålen, höften stilla."},
                    {"name": "Avslutning", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Andas lugnt genom näsan."},
                ],
            },
            language=language,
        ),
        finalize_workout(
            {
                "title": "zon-2-promenad",
                "blocks": [
                    {"name": "Lugn start", "type": "time", "sets": 1, "seconds": 300, "rest_seconds": 0, "cue": "Prattakt — inte flås."},
                    {"name": "Jämn zon-2", "type": "time", "sets": 1, "seconds": 1200, "rest_seconds": 0, "cue": "Jämn andning hela vägen."},
                    {"name": "Nedvarvning", "type": "time", "sets": 1, "seconds": 300, "rest_seconds": 0, "cue": "Sakta ner gradvis."},
                ],
            },
            language=language,
        ),
        finalize_workout(
            {
                "title": "HIIT",
                "blocks": [
                    {"name": "Uppvärmning", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Lätt jogg på stället."},
                    {"name": "Knäböj", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Håll dig låg."},
                    {"name": "Armhävningar", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Kvalitet före fart."},
                    {"name": "Mountain climbers", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Höften stilla."},
                    {"name": "Jumping jacks", "type": "time", "sets": 4, "seconds": 40, "rest_seconds": 20, "cue": "Mjuka landningar."},
                    {"name": "Avslutning", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Gå och andas."},
                ],
            },
            language=language,
        ),
        finalize_workout(
            {
                "title": "yogaflöde",
                "blocks": [
                    {"name": "Andning", "type": "time", "sets": 1, "seconds": 180, "rest_seconds": 0, "cue": "In via näsan, lång utandning."},
                    {"name": "Solhälsningar", "type": "reps", "sets": 1, "reps": 5, "rest_seconds": 0, "cue": "Rör dig med andningen."},
                    {"name": "Krigarposition II", "type": "time", "sets": 2, "seconds": 30, "rest_seconds": 15, "cue": "Främre knät över ankeln."},
                    {"name": "Hund och katt", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Mjuka vågor i ryggen."},
                    {"name": "Barnets pose", "type": "time", "sets": 1, "seconds": 120, "rest_seconds": 0, "cue": "Pannan i golvet, käken mjuk."},
                ],
            },
            language=language,
        ),
        finalize_workout(
            {
                "title": "armhävningar + knäböj-stege",
                "blocks": [
                    {"name": "Uppvärmning", "type": "time", "sets": 1, "seconds": 90, "rest_seconds": 0, "cue": "Armsving och lätta knäböj."},
                    {"name": "Armhävningar", "type": "reps", "sets": 3, "reps": 10, "rest_seconds": 60, "cue": "Knän i golvet går bra."},
                    {"name": "Knäböj", "type": "reps", "sets": 3, "reps": 15, "rest_seconds": 60, "cue": "Hälarna i golvet."},
                    {"name": "Avslutningsstretch", "type": "time", "sets": 1, "seconds": 90, "rest_seconds": 0, "cue": "Höftböjare och bröst."},
                ],
            },
            language=language,
        ),
    ]


def candidate_from_workout(workout: Workout, language: str = "sv", *, wildcard: bool = False) -> dict[str, Any]:
    w = finalize_workout(workout, language=language)
    return {
        "suggestion": suggestion_from_workout(w, language),
        "justification": justification_from_workout(w, language),
        "wildcard": wildcard,
        "meta": {
            "minutes": w["total_minutes"],
            "workout": w,
        },
        "execution": execution_from_workout(w, language),
    }


def local_candidates(language: str = "sv") -> list[dict[str, Any]]:
    templates = workout_templates(language)
    out: list[dict[str, Any]] = []
    for i, w in enumerate(templates):
        out.append(candidate_from_workout(w, language, wildcard=(i == len(templates) - 1)))
    return out


def ensure_workout_on_candidate(
    candidate: dict[str, Any],
    *,
    language: str = "sv",
    budget_minutes: int | None = None,
) -> dict[str, Any]:
    """Attach finalized workout structure; rewrite suggestion/justification from it."""
    meta = dict(candidate.get("meta") or {})
    raw = meta.get("workout")
    if not isinstance(raw, dict) or not (raw.get("blocks") or []):
        # Match template by title keywords in suggestion
        raw = _match_template(str(candidate.get("suggestion") or ""), language)
    w = finalize_workout(raw, language=language)
    if budget_minutes is not None and w["total_minutes"] > int(budget_minutes) + 5:
        # Prefer a shorter template if over budget
        for t in workout_templates(language):
            if t["total_minutes"] <= int(budget_minutes) + 5:
                w = t
                break
    meta["minutes"] = w["total_minutes"]
    meta["workout"] = w
    out = dict(candidate)
    out["meta"] = meta
    out["suggestion"] = suggestion_from_workout(w, language)
    out["justification"] = justification_from_workout(w, language)
    out["execution"] = execution_from_workout(w, language)
    return out


def _match_template(suggestion: str, language: str) -> Workout:
    s = suggestion.lower()
    templates = workout_templates(language)
    keys = (
        ("yoga", "yoga"),
        ("hiit", "hiit"),
        ("tabata", "hiit"),
        ("promenad", "zon-2"),
        ("zon-2", "zon-2"),
        ("zon 2", "zon-2"),
        ("walk", "zone-2"),
        ("armhäv", "armhäv"),
        ("push-up", "push-up"),
        ("stege", "stege"),
        ("ladder", "ladder"),
        ("helkropp", "helkropp"),
        ("full-body", "full-body"),
        ("styrka", "helkropp"),
    )
    for needle, tag in keys:
        if needle in s:
            for t in templates:
                if tag in t["title"].lower():
                    return t
    return templates[0]


def get_workout_from_decision(cur: dict[str, Any] | None) -> Workout | None:
    if not isinstance(cur, dict):
        return None
    ctx = cur.get("context") or {}
    w = ctx.get("workout")
    if isinstance(w, dict) and w.get("blocks"):
        return finalize_workout(w, language="sv")
    return None
