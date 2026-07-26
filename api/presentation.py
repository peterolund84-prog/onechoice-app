# -*- coding: utf-8 -*-
"""Presentation helpers for HTML result/execute cards (images, ratings, nutrition)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def dish_image_url(title: str, category_hint: str | None = None) -> str | None:
    """Public URL for a local dish JPEG via API (uvicorn-safe), or None."""
    from urllib.parse import urlencode

    import dish_images as dimg

    path = dimg.resolve_dish_image(title, category_hint)
    if not path:
        return None
    name = Path(path).name
    if not name or ".." in name or "/" in name or "\\" in name:
        return None
    q = urlencode({"title": title or "", "category": category_hint or ""})
    return f"/api/media/dish?{q}"


def _shop_item_count(shop: dict[str, Any] | None) -> int:
    if not isinstance(shop, dict):
        return 0
    to_buy = shop.get("to_buy") or {}
    if not isinstance(to_buy, dict):
        return 0
    n = 0
    for items in to_buy.values():
        if isinstance(items, list):
            n += len(items)
    return n


def food_meta_line(ctx: dict[str, Any] | None) -> str:
    """Muted meta: ⏱ min · portioner · N varor."""
    ctx = ctx if isinstance(ctx, dict) else {}
    shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else {}
    recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
    if not recipe and shop:
        recipe = shop.get("recipe") if isinstance(shop.get("recipe"), dict) else None

    bits: list[str] = []
    mins = None
    if isinstance(recipe, dict):
        mins = recipe.get("active_minutes") or recipe.get("total_minutes")
    if mins is None:
        mins = ctx.get("active_minutes")
    if mins is not None:
        try:
            bits.append(f"⏱ {int(mins)} min")
        except (TypeError, ValueError):
            pass

    portions = 1
    if isinstance(recipe, dict):
        portions = recipe.get("portioner") or recipe.get("portions") or 1
    try:
        n = int(portions)
    except (TypeError, ValueError):
        n = 1
    bits.append("1 portion" if n <= 1 else f"{n} portioner")

    n_buy = _shop_item_count(shop if isinstance(shop, dict) else None)
    if n_buy > 0:
        bits.append(f"{n_buy} varor att köpa")
    return " · ".join(bits)


def movie_vote_line(vote_average: Any) -> str | None:
    if vote_average is None:
        return None
    try:
        v = float(vote_average)
    except (TypeError, ValueError):
        return None
    return f"★ {v:.1f}".replace(".", ",")


def movie_rating_line(ctx: dict[str, Any] | None) -> str | None:
    ctx = ctx if isinstance(ctx, dict) else {}
    star = movie_vote_line(ctx.get("movie_tmdb_vote_average"))
    if not star:
        return None
    parts = [star]
    runtime = ctx.get("movie_runtime_min")
    if runtime is not None:
        try:
            parts.append(f"{int(runtime)} min")
        except (TypeError, ValueError):
            pass
    service = ctx.get("movie_service")
    if service:
        parts.append(str(service).replace("_", " ").title())
    return " · ".join(parts)


def nutrition_stats(recipe: dict[str, Any] | None, *, suggestion: str = "") -> dict[str, int] | None:
    """Return {kcal, protein_g, fat_g, carbs_g} per portion, or None."""
    if not isinstance(recipe, dict):
        return None
    try:
        import shopping as shopping_mod

        ensure = getattr(shopping_mod, "ensure_recipe_nutrition", None)
        if callable(ensure):
            recipe = ensure(
                recipe,
                suggestion=suggestion or str(recipe.get("title") or ""),
                allow_estimate=True,
            )
    except Exception:
        pass

    nut = recipe.get("nutrition") if isinstance(recipe.get("nutrition"), dict) else {}

    def _i(*keys: str) -> int | None:
        for k in keys:
            raw = recipe.get(k) if k in recipe else nut.get(k)
            try:
                if raw is None:
                    continue
                return int(raw)
            except (TypeError, ValueError):
                continue
        return None

    kcal = _i("kcal_per_portion", "kcal")
    protein = _i("protein_g_per_portion", "protein_g")
    fat = _i("fat_g_per_portion", "fat_g")
    carbs = _i("carbs_g_per_portion", "carbs_g")
    if kcal is None or protein is None:
        return None
    return {
        "kcal": kcal,
        "protein_g": protein,
        "fat_g": 0 if fat is None else fat,
        "carbs_g": 0 if carbs is None else carbs,
    }


def _safe_movie_poster(url: Any) -> str | None:
    """Keep real TMDB CDN URLs; drop offline placeholder paths that 404."""
    if not url:
        return None
    s = str(url).strip()
    if s.startswith("/api/media/poster"):
        return s
    if not s.startswith("http"):
        return None
    # Offline catalog used fake paths like /wednesday.jpg — not real TMDB assets.
    if "image.tmdb.org" in s:
        tail = s.rsplit("/", 1)[-1].lower()
        stem = tail.split(".", 1)[0]
        if stem.isalpha() and len(stem) < 24:
            return None
        return s
    return None


def proxied_poster_url(url: Any) -> str | None:
    """Same-origin poster URL so LAN phones always load the image."""
    from urllib.parse import urlencode

    safe = _safe_movie_poster(url)
    if not safe:
        return None
    if safe.startswith("/api/media/poster"):
        return safe
    return f"/api/media/poster?{urlencode({'url': safe})}"


def _resolve_movie_poster(ctx: dict[str, Any], suggestion: str) -> str | None:
    """Use context poster, or re-query TMDB when the key is available."""
    poster = proxied_poster_url(ctx.get("movie_poster_url"))
    if poster:
        return poster
    if not suggestion:
        return None
    try:
        import tmdb as tmdb_mod
        from api.secrets import tmdb_api_key

        if not tmdb_api_key():
            return None
        kind = str(ctx.get("kind") or "series").strip().lower()
        if kind not in ("series", "film"):
            kind = "series"
        # Bust stale offline cache entries from before the key was loaded
        try:
            tmdb_mod.lookup_title.cache_clear()
        except Exception:
            pass
        meta = tmdb_mod.lookup_title(suggestion, kind=kind)
        if isinstance(meta, dict):
            return proxied_poster_url(meta.get("poster_url"))
    except Exception:
        return None
    return None


def share_text_for(decision: dict[str, Any], *, language: str = "sv") -> str:
    import share_domain as sd

    ctx = decision.get("context") if isinstance(decision.get("context"), dict) else {}
    return sd.share_message(
        domain=str(decision.get("domain") or ""),
        suggestion=str(decision.get("suggestion") or ""),
        language=language,
        year=ctx.get("movie_tmdb_year"),
    )


def enrich_decision(
    decision: dict[str, Any] | None,
    *,
    language: str = "sv",
) -> dict[str, Any] | None:
    """Attach presentation fields used by the HTML UI."""
    if not isinstance(decision, dict):
        return decision
    out = dict(decision)
    ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
    domain = str(out.get("domain") or "")
    suggestion = str(out.get("suggestion") or "")
    poster = None
    if domain == "movie":
        poster = _resolve_movie_poster(ctx, suggestion)
        # Backfill rating/year from a live lookup when context is thin
        if suggestion and (not movie_rating_line(ctx) or not ctx.get("movie_tmdb_year")):
            try:
                import tmdb as tmdb_mod
                from api.secrets import tmdb_api_key

                if tmdb_api_key():
                    kind = str(ctx.get("kind") or "series").strip().lower()
                    if kind not in ("series", "film"):
                        kind = "series"
                    meta = tmdb_mod.lookup_title(suggestion, kind=kind) or {}
                    if isinstance(meta, dict):
                        ctx = dict(ctx)
                        if meta.get("vote_average") is not None:
                            ctx.setdefault("movie_tmdb_vote_average", meta.get("vote_average"))
                        if meta.get("year") is not None:
                            ctx.setdefault("movie_tmdb_year", meta.get("year"))
                        if meta.get("poster_url") and not poster:
                            poster = proxied_poster_url(meta.get("poster_url"))
                        out["context"] = ctx
            except Exception:
                pass
    presentation: dict[str, Any] = {
        "domain": domain,
        "dish_image_url": None,
        "food_meta": "",
        "movie_poster_url": poster,
        "movie_year": ctx.get("movie_tmdb_year"),
        "movie_rating": movie_rating_line(ctx),
        "nutrition": None,
        "is_favorite": bool(out.get("favorite")),
        "share_text": share_text_for(out, language=language),
        "decision_id": out.get("decision_id") or out.get("id"),
    }
    if domain == "food":
        hint = ctx.get("dish_category") or ctx.get("category")
        presentation["dish_image_url"] = dish_image_url(
            suggestion, str(hint) if hint else None
        )
        presentation["food_meta"] = food_meta_line(ctx)
        shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else {}
        recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
        if not recipe and shop:
            recipe = shop.get("recipe") if isinstance(shop.get("recipe"), dict) else None
        presentation["nutrition"] = nutrition_stats(recipe, suggestion=suggestion)
    out["presentation"] = presentation
    return out
