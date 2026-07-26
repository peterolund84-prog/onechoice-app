# -*- coding: utf-8 -*-
"""Trendar nu — web-search grounded movie/series picks for Sweden.

Flow:
  1. Search (Grok web_search or injected fn) for titles talked about this month
  2. Keep only hits with ≥1 dated source from the last ~30 days
  3. Verify each title on TMDB (same gate as normal movie picks)
  4. Prefer titles available on the user's streaming services
  5. Cache grounded hits ~24h

No fabricated trends: empty search / no grounded / no TMDB → empty list.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("onechoice.movie_trending")

CACHE_TTL_SEC = 24 * 60 * 60
MAX_SOURCE_AGE_DAYS = 30

EMPTY_SV = "Hittar inga tydliga trender just nu — testa Humör istället"
EMPTY_EN = "No clear trends right now — try Mood instead"

# Optional test/runtime injection: (query: str) -> list[raw hit dict]
_SEARCH_OVERRIDE: Callable[[str], list[dict[str, Any]]] | None = None


def set_search_override(fn: Callable[[str], list[dict[str, Any]]] | None) -> None:
    """Tests inject a mocked search; pass None to restore default."""
    global _SEARCH_OVERRIDE
    _SEARCH_OVERRIDE = fn


def empty_message(language: str = "sv") -> str:
    return EMPTY_SV if language == "sv" else EMPTY_EN


def is_trending_mode(value: Any) -> bool:
    key = str(value or "").strip().lower()
    return key in ("trendar", "trending", "trendar_nu", "trendar nu")


def normalize_mode(value: Any) -> str:
    """Return 'trendar' or 'mood'."""
    return "trendar" if is_trending_mode(value) else "mood"


def mode_label(mode: str, language: str = "sv") -> str:
    if normalize_mode(mode) == "trendar":
        return "Trendar nu" if language == "sv" else "Trending"
    return "Humör" if language == "sv" else "Mood"


def _cache_path() -> Path:
    return Path(tempfile.gettempdir()) / "onechoice_movie_trending_cache.json"


def _cache_key(*, language: str, kind: str | None, month: str) -> str:
    return f"{language}|{kind or 'any'}|{month}"


def _load_cache() -> dict[str, Any]:
    path = _cache_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    try:
        _cache_path().write_text(
            json.dumps(data, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
    except Exception as exc:
        log.debug("trending cache write failed: %s", exc)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    # ISO date or datetime
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return date.fromisoformat(s[:10])
    except Exception:
        pass
    # 2026-07-01 / 1 juli 2026 / July 1, 2026 — light fallbacks
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except Exception:
            return None
    return None


def source_is_fresh(
    source: dict[str, Any],
    *,
    now: date | None = None,
    max_age_days: int = MAX_SOURCE_AGE_DAYS,
) -> bool:
    """True when source has a parseable date within max_age_days."""
    d = _parse_date(source.get("date") or source.get("published") or source.get("published_at"))
    if not d:
        return False
    today = now or datetime.now(timezone.utc).date()
    age = (today - d).days
    return 0 <= age <= int(max_age_days)


def filter_grounded_hits(
    hits: list[dict[str, Any]],
    *,
    now: date | None = None,
    max_age_days: int = MAX_SOURCE_AGE_DAYS,
) -> list[dict[str, Any]]:
    """Drop candidates without at least one fresh dated source naming them."""
    out: list[dict[str, Any]] = []
    for hit in hits or []:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or hit.get("suggestion") or "").strip()
        if not title:
            continue
        sources = hit.get("sources") if isinstance(hit.get("sources"), list) else []
        fresh = [s for s in sources if isinstance(s, dict) and source_is_fresh(s, now=now, max_age_days=max_age_days)]
        if not fresh:
            continue
        kind = str(hit.get("kind") or "series").strip().lower()
        if kind not in ("series", "film"):
            kind = "series"
        why = str(hit.get("why") or hit.get("reason") or hit.get("justification") or "").strip()
        out.append(
            {
                "title": title,
                "kind": kind,
                "why": why,
                "sources": fresh,
            }
        )
    return out


def _build_search_query(*, language: str, kind: str | None, month_label: str) -> str:
    kind_bit = ""
    if kind == "film":
        kind_bit = "filmer" if language == "sv" else "movies"
    elif kind == "series":
        kind_bit = "serier" if language == "sv" else "TV series"
    else:
        kind_bit = "filmer och serier" if language == "sv" else "movies and TV series"
    if language == "sv":
        return (
            f"Mest omtalade och trendande {kind_bit} i Sverige {month_label}. "
            "Lista konkreta titlar som nämns i artiklar, topplistor eller recensioner "
            "publicerade senaste 30 dagarna. Inkludera källa med datum."
        )
    return (
        f"Most talked-about and trending {kind_bit} in Sweden during {month_label}. "
        "List concrete titles named in articles, charts, or reviews from the last 30 days. "
        "Include source with date."
    )


def _extract_json_payload(text: str) -> list[dict[str, Any]]:
    raw = (text or "").strip()
    if not raw:
        return []
    # Fenced ```json ... ```
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Find first array/object
        start = raw.find("[")
        if start < 0:
            start = raw.find("{")
        if start < 0:
            return []
        try:
            data = json.loads(raw[start:])
        except json.JSONDecodeError:
            return []
    if isinstance(data, dict):
        items = data.get("titles") or data.get("candidates") or data.get("results") or []
    else:
        items = data
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def _grok_web_search(query: str, *, api_key: str) -> list[dict[str, Any]]:
    """Server-side grounded search via xAI Responses + web_search tool."""
    import llm_config
    import requests

    prompt = (
        f"{query}\n\n"
        "Return ONLY JSON (no prose) as:\n"
        "{\n"
        '  "titles": [\n'
        "    {\n"
        '      "title": "Exact title",\n'
        '      "kind": "series|film",\n'
        '      "why": "one short Swedish line why it is trending now",\n'
        '      "sources": [\n'
        '        {"name": "Outlet", "url": "https://...", "date": "YYYY-MM-DD"}\n'
        "      ]\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Rules: every title MUST have at least one source with an ISO date "
        "from the last 30 days that names the title. Max 8 titles. "
        "Prefer Sweden-relevant coverage (SVT, Aftonbladet, DN, MovieZine, Netflix Nordic charts)."
    )
    model = llm_config.text_model()
    resp = requests.post(
        "https://api.x.ai/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": [{"role": "user", "content": prompt}],
            "tools": [{"type": "web_search"}],
            "temperature": 0.2,
        },
        timeout=75,
    )
    if resp.status_code != 200:
        log.warning("trending web_search HTTP %s: %s", resp.status_code, resp.text[:240])
        return []
    payload = resp.json() or {}
    # Responses API shapes vary — collect text fields.
    chunks: list[str] = []
    if isinstance(payload.get("output_text"), str):
        chunks.append(payload["output_text"])
    output = payload.get("output") or payload.get("response") or []
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                chunks.append(item["text"])
            content = item.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and isinstance(part.get("text"), str):
                        chunks.append(part["text"])
            elif isinstance(content, str):
                chunks.append(content)
    if isinstance(payload.get("choices"), list):
        for ch in payload["choices"]:
            msg = (ch or {}).get("message") or {}
            if isinstance(msg.get("content"), str):
                chunks.append(msg["content"])
    text = "\n".join(chunks).strip()
    return _extract_json_payload(text)


def search_trending_hits(
    *,
    language: str = "sv",
    kind: str | None = None,
    api_key: str = "",
    now: datetime | None = None,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    """Return raw search hits (may be ungrounded). Uses 24h cache."""
    now = now or datetime.now(timezone.utc)
    month = now.strftime("%Y-%m")
    month_label = now.strftime("%B %Y")
    if language == "sv":
        months_sv = (
            "januari",
            "februari",
            "mars",
            "april",
            "maj",
            "juni",
            "juli",
            "augusti",
            "september",
            "oktober",
            "november",
            "december",
        )
        month_label = f"{months_sv[now.month - 1]} {now.year}"

    key = _cache_key(language=language, kind=kind, month=month)
    if use_cache and _SEARCH_OVERRIDE is None:
        cached = _load_cache()
        row = cached.get(key) if isinstance(cached, dict) else None
        if isinstance(row, dict):
            ts = float(row.get("ts") or 0)
            if time.time() - ts < CACHE_TTL_SEC and isinstance(row.get("hits"), list):
                return list(row["hits"])

    query = _build_search_query(language=language, kind=kind, month_label=month_label)
    hits: list[dict[str, Any]] = []
    try:
        if _SEARCH_OVERRIDE is not None:
            hits = list(_SEARCH_OVERRIDE(query) or [])
        elif api_key:
            hits = _grok_web_search(query, api_key=api_key)
        else:
            hits = []
    except Exception as exc:
        log.warning("trending search failed: %s", exc)
        hits = []

    # Never cache empty results — empty often means missing key / transient fail.
    if use_cache and _SEARCH_OVERRIDE is None and hits:
        cached = _load_cache()
        if not isinstance(cached, dict):
            cached = {}
        cached[key] = {"ts": time.time(), "hits": hits}
        _save_cache(cached)
    return hits


def verify_tmdb(
    title: str,
    *,
    kind: str = "series",
) -> dict[str, Any] | None:
    """TMDB lookup — same contract as normal movie picks."""
    try:
        import tmdb as tmdb_mod

        row = tmdb_mod.lookup_title(title, kind=kind)
        if not row:
            return None
        return dict(row)
    except Exception as exc:
        log.debug("trending tmdb failed for %s: %s", title, exc)
        return None


def _on_user_services(meta: dict[str, Any], user_services: list[str]) -> bool:
    services = {str(s).strip().lower() for s in user_services if s}
    if not services:
        return True
    svc = str(meta.get("service") or "").strip().lower()
    if svc and svc in services:
        return True
    # Catalog overlap from mocks when present
    try:
        import mocks

        title = str(meta.get("title") or "").strip().lower()
        row = mocks.STREAMING_CATALOG.get(title)
        if row and (services & set(row.get("services") or set())):
            return True
    except Exception:
        pass
    return False


def build_trending_candidates(
    *,
    language: str = "sv",
    fmt: str | None = None,
    user_services: list[str] | None = None,
    api_key: str = "",
    now: datetime | None = None,
    use_cache: bool = True,
    search_hits: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Grounded + TMDB-verified candidates, service-available first.

    Paywalled / unavailable titles are kept only at the end and marked
    ``meta.paywalled`` so the pipeline can refuse to pick them.
    """
    import movie_domain as md

    fmt_n = md.normalize_format(fmt) if fmt else None
    want_kind = md.format_kind(fmt_n) if fmt_n else None
    # Avsnitt / Ny serie → series; Film → film; unknown → both
    kind_filter = want_kind if want_kind in ("series", "film") else None

    raw = (
        list(search_hits)
        if search_hits is not None
        else search_trending_hits(
            language=language,
            kind=kind_filter,
            api_key=api_key,
            now=now,
            use_cache=use_cache,
        )
    )
    grounded = filter_grounded_hits(
        raw,
        now=(now.date() if isinstance(now, datetime) else now),
    )
    if kind_filter:
        grounded = [h for h in grounded if h.get("kind") == kind_filter] or grounded

    services = list(user_services or [])
    available: list[dict[str, Any]] = []
    paywalled: list[dict[str, Any]] = []
    chart_fallback = False

    def _append_cand(
        *,
        display: str,
        kind: str,
        why: str,
        tmdb_row: dict[str, Any],
        sources: list[Any] | None = None,
        trending_source: str = "web",
    ) -> None:
        catalog_title = display.lower()
        meta: dict[str, Any] = {
            "title": catalog_title,
            "kind": kind,
            "trending": True,
            "trending_source": trending_source,
            "local_pack": False,
            "sources": list(sources or []),
            "tmdb_id": tmdb_row.get("tmdb_id"),
            "poster_url": tmdb_row.get("poster_url"),
            "vote_average": tmdb_row.get("vote_average"),
            "year": tmdb_row.get("year"),
            "display_title": display,
        }
        try:
            import mocks

            match = mocks.streaming_availability(
                catalog_title,
                user_services=services or ["netflix", "svt_play"],
                max_minutes=None,
                allow_rentals=False,
            )
            if match:
                meta["service"] = match.get("service")
                meta["runtime_min"] = match.get("runtime_min")
        except Exception:
            pass

        cand = {
            "suggestion": display,
            "justification": why,
            "wildcard": False,
            "meta": meta,
        }
        if services and not _on_user_services(meta, services):
            meta["paywalled"] = True
            paywalled.append(cand)
        else:
            meta["paywalled"] = False
            available.append(cand)

    for hit in grounded:
        title = str(hit["title"]).strip()
        kind = str(hit.get("kind") or "series")
        tmdb_row = verify_tmdb(title, kind=kind)
        if not tmdb_row:
            continue
        display = str(tmdb_row.get("title") or title).strip()
        why = str(hit.get("why") or "").strip()
        if not why:
            why = (
                "Snackas överallt just nu — syns i listor och snack den här månaden."
                if language == "sv"
                else "Everyone’s talking about it — showing up in charts this month."
            )
        why = re.sub(r"\s+", " ", why).strip()
        if len(why) > 160:
            why = why[:157].rstrip() + "…"
        _append_cand(
            display=display,
            kind=kind,
            why=why,
            tmdb_row=tmdb_row,
            sources=hit.get("sources") or [],
            trending_source="web",
        )

    # No grounded web hits → honest TMDB week-chart fallback so Trendar still works.
    if not available and not paywalled:
        chart_fallback = True
        try:
            import tmdb as tmdb_mod

            kinds = [kind_filter] if kind_filter in ("series", "film") else ["series", "film"]
            seen: set[str] = set()
            for k in kinds:
                for row in tmdb_mod.trending_titles(kind=k, limit=8):
                    display = str(row.get("title") or "").strip()
                    if not display:
                        continue
                    key = display.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    why = (
                        "Populärt just nu — syns i TMDB:s trendlista den här veckan."
                        if language == "sv"
                        else "Popular right now — on TMDB’s trending chart this week."
                    )
                    _append_cand(
                        display=display,
                        kind=str(row.get("kind") or k),
                        why=why,
                        tmdb_row=row,
                        sources=[],
                        trending_source="tmdb_chart",
                    )
        except Exception as exc:
            log.warning("trending TMDB chart fallback failed: %s", exc)
            chart_fallback = False

    if chart_fallback:
        log.info("trending using TMDB chart fallback (%d candidates)", len(available) + len(paywalled))

    # Available first — paywalled deprioritised (never preferred as the pick)
    return available + paywalled


def pick_trending_candidate(
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """First non-paywalled candidate, or None."""
    for c in candidates or []:
        meta = c.get("meta") if isinstance(c.get("meta"), dict) else {}
        if meta.get("paywalled"):
            continue
        return c
    return None
