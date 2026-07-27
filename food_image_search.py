# -*- coding: utf-8 -*-
"""AI-sourced dish images via xAI web_search (enable_image_search).

Fallback chain (never show a wrong photo):
  1. Validated AI image URL (cached 24h)
  2. Local keyword library (dish_images.resolve_dish_image)
  3. None → tonal placeholder in the UI

The keyword map alone cannot cover free LLM dish titles — AI search closes
the gap at the source (same model that named the dish).
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlparse

import requests

log = logging.getLogger("onechoice.food_image_search")

CACHE_TTL_SEC = 24 * 60 * 60
_SEARCH_OVERRIDE: Callable[[str], str | None] | None = None

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


def set_search_override(fn: Callable[[str], str | None] | None) -> None:
    """Tests inject a mocked image URL (or None); pass None to restore."""
    global _SEARCH_OVERRIDE
    _SEARCH_OVERRIDE = fn


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
    for m in re.finditer(r"!\[[^\]]*\]\((https?://[^)\s]+)\)", text or ""):
        found.append(m.group(1).strip())
    for m in re.finditer(r"(https?://[^\s\"'<>]+\.(?:jpg|jpeg|png|webp)(?:\?[^\s\"'<>]*)?)", text or "", re.I):
        u = m.group(1).strip().rstrip(").,;")
        if u not in found:
            found.append(u)
    return found


def validate_image_url(url: str, *, timeout: float = 8.0) -> bool:
    """True when URL looks like a reachable image (HEAD/GET content-type)."""
    s = (url or "").strip()
    if not s.startswith("http://") and not s.startswith("https://"):
        return False
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    # Prefer allowlisted hosts; still attempt validation for others but reject
    # clearly unsafe schemes/paths.
    try:
        resp = requests.head(
            s,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "OneChoice/1.0"},
        )
        ctype = (resp.headers.get("content-type") or "").lower()
        if resp.status_code < 400 and ctype.startswith("image/"):
            return True
        # Some CDNs block HEAD — try a tiny GET range
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
        log.debug("image validate failed %s: %s", s[:80], exc)
        return False


def _collect_response_text(payload: dict[str, Any]) -> str:
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
                    if isinstance(part, dict) and isinstance(part.get("url"), str):
                        chunks.append(f"![]({part['url']})")
            elif isinstance(content, str):
                chunks.append(content)
    if isinstance(payload.get("choices"), list):
        for ch in payload["choices"]:
            msg = (ch or {}).get("message") or {}
            if isinstance(msg.get("content"), str):
                chunks.append(msg["content"])
    return "\n".join(chunks)


def _grok_image_search(title: str, *, api_key: str, timeout: float = 8.0) -> str | None:
    """Ask Grok web_search with enable_image_search for one matching dish photo."""
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
    try:
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
    if resp.status_code != 200:
        log.warning("food image_search HTTP %s: %s", resp.status_code, resp.text[:200])
        return None
    try:
        text = _collect_response_text(resp.json() or {})
    except Exception as exc:
        log.warning("food image_search parse failed: %s", exc)
        return None
    if not text or "NONE" in text.strip().upper()[:20]:
        return None
    for url in extract_markdown_image_urls(text):
        if validate_image_url(url, timeout=min(4.0, timeout)):
            return url
    return None


def search_dish_image_url(
    title: str,
    *,
    api_key: str = "",
    use_cache: bool = True,
    timeout: float = 8.0,
) -> str | None:
    """Return a validated AI image URL for the dish, or None."""
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
        if isinstance(hit, dict) and (time.time() - float(hit.get("ts") or 0)) < CACHE_TTL_SEC:
            url = hit.get("url")
            if isinstance(url, str) and url:
                return url
            if hit.get("empty"):
                return None
    if not (api_key or "").strip():
        return None
    try:
        url = _grok_image_search(
            title, api_key=api_key.strip(), timeout=max(2.0, float(timeout))
        )
    except Exception as exc:
        log.warning("food image_search failed: %s", exc)
        url = None
    if use_cache:
        cached = _load_cache()
        if not isinstance(cached, dict):
            cached = {}
        cached[key] = {"ts": time.time(), "url": url, "empty": url is None}
        _save_cache(cached)
    return url


def proxy_url_for(remote_url: str) -> str:
    """Same-origin proxy path for HTML cards."""
    return f"/api/media/food?url={quote(remote_url, safe='')}"


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

    Never returns a mismatched local photo when AI failed — local is only used
    when it resolves; otherwise placeholder (url=None).
    """
    import dish_images as dimg
    from urllib.parse import urlencode

    # 1) Explicit recipe URL (already searched upstream)
    for candidate in (recipe_image_url,):
        if isinstance(candidate, str) and candidate.strip():
            raw = candidate.strip()
            if raw.startswith("/api/media/"):
                return {"url": raw, "source": "ai", "remote_url": None}
            if validate_image_url(raw):
                return {
                    "url": proxy_url_for(raw),
                    "source": "ai",
                    "remote_url": raw,
                }

    # 2) AI image search
    if prefer_ai and (api_key or "").strip():
        ai_url = search_dish_image_url(
            title, api_key=api_key, use_cache=use_cache, timeout=8.0
        )
        if ai_url:
            log.info("dish image source=ai title=%r", title)
            return {
                "url": proxy_url_for(ai_url),
                "source": "ai",
                "remote_url": ai_url,
            }

    # 3) Local keyword library
    path = dimg.resolve_dish_image(title, category_hint)
    if path:
        q = urlencode({"title": title or "", "category": category_hint or ""})
        log.info("dish image source=local title=%r", title)
        return {
            "url": f"/api/media/dish?{q}",
            "source": "local",
            "remote_url": None,
        }

    # 4) Placeholder — never invent a wrong photo
    log.info("dish image source=placeholder title=%r", title)
    return {"url": None, "source": "placeholder", "remote_url": None}
