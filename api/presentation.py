# -*- coding: utf-8 -*-
"""Presentation helpers for HTML result/execute cards (images, ratings, nutrition)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def dish_image_url(title: str, category_hint: str | None = None) -> str | None:
    """Public URL for a local dish JPEG, or None."""
    import dish_images as dimg

    path = dimg.resolve_dish_image(title, category_hint)
    if not path:
        return None
    name = Path(path).name
    if not name or ".." in name or "/" in name or "\\" in name:
        return None
    return f"/assets/dishes/{name}"


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


def enrich_decision(decision: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach presentation fields used by the HTML UI."""
    if not isinstance(decision, dict):
        return decision
    out = dict(decision)
    ctx = out.get("context") if isinstance(out.get("context"), dict) else {}
    domain = str(out.get("domain") or "")
    suggestion = str(out.get("suggestion") or "")
    presentation: dict[str, Any] = {
        "domain": domain,
        "dish_image_url": None,
        "food_meta": "",
        "movie_poster_url": ctx.get("movie_poster_url"),
        "movie_year": ctx.get("movie_tmdb_year"),
        "movie_rating": movie_rating_line(ctx),
        "nutrition": None,
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
