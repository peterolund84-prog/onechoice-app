# -*- coding: utf-8 -*-
"""Presentation helpers for HTML result/execute cards (images, ratings, nutrition)."""

from __future__ import annotations

from typing import Any


def dish_image_url(
    title: str,
    category_hint: str | None = None,
    *,
    recipe: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    api_key: str = "",
) -> str | None:
    """Public dish image URL: AI (validated) → local keyword → None (placeholder).

    Prefer URLs already resolved on the recipe/context so decide-time AI search
    is not repeated on every enrich. Never invent a mismatched photo.
    Never raises — image failure must not kill the decision card.
    """
    try:
        import food_image_search as fis

        ctx = context if isinstance(context, dict) else {}
        rec = recipe if isinstance(recipe, dict) else {}
        for key in ("image_display_url", "dish_image_url"):
            existing = rec.get(key) or ctx.get(key)
            if isinstance(existing, str) and existing.startswith("/api/media/"):
                return existing

        raw = rec.get("image_url") or ctx.get("image_url") or ctx.get("dish_image_remote_url")
        resolved = fis.resolve_food_image(
            title,
            category_hint,
            api_key=api_key,
            recipe_image_url=str(raw).strip()
            if isinstance(raw, str) and raw.strip()
            else None,
            prefer_ai=bool((api_key or "").strip()),
        )
        return resolved.get("url") if isinstance(resolved, dict) else None
    except Exception:
        return None

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


def _resolve_movie_poster(ctx: dict[str, Any], suggestion: str) -> str | None:
    """TMDB (if keyed) → TVMaze/iTunes fallback → proxied same-origin URL."""
    from api.movie_posters import resolve_poster_url

    kind = str(ctx.get("kind") or "").strip().lower()
    if kind not in ("series", "film"):
        fmt = str(ctx.get("format") or "")
        try:
            import movie_domain as md

            kind = md.format_kind(fmt) if fmt else "series"
        except Exception:
            kind = "series"
    # Prefer catalog meta title for search (handles Swedish labels).
    meta_title = str(ctx.get("series_title") or "").strip()
    query = suggestion or meta_title
    return resolve_poster_url(
        query,
        kind=kind,
        existing=None,  # never reuse stale poster across titles
    )


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
    if domain == "movie" and suggestion:
        from api.movie_posters import display_title as _movie_display

        pretty = _movie_display(suggestion)
        if pretty and pretty != suggestion:
            suggestion = pretty
            out["suggestion"] = pretty
    poster = None
    if domain == "movie":
        poster = _resolve_movie_poster(ctx, suggestion)
        if poster:
            ctx = dict(ctx)
            ctx["movie_poster_url"] = poster
            out["context"] = ctx
    presentation: dict[str, Any] = {
        "domain": domain,
        "dish_image_url": None,
        "food_meta": "",
        "movie_poster_url": poster,
        "movie_year": ctx.get("movie_tmdb_year"),
        "movie_rating": movie_rating_line(ctx),
        "nutrition": None,
        # Cost is execute/recipe-only — never attach to decision-card presentation.
        "cost": None,
        "is_favorite": bool(out.get("favorite")),
        "share_text": share_text_for(out, language=language),
        "decision_id": out.get("decision_id") or out.get("id"),
        "execution_url": out.get("execution_url") or ctx.get("execution_url"),
        "execution_label": out.get("execution_label") or ctx.get("execution_label"),
        "execution_type": out.get("execution_type") or ctx.get("execution_type"),
    }
    if domain == "food":
        hint = ctx.get("dish_category") or ctx.get("category")
        shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else {}
        recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
        if not recipe and shop:
            recipe = shop.get("recipe") if isinstance(shop.get("recipe"), dict) else None
        try:
            presentation["dish_image_url"] = dish_image_url(
                suggestion,
                str(hint) if hint else None,
                recipe=recipe if isinstance(recipe, dict) else None,
                context=ctx,
            )
            presentation["dish_image_source"] = (
                (recipe.get("image_source") if isinstance(recipe, dict) else None)
                or ctx.get("dish_image_source")
            )
            presentation["image_pending"] = bool(
                (recipe.get("image_pending") if isinstance(recipe, dict) else False)
                or ctx.get("image_pending")
            )
        except Exception:
            presentation["dish_image_url"] = None
            presentation["dish_image_source"] = "placeholder"
            presentation["image_pending"] = False
        try:
            presentation["food_meta"] = food_meta_line(ctx)
        except Exception:
            presentation["food_meta"] = ""
        # Nutrition may hydrate recipe payloads for execute; result.html must not render it.
        try:
            presentation["nutrition"] = nutrition_stats(recipe, suggestion=suggestion)
        except Exception:
            presentation["nutrition"] = None
    out["presentation"] = presentation
    return out
