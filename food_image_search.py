# -*- coding: utf-8 -*-
"""AI-sourced dish images via xAI web_search (enable_image_search).

Fallback chain (never show a wrong photo; never break a decision):
  1. Validated AI image URL (cached 24h) — skipped if AI search disabled
  2. Local keyword library (dish_images.resolve_dish_image)
  3. None → tonal placeholder in the UI

EVERY public entry point catches exceptions and returns a safe placeholder.
If enable_image_search is unsupported on the current model/endpoint, we disable
AI image search for the process lifetime and fall back — never retry-crash.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode, urlparse

import requests

log = logging.getLogger("onechoice.food_image_search")

CACHE_TTL_SEC = 24 * 60 * 60
_SEARCH_OVERRIDE: Callable[[str], str | None] | None = None

# Process-lifetime kill switch when the API rejects enable_image_search / responses.
_AI_IMAGE_SEARCH_DISABLED = False
_AI_IMAGE_SEARCH_DISABLE_REASON = ""
_RAW_RESPONSE_LOGGED = False

_PLACEHOLDER: dict[str, Any] = {
    "url": None,
    "source": "placeholder",
    "remote_url": None,
}

# Hosts we are willing to proxy for food photos (plus common CDNs).
_ALLOWED_IMAGE_HOST_SUFFIXES = (
    ".googleusercontent.com",
    ".ggpht.com",
    ".gstatic.com",
    ".bing.com",
    ".bing.net",
    ".msn.com",
    ".pinimg.com",
    ".unsplash.com",
    ".amazonaws.com",
    ".cloudfront.net",
    ".wp.com",
    ".wordpress.com",
    ".bbc.co.uk",
    ".bbci.co.uk",
    ".guim.co.uk",
    ".nyt.com",
    ".mzstatic.com",
    ".twimg.com",
    ".flickr.com",
    ".staticflickr.com",
    ".imgur.com",
    ".wikimedia.org",
    ".wikipedia.org",
)

_UNSUPPORTED_MARKERS = (
    "enable_image_search",
    "image_search",
    "unknown tool",
    "unknown parameter",
    "unsupported",
    "invalid tool",
    "not supported",
    "unrecognized",
    "extra inputs are not permitted",
    "web_search",
)


def set_search_override(fn: Callable[[str], str | None] | None) -> None:
    """Tests inject a mocked image URL (or None); pass None to restore."""
    global _SEARCH_OVERRIDE
    _SEARCH_OVERRIDE = fn


def reset_ai_image_search_state() -> None:
    """Tests only — re-enable AI search and clear disable reason."""
    global _AI_IMAGE_SEARCH_DISABLED, _AI_IMAGE_SEARCH_DISABLE_REASON, _RAW_RESPONSE_LOGGED
    _AI_IMAGE_SEARCH_DISABLED = False
    _AI_IMAGE_SEARCH_DISABLE_REASON = ""
    _RAW_RESPONSE_LOGGED = False


def ai_image_search_enabled() -> bool:
    return not _AI_IMAGE_SEARCH_DISABLED


def ai_image_search_disable_reason() -> str:
    return _AI_IMAGE_SEARCH_DISABLE_REASON


def _disable_ai_image_search(reason: str) -> None:
    global _AI_IMAGE_SEARCH_DISABLED, _AI_IMAGE_SEARCH_DISABLE_REASON
    if _AI_IMAGE_SEARCH_DISABLED:
        return
    _AI_IMAGE_SEARCH_DISABLED = True
    _AI_IMAGE_SEARCH_DISABLE_REASON = (reason or "unsupported")[:500]
    log.warning(
        "AI dish image_search DISABLED for this process: %s",
        _AI_IMAGE_SEARCH_DISABLE_REASON,
    )


def _looks_unsupported(status: int, body: str) -> bool:
    low = (body or "").lower()
    if status in (400, 404, 422):
        if any(m in low for m in _UNSUPPORTED_MARKERS):
            return True
        # Generic bad-request on /responses tools often means the flag/model combo
        if "tool" in low and ("invalid" in low or "unknown" in low or "error" in low):
            return True
    return False


def _cache_path() -> Path:
    return Path(tempfile.gettempdir()) / "onechoice_food_image_cache.json"


def _cache_key(title: str) -> str:
    return re.sub(r"\s+", " ", (title or "").strip().lower())[:120]


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
        log.debug("food image cache write failed: %s", exc)


def _host_allowed(host: str) -> bool:
    h = (host or "").lower()
    if not h:
        return False
    if h in {"images.unsplash.com", "i.imgur.com", "cdn.pixabay.com"}:
        return True
    return any(h.endswith(suf) for suf in _ALLOWED_IMAGE_HOST_SUFFIXES)


def extract_markdown_image_urls(text: str) -> list[str]:
    """Pull http(s) URLs from Markdown image embeds and bare image links."""
    found: list[str] = []
    try:
        for m in re.finditer(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", text or ""):
            found.append(m.group(1).strip())
        for m in re.finditer(
            r"(https?://[^\s\"'<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s\"'<>]*)?)",
            text or "",
            re.I,
        ):
            u = m.group(1).strip().rstrip(").,;")
            if u not in found:
                found.append(u)
    except Exception as exc:
        log.debug("extract_markdown_image_urls failed: %s", exc)
    return found


def validate_image_url(url: str, *, timeout: float = 4.0) -> bool:
    """True when URL is reachable with an image content-type. Never raises."""
    try:
        s = (url or "").strip()
        if not s.startswith("http://") and not s.startswith("https://"):
            return False
        parsed = urlparse(s)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        resp = requests.head(
            s,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "OneChoice/1.0"},
        )
        ctype = (resp.headers.get("content-type") or "").lower()
        if resp.status_code < 400 and ctype.startswith("image/"):
            return True
        resp = requests.get(
            s,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "OneChoice/1.0", "Range": "bytes=0-1023"},
        )
        ctype = (resp.headers.get("content-type") or "").lower()
        ok = resp.status_code < 400 and ctype.startswith("image/")
        resp.close()
        return bool(ok)
    except Exception as exc:
        log.debug("image validate failed %s: %s", (url or "")[:80], exc)
        return False


def _collect_response_text(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    try:
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
                        if isinstance(part, dict) and isinstance(part.get("url"), str):
                            chunks.append(f"![]({part['url']})")
                        # Some payloads nest image results under image_url / image
                        for ik in ("image_url", "image"):
                            nested = part.get(ik) if isinstance(part, dict) else None
                            if isinstance(nested, str) and nested.startswith("http"):
                                chunks.append(f"![]({nested})")
                            if isinstance(nested, dict) and isinstance(
                                nested.get("url"), str
                            ):
                                chunks.append(f"![]({nested['url']})")
                elif isinstance(content, str):
                    chunks.append(content)
        if isinstance(payload.get("choices"), list):
            for ch in payload["choices"]:
                msg = (ch or {}).get("message") or {}
                if isinstance(msg.get("content"), str):
                    chunks.append(msg["content"])
    except Exception as exc:
        log.debug("collect_response_text failed: %s", exc)
    return "\n".join(chunks)


def _log_raw_response_once(label: str, payload: Any) -> None:
    """Log one raw /v1/responses body so we can see if image URLs appear."""
    global _RAW_RESPONSE_LOGGED
    if _RAW_RESPONSE_LOGGED:
        return
    _RAW_RESPONSE_LOGGED = True
    try:
        if isinstance(payload, (dict, list)):
            raw = json.dumps(payload, ensure_ascii=False)[:2500]
        else:
            raw = str(payload)[:2500]
        log.info("food image_search raw %s (truncated): %s", label, raw)
    except Exception as exc:
        log.debug("raw response log failed: %s", exc)


def _grok_image_search(title: str, *, api_key: str, timeout: float = 8.0) -> str | None:
    """Ask Grok web_search with enable_image_search for one matching dish photo.

    Never raises. Disables AI search for the process on unsupported API errors.
    """
    if _AI_IMAGE_SEARCH_DISABLED:
        return None
    try:
        import llm_config

        dish = (title or "").strip()
        if not dish:
            return None
        prompt = (
            f"Find one clear, appetizing food photograph of this exact dish: {dish!r}.\n"
            "Return ONLY a Markdown image embed for the best match, like "
            "![dish](https://...jpg). Prefer a plated home-cooked look matching the title. "
            "No collage, no packaging, no people faces. If nothing matches, return NONE."
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
                "tools": [{"type": "web_search", "enable_image_search": True}],
                "temperature": 0.2,
            },
            timeout=timeout,
        )
    except Exception as exc:
        log.warning("food image_search request failed: %s", exc)
        return None

    body_text = ""
    try:
        body_text = resp.text or ""
    except Exception:
        body_text = ""

    if resp.status_code != 200:
        log.warning(
            "food image_search HTTP %s: %s",
            resp.status_code,
            body_text[:400],
        )
        _log_raw_response_once(f"http_{resp.status_code}", body_text)
        if _looks_unsupported(resp.status_code, body_text):
            _disable_ai_image_search(
                f"HTTP {resp.status_code}: {body_text[:240]}"
            )
        return None

    try:
        payload = resp.json() or {}
    except Exception as exc:
        log.warning("food image_search JSON parse failed: %s", exc)
        _log_raw_response_once("non_json", body_text)
        return None

    _log_raw_response_once("ok", payload)

    # Explicit API error object inside 200 (rare but defensive)
    err = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(err, dict):
        msg = str(err.get("message") or err)
        log.warning("food image_search error payload: %s", msg[:300])
        if _looks_unsupported(400, msg):
            _disable_ai_image_search(msg[:240])
        return None

    try:
        text = _collect_response_text(payload if isinstance(payload, dict) else {})
    except Exception as exc:
        log.warning("food image_search collect text failed: %s", exc)
        return None

    if not text or "NONE" in text.strip().upper()[:20]:
        return None
    for url in extract_markdown_image_urls(text):
        try:
            if validate_image_url(url, timeout=min(4.0, timeout)):
                return url
        except Exception:
            continue
    return None


def search_dish_image_url(
    title: str,
    *,
    api_key: str = "",
    use_cache: bool = True,
    timeout: float = 8.0,
) -> str | None:
    """Return a validated AI image URL for the dish, or None. Never raises."""
    try:
        if _AI_IMAGE_SEARCH_DISABLED:
            return None
        key = _cache_key(title)
        if not key:
            return None
        if _SEARCH_OVERRIDE is not None:
            try:
                return _SEARCH_OVERRIDE(title)
            except Exception:
                return None
        if use_cache:
            cached = _load_cache()
            hit = cached.get(key) if isinstance(cached, dict) else None
            if isinstance(hit, dict) and (
                time.time() - float(hit.get("ts") or 0)
            ) < CACHE_TTL_SEC:
                url = hit.get("url")
                if isinstance(url, str) and url:
                    return url
                if hit.get("empty"):
                    return None
        if not (api_key or "").strip():
            return None
        url = _grok_image_search(
            title, api_key=api_key.strip(), timeout=max(2.0, float(timeout))
        )
        if use_cache:
            cached = _load_cache()
            if not isinstance(cached, dict):
                cached = {}
            cached[key] = {"ts": time.time(), "url": url, "empty": url is None}
            _save_cache(cached)
        return url
    except Exception as exc:
        log.warning("search_dish_image_url failed: %s", exc)
        return None


def proxy_url_for(remote_url: str) -> str:
    """Same-origin proxy path for HTML cards."""
    try:
        return f"/api/media/food?url={quote(remote_url or '', safe='')}"
    except Exception:
        return "/api/media/food?url="


def _try_local(
    title: str, category_hint: str | None
) -> dict[str, Any] | None:
    try:
        import dish_images as dimg

        path = dimg.resolve_dish_image(title, category_hint)
        if not path:
            return None
        q = urlencode({"title": title or "", "category": category_hint or ""})
        return {
            "url": f"/api/media/dish?{q}",
            "source": "local",
            "remote_url": None,
        }
    except Exception as exc:
        log.warning("local dish image resolve failed: %s", exc)
        return None


def resolve_food_image(
    title: str,
    category_hint: str | None = None,
    *,
    api_key: str = "",
    recipe_image_url: str | None = None,
    use_cache: bool = True,
    prefer_ai: bool = True,
) -> dict[str, Any]:
    """Resolve display URL + source: ai | local | placeholder.

    NEVER raises — a decision must render even when image lookup fails completely.
    Each fallback step is independently guarded.
    """
    try:
        # 1) Explicit recipe URL (already searched upstream)
        try:
            if isinstance(recipe_image_url, str) and recipe_image_url.strip():
                raw = recipe_image_url.strip()
                if raw.startswith("/api/media/"):
                    src = "ai" if "/food" in raw else "local"
                    return {"url": raw, "source": src, "remote_url": None}
                if validate_image_url(raw, timeout=4.0):
                    return {
                        "url": proxy_url_for(raw),
                        "source": "ai",
                        "remote_url": raw,
                    }
        except Exception as exc:
            log.warning("recipe image_url step failed: %s", exc)

        # 2) AI image search (skipped when disabled / no key / prefer_ai=False)
        try:
            if (
                prefer_ai
                and not _AI_IMAGE_SEARCH_DISABLED
                and (api_key or "").strip()
            ):
                ai_url = search_dish_image_url(
                    title,
                    api_key=api_key,
                    use_cache=use_cache,
                    timeout=8.0,
                )
                if ai_url:
                    log.info("dish image source=ai title=%r", title)
                    return {
                        "url": proxy_url_for(ai_url),
                        "source": "ai",
                        "remote_url": ai_url,
                    }
        except Exception as exc:
            log.warning("AI dish image step failed: %s", exc)

        # 3) Local keyword library
        local = _try_local(title, category_hint)
        if local:
            log.info("dish image source=local title=%r", title)
            return local

        # 4) Placeholder — never invent a wrong photo
        log.info("dish image source=placeholder title=%r", title)
        return dict(_PLACEHOLDER)
    except Exception as exc:
        log.warning("resolve_food_image failed completely: %s", exc)
        return dict(_PLACEHOLDER)
