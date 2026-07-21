# -*- coding: utf-8 -*-
"""Movie domain: format (time) + mood inputs — inferred, confirmable chips."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

# Format = time commitment (not content genre)
FORMATS: dict[str, dict[str, Any]] = {
    "avsnitt": {
        "sv": "Avsnitt",
        "en": "Episode",
        "kind": "series",
        "max_minutes": 50,
        "repeat_days": 3,
    },
    "film": {
        "sv": "Film",
        "en": "Movie",
        "kind": "film",
        "max_minutes": 140,
        "repeat_days": 14,
    },
    "ny_serie": {
        "sv": "Ny serie",
        "en": "New series",
        "kind": "series",
        "max_minutes": 60,  # pilot
        "repeat_days": 7,
    },
}

FORMAT_ORDER = ("avsnitt", "film", "ny_serie")

# Mood = how people choose (NOT catalog genre)
MOODS: dict[str, dict[str, Any]] = {
    "avkopplat": {
        "sv": "Avkopplat",
        "en": "Unwind",
        "genres": ("comfort", "comedy", "feel-good", "familiar", "slice-of-life"),
        "tone": "low cognitive load, familiar, comfort rewatch OK",
    },
    "spanning": {
        "sv": "Spänning",
        "en": "Thrills",
        "genres": ("thriller", "crime", "action", "suspense", "spy"),
        "tone": "high pace, tension, keep me hooked",
    },
    "skratta": {
        "sv": "Skratta",
        "en": "Laugh",
        "genres": ("comedy", "sitcom", "romcom", "satire"),
        "tone": "funny, light, laughs over plot density",
    },
    "lar_mig": {
        "sv": "Lär mig något",
        "en": "Learn something",
        "genres": ("documentary", "docuseries", "science", "history", "nature"),
        "tone": "curious, informative, still watchable tonight",
    },
    "med_barnen": {
        "sv": "Med barnen",
        "en": "With kids",
        "genres": ("family", "animation", "kids", "adventure"),
        "tone": "age-appropriate for household kids — hard constraint",
        "kids_only": True,
    },
}

MOOD_ORDER = ("avkopplat", "spanning", "skratta", "lar_mig", "med_barnen")

# Local catalog hints keyed by mood (titles must exist in mocks.STREAMING_CATALOG
# or be generic enough to pass feasibility without a named paywalled title).
_MOOD_LOCAL: dict[str, dict[str, list[dict[str, Any]]]] = {
    "avkopplat": {
        "sv": [
            {
                "suggestion": "Seinfeld",
                "justification": "Lugn bekant sitcom — noll energi, måndagssoffa.",
                "meta": {"title": "seinfeld", "kind": "series"},
            },
            {
                "suggestion": "Vänner",
                "justification": "Varm och lätt — ett avsnitt och du är klar.",
                "meta": {"title": "vänner", "kind": "series"},
            },
        ],
        "en": [
            {
                "suggestion": "Seinfeld",
                "justification": "Familiar comfort — zero effort, weekday sofa.",
                "meta": {"title": "seinfeld", "kind": "series"},
            },
            {
                "suggestion": "Friends",
                "justification": "Warm and easy — one episode and you're done.",
                "meta": {"title": "friends", "kind": "series"},
            },
        ],
    },
    "spanning": {
        "sv": [
            {
                "suggestion": "The Night Agent",
                "justification": "Högt tempo när du vill bli uppslukad.",
                "meta": {"title": "the night agent", "kind": "series"},
            },
            {
                "suggestion": "Andor",
                "justification": "Tät spänning — ett avsnitt som känns som film.",
                "meta": {"title": "andor", "kind": "series"},
            },
            {
                "suggestion": "Dune",
                "justification": "Episk spänning — en filmkväll som tar dig någonstans.",
                "meta": {"title": "dune", "kind": "film"},
            },
        ],
        "en": [
            {
                "suggestion": "The Night Agent",
                "justification": "High pace when you want to disappear into a story.",
                "meta": {"title": "the night agent", "kind": "series"},
            },
            {
                "suggestion": "Andor",
                "justification": "Tight tension — one episode that feels like a film.",
                "meta": {"title": "andor", "kind": "series"},
            },
            {
                "suggestion": "Dune",
                "justification": "Epic thrills — a film night that takes you somewhere.",
                "meta": {"title": "dune", "kind": "film"},
            },
        ],
    },
    "skratta": {
        "sv": [
            {
                "suggestion": "Seinfeld",
                "justification": "Torr humor i lagom dos — skratt utan ansträngning.",
                "meta": {"title": "seinfeld", "kind": "series"},
            },
            {
                "suggestion": "Vänner",
                "justification": "Klassiska skratt — lätt efter en lång dag.",
                "meta": {"title": "vänner", "kind": "series"},
            },
        ],
        "en": [
            {
                "suggestion": "Seinfeld",
                "justification": "Dry laughs in a right-sized dose.",
                "meta": {"title": "seinfeld", "kind": "series"},
            },
            {
                "suggestion": "Friends",
                "justification": "Classic laughs — easy after a long day.",
                "meta": {"title": "friends", "kind": "series"},
            },
        ],
    },
    "lar_mig": {
        "sv": [
            {
                "suggestion": "Our Planet",
                "justification": "Lär dig om naturen — ett avsnitt, lagom tempo.",
                "meta": {"title": "our planet", "kind": "series", "genres": ["documentary"]},
            },
            {
                "suggestion": "Explained",
                "justification": "Kort och klokt — ett ämne, en kväll.",
                "meta": {"title": "explained", "kind": "series", "genres": ["documentary"]},
            },
            {
                "suggestion": "Det sista kapitlet",
                "justification": "Svenskt och tankeväckande — perfekt för en nyfiken kväll.",
                "meta": {"title": "det sista kapitlet", "kind": "series", "genres": ["documentary"]},
            },
            {
                "suggestion": "My Octopus Teacher",
                "justification": "En film som lär och stillar — under 90 minuter.",
                "meta": {"title": "my octopus teacher", "kind": "film", "genres": ["documentary", "nature"]},
            },
        ],
        "en": [
            {
                "suggestion": "Our Planet",
                "justification": "Learn about the natural world — one episode, easy pace.",
                "meta": {"title": "our planet", "kind": "series", "genres": ["documentary"]},
            },
            {
                "suggestion": "Explained",
                "justification": "Short and smart — one topic, one evening.",
                "meta": {"title": "explained", "kind": "series", "genres": ["documentary"]},
            },
            {
                "suggestion": "Det sista kapitlet",
                "justification": "Swedish and thought-provoking — curious evening without stress.",
                "meta": {"title": "det sista kapitlet", "kind": "series", "genres": ["documentary"]},
            },
            {
                "suggestion": "My Octopus Teacher",
                "justification": "A film that teaches and calms — under 90 minutes.",
                "meta": {"title": "my octopus teacher", "kind": "film", "genres": ["documentary", "nature"]},
            },
        ],
    },
    "med_barnen": {
        "sv": [
            {
                "suggestion": "Hilda",
                "justification": "Med barnen — äventyr i lagom dos, klart innan läggdags.",
                "meta": {"title": "hilda", "kind": "series", "kids_ok": True, "max_age_rating": 7},
            },
            {
                "suggestion": "Kung Fu Panda",
                "justification": "Familjefilm med hjärta — alla skrattar i soffan.",
                "meta": {"title": "kung fu panda", "kind": "film", "kids_ok": True, "max_age_rating": 7},
            },
        ],
        "en": [
            {
                "suggestion": "Hilda",
                "justification": "With the kids — right-sized adventure, done before bedtime.",
                "meta": {"title": "hilda", "kind": "series", "kids_ok": True, "max_age_rating": 7},
            },
            {
                "suggestion": "Kung Fu Panda",
                "justification": "Family film with heart — everyone laughs on the couch.",
                "meta": {"title": "kung fu panda", "kind": "film", "kids_ok": True, "max_age_rating": 7},
            },
        ],
    },
}

# Adult / not-for-kids title keys (catalog + common names)
_ADULT_TITLES = frozenset(
    {
        "the night agent",
        "andor",
        "succession",
        " Succession",
        "dune",
        "top gun maverick",
        "wednesday",  # teen/dark — not for young kids
        "the bear",
        "det sista kapitlet",
    }
)


def format_label(
    key: str,
    language: str = "sv",
    *,
    in_progress_series: str | None = None,
) -> str:
    row = FORMATS.get(key) or {}
    base = str(row.get(language) or row.get("sv") or key)
    if key == "avsnitt" and in_progress_series:
        name = str(in_progress_series).strip()
        if name:
            if language == "sv":
                return f"Nästa avsnitt av {name}"
            return f"Next episode of {name}"
    return base


def mood_label(key: str, language: str = "sv") -> str:
    row = MOODS.get(key) or {}
    return str(row.get(language) or row.get("sv") or key)


def max_minutes(fmt: str) -> int:
    return int((FORMATS.get(fmt) or FORMATS["avsnitt"]).get("max_minutes") or 50)


def format_kind(fmt: str) -> str:
    return str((FORMATS.get(fmt) or {}).get("kind") or "series")


def mood_guidance(mood: str, language: str = "sv") -> str:
    """LLM prompt guidance — soft genre/tone clusters, not a hard filter."""
    row = MOODS.get(mood) or MOODS["avkopplat"]
    genres = ", ".join(row.get("genres") or ())
    tone = str(row.get("tone") or "")
    if language == "sv":
        return (
            f"Humör={mood_label(mood, 'sv')}. "
            f"Intern genre-/tonvägledning (inte hårt filter): {genres}. "
            f"Ton: {tone}. "
            "Justification MUST reference the mood in one warm line "
            '(ex: "Lugn brittisk deckare — perfekt måndagssoffa."). '
            "Comfort rewatches are valid for Avkopplat. "
            "ONE suggestion only — never a browse list."
        )
    return (
        f"Mood={mood_label(mood, 'en')}. "
        f"Internal genre/tone guidance (not a hard filter): {genres}. "
        f"Tone: {tone}. "
        "Justification MUST reference the mood in one warm line. "
        "Comfort rewatches are valid for Unwind. "
        "ONE suggestion only — never a browse list."
    )


def is_kids_mood(mood: str) -> bool:
    return bool((MOODS.get(mood) or {}).get("kids_only"))


def default_format(
    hour: int | None = None,
    *,
    weekday: bool | None = None,
    now: datetime | None = None,
    in_progress_series: str | None = None,
) -> str:
    """
    Preselect format from clock + day:
      weekday 20:00+ → Avsnitt
      Fri/Sat evening (17+) → Film
      weekend afternoon (12–17) → Ny serie
      else → Avsnitt (if series in progress) or Film daytime weekday → Avsnitt
    """
    if now is not None:
        hour = now.hour
        if weekday is None:
            weekday = now.weekday() < 5
    if hour is None:
        now = datetime.now().astimezone()
        hour = now.hour
        if weekday is None:
            weekday = now.weekday() < 5
    if weekday is None:
        weekday = datetime.now().astimezone().weekday() < 5

    # In-progress series grounds Avsnitt like leftovers — prefer it evenings
    if in_progress_series and (hour >= 19 or not weekday):
        return "avsnitt"

    if weekday:
        if hour >= 20:
            return "avsnitt"
        if hour >= 17:
            return "film"
        return "avsnitt"

    # Weekend
    if 12 <= hour < 17:
        return "ny_serie"
    if hour >= 17:
        return "film"
    return "avsnitt"


def default_mood(
    hour: int | None = None,
    *,
    weekday: bool | None = None,
    now: datetime | None = None,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """
    Preselect mood: history per time-slot when data exists;
    else Avkopplat on weekdays, Spänning on weekends.
    """
    if now is not None:
        hour = now.hour
        if weekday is None:
            weekday = now.weekday() < 5
    if hour is None:
        now = datetime.now().astimezone()
        hour = now.hour
        if weekday is None:
            weekday = now.weekday() < 5
    if weekday is None:
        weekday = datetime.now().astimezone().weekday() < 5

    slot = _hour_bucket(hour)
    from_hist = _mood_from_history(history or [], slot=slot, weekday=weekday)
    if from_hist:
        return from_hist
    return "avkopplat" if weekday else "spanning"


def _hour_bucket(hour: int) -> str:
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour <= 22:
        return "evening"
    return "late"


def _mood_from_history(
    history: list[dict[str, Any]],
    *,
    slot: str,
    weekday: bool,
) -> str | None:
    """Most common accepted mood in the same time-slot (needs ≥2 samples)."""
    counts: Counter[str] = Counter()
    for row in history:
        if str(row.get("status") or "") not in ("accepted", "locked"):
            continue
        ctx = row.get("context") or {}
        if isinstance(ctx, str):
            continue
        mood = str(ctx.get("mood") or "")
        if mood not in MOODS:
            continue
        try:
            h = int(ctx.get("hour") if ctx.get("hour") is not None else -1)
        except (TypeError, ValueError):
            h = -1
        if h < 0:
            continue
        if _hour_bucket(h) != slot:
            continue
        is_wd = ctx.get("weekday")
        if is_wd is None and ctx.get("is_weekend") is not None:
            is_wd = not bool(ctx.get("is_weekend"))
        if is_wd is not None and bool(is_wd) != weekday:
            continue
        counts[mood] += 1
    if not counts:
        return None
    top, n = counts.most_common(1)[0]
    return top if n >= 2 else None


def find_in_progress_series(
    history: list[dict[str, Any]],
) -> str | None:
    """
    Grounded like leftovers: only when an accepted series decision exists
    without a completed flag. Always return the series name.
    """
    for row in history:
        if str(row.get("status") or "") not in ("accepted", "locked"):
            continue
        ctx = row.get("context") or {}
        if not isinstance(ctx, dict):
            continue
        if ctx.get("series_completed") or ctx.get("completed"):
            continue
        fmt = str(ctx.get("format") or "")
        kind = str(ctx.get("kind") or (ctx.get("meta") or {}).get("kind") or "")
        if fmt not in ("avsnitt", "ny_serie") and kind != "series":
            # Heuristic: runtime-ish episode or explicit series meta
            meta = ctx.get("meta") if isinstance(ctx.get("meta"), dict) else {}
            if str(meta.get("kind") or "") != "series":
                continue
        name = (
            str(ctx.get("series_title") or "").strip()
            or str((ctx.get("meta") or {}).get("title") or "").strip()
            or str(row.get("suggestion") or "").strip()
        )
        if not name:
            continue
        # Skip vague generics
        low = name.lower()
        if low.startswith("ett avsnitt") or low.startswith("one episode"):
            continue
        if low.startswith("en familje") or low.startswith("a family"):
            continue
        if low.startswith("ett kort") or low.startswith("a short"):
            continue
        # Title-case display
        return name.title() if name.islower() else name
    return None


def normalize_format(value: str | None) -> str:
    v = str(value or "").strip().lower()
    return v if v in FORMATS else "avsnitt"


def has_catalog_title(candidate: dict[str, Any]) -> bool:
    """True when meta.title names a concrete title (not a vague category phrase)."""
    meta = candidate.get("meta") if isinstance(candidate.get("meta"), dict) else {}
    title = str(meta.get("title") or "").strip()
    return bool(title) and not is_vague_movie_phrase(title)


def is_vague_movie_phrase(text: str) -> bool:
    """Detect category placeholders like 'Ett kort dokumentäravsnitt'."""
    low = str(text or "").strip().lower()
    if not low:
        return True
    vague_prefixes = (
        "ett ",
        "en ",
        "a ",
        "an ",
        "one ",
    )
    vague_fragments = (
        "documentäravsnitt",
        "documentary episode",
        "familjevänlig",
        "family-friendly",
        "family episode",
        "familjeavsnitt",
        "naturdokumentär",
        "nature documentary",
        "under 90",
        "under two hours",
        "avsnitt av en",
        "episode of a",
    )
    if any(low.startswith(p) for p in vague_prefixes):
        return True
    return any(frag in low for frag in vague_fragments)


def normalize_mood(value: str | None) -> str:
    v = str(value or "").strip().lower()
    aliases = {
        "spänning": "spanning",
        "lär mig något": "lar_mig",
        "lar mig": "lar_mig",
        "learn": "lar_mig",
        "with kids": "med_barnen",
        "kids": "med_barnen",
        "unwind": "avkopplat",
        "laugh": "skratta",
        "thrills": "spanning",
    }
    v = aliases.get(v, v)
    return v if v in MOODS else "avkopplat"


def kids_ages_from_profile(profile: dict[str, Any]) -> list[int]:
    movie = profile.get("movie") or {}
    weekend = profile.get("weekend") or {}
    ages = movie.get("kids_ages") or weekend.get("kids_ages") or []
    out: list[int] = []
    for a in ages:
        try:
            out.append(int(a))
        except (TypeError, ValueError):
            continue
    return out


def max_kids_age(profile: dict[str, Any]) -> int | None:
    ages = kids_ages_from_profile(profile)
    return max(ages) if ages else None


def is_age_appropriate(
    candidate: dict[str, Any],
    profile: dict[str, Any],
) -> bool:
    """Hard gate for Med barnen — reject known adult titles / high ratings."""
    suggestion = str(candidate.get("suggestion") or "").lower()
    meta = candidate.get("meta") if isinstance(candidate.get("meta"), dict) else {}
    title = str(meta.get("title") or suggestion).strip().lower()
    if title in _ADULT_TITLES or any(a in suggestion for a in _ADULT_TITLES):
        return False
    if meta.get("kids_ok") is True:
        return True
    rating = meta.get("age_rating") or meta.get("max_age_rating")
    if rating is None:
        # Unknown named catalog title without kids flag → fail closed for kids mood
        try:
            import mocks

            if title in mocks.STREAMING_CATALOG or any(
                k in suggestion for k in mocks.STREAMING_CATALOG
            ):
                return False
        except Exception:
            pass
        # Vague family wording OK
        return any(
            w in suggestion
            for w in ("familj", "family", "barn", "kids", "animation", "animerad")
        )
    try:
        rating_i = int(rating)
    except (TypeError, ValueError):
        return False
    max_age = max_kids_age(profile)
    # If no ages on profile, still require kids_ok / low rating ≤7
    if max_age is None:
        return rating_i <= 7
    return rating_i <= max_age


def matches_format(candidate: dict[str, Any], fmt: str) -> bool:
    """Soft kind check — prefer matching kind; vague OK."""
    want = format_kind(fmt)
    meta = candidate.get("meta") if isinstance(candidate.get("meta"), dict) else {}
    kind = str(meta.get("kind") or "").lower()
    if not kind:
        return True  # vague / LLM without kind — don't hard-fail
    return kind == want


def local_candidates(
    *,
    fmt: str,
    mood: str,
    language: str = "sv",
    in_progress_series: str | None = None,
) -> list[dict[str, Any]]:
    """Mood-biased local pack filtered to format kind when possible."""
    lang = "sv" if language == "sv" else "en"
    mood_n = normalize_mood(mood)
    fmt_n = normalize_format(fmt)
    want_kind = format_kind(fmt_n)
    pack = list((_MOOD_LOCAL.get(mood_n) or _MOOD_LOCAL["avkopplat"]).get(lang) or [])

    # Grounded next-episode suggestion when format is avsnitt + series in progress
    if fmt_n == "avsnitt" and in_progress_series:
        name = str(in_progress_series).strip()
        if lang == "sv":
            pack.insert(
                0,
                {
                    "suggestion": name,
                    "justification": f"Nästa avsnitt av {name} — du är mitt i det.",
                    "meta": {
                        "title": name.lower(),
                        "kind": "series",
                        "series_title": name,
                        "in_progress": True,
                        "local_pack": True,
                    },
                },
            )
        else:
            pack.insert(
                0,
                {
                    "suggestion": name,
                    "justification": f"Next episode of {name} — you're in the middle of it.",
                    "meta": {
                        "title": name.lower(),
                        "kind": "series",
                        "series_title": name,
                        "in_progress": True,
                        "local_pack": True,
                    },
                },
            )

    out: list[dict[str, Any]] = []
    for c in pack:
        meta = dict(c.get("meta") or {})
        kind = str(meta.get("kind") or "")
        if kind and kind != want_kind:
            # For film format, skip series-only comfort packs unless mood is learn/kids vague
            if want_kind == "film" and kind == "series":
                continue
            if want_kind == "series" and kind == "film":
                continue
        meta.setdefault("kind", want_kind)
        meta["format"] = fmt_n
        meta["mood"] = mood_n
        meta["local_pack"] = True
        out.append({**c, "meta": meta})

    if not out:
        # Last resort: reuse avkopplat comfort titles (always named + streamable).
        fallback = list((_MOOD_LOCAL.get("avkopplat") or {}).get(lang) or [])
        for c in fallback:
            meta = dict(c.get("meta") or {})
            kind = str(meta.get("kind") or "")
            if kind and kind != want_kind:
                continue
            meta.setdefault("kind", want_kind)
            meta["format"] = fmt_n
            meta["mood"] = mood_n
            meta["local_pack"] = True
            out.append({**c, "meta": meta})
            if len(out) >= 2:
                break
    return out[:5]


def apply_context(
    ctx: dict[str, Any],
    *,
    fmt: str,
    mood: str,
    in_progress_series: str | None = None,
) -> dict[str, Any]:
    """Write format+mood (+ derived minutes/kind) onto decision context."""
    fmt_n = normalize_format(fmt)
    mood_n = normalize_mood(mood)
    out = dict(ctx)
    out["format"] = fmt_n
    out["mood"] = mood_n
    out["kind"] = format_kind(fmt_n)
    out["available_minutes"] = max_minutes(fmt_n)
    if in_progress_series:
        out["in_progress_series"] = in_progress_series
        out["series_title"] = in_progress_series
    return out
