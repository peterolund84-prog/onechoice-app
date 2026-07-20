# -*- coding: utf-8 -*-
"""
Compatibility shim — app/feasibility must not crash when Cloud hot-reloads
a new app.py before shopping.py (missing build_meal_bundle / shopping_from_recipe).
"""

from __future__ import annotations

from typing import Any


def resolve_meal_bundle(
    suggestion: str,
    *,
    meta: dict[str, Any] | None = None,
    meal_type: str = "middag",
    store: str = "ICA",
    language: str = "sv",
    grok_api_key: str = "",
    include_shopping: bool = True,
    active_minutes: int | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    import shopping as shop

    bundle = getattr(shop, "build_meal_bundle", None)
    if callable(bundle):
        return bundle(
            suggestion,
            meta=meta,
            meal_type=meal_type,
            store=store,
            language=language,
            grok_api_key=grok_api_key,
            include_shopping=include_shopping,
            active_minutes=active_minutes,
        )

    meta = dict(meta or {})
    meta.setdefault("meal_type", meal_type)
    shop_payload = shop.build_shopping(suggestion, meta=meta, store=store)
    if shop_payload:
        return shop_payload.get("recipe"), shop_payload if include_shopping else None

    recipe = shop.build_recipe(
        suggestion,
        meta.get("ingredients"),
        meal_type=meal_type,
        active_minutes=active_minutes,
        language=language,
        grok_api_key=grok_api_key,
    )
    if not include_shopping:
        return recipe, None
    shop_payload = shop.build_shopping(
        suggestion, meta={**meta, "recipe": recipe}, store=store
    )
    return recipe, shop_payload


def shopping_from_recipe(
    recipe: dict[str, Any],
    *,
    suggestion: str = "",
    store: str = "ICA",
) -> dict[str, Any] | None:
    import shopping as shop

    fn = getattr(shop, "shopping_from_recipe", None)
    if callable(fn):
        return fn(recipe, suggestion=suggestion, store=store)

    title = suggestion or str(recipe.get("title") or "")
    names_fn = getattr(shop, "_names_from_recipe", None)
    if callable(names_fn):
        ings = names_fn(recipe)
    else:
        strip = getattr(shop, "_strip_hint", lambda x: str(x))
        ings = [
            strip(str(x))
            for x in (recipe.get("ingredient_lines") or recipe.get("ingredients") or [])
            if str(x).strip()
        ]

    legacy = getattr(shop, "_build_shopping_from_names", None)
    if callable(legacy):
        meal_type = str(recipe.get("meal_type") or "middag")
        return legacy(title, ings, store=store, meal_type=meal_type)

    return shop.build_shopping(title, meta={"recipe": recipe, "ingredients": ings}, store=store)
