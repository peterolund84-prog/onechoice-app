# -*- coding: utf-8 -*-
"""
Universal feasibility layer for OneChoice.

Core rule: never show a broken decision. Candidates that fail domain validators
are discarded before ranking. No substitution notes, no problems pushed to user.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import mocks
import shopping

# Ingredients that fail the Swedish basic-assortment check (specialty / import)
EXOTIC_INGREDIENTS = (
    "teff",
    "lemongrass",
    "citronella",
    "galangal",
    "yuzu",
    "matcha powder",  # specialty cafe — leave matcha latte alone; powder is ok-ish but keep
    "fresh lemongrass",
    "gochujang",
    "miso paste",  # increasingly common — keep as soft fail only via exact exotic list
    "sumac",
    "za'atar",
    "zaatar",
    "black garlic",
    "truffle oil",
    "edible flowers",
    "fresh turmeric root",
    "palm sugar",
    "pandan",
)

# Soft-ok specialty that still fails if explicitly required as "fresh import"
HARD_EXOTIC = (
    "teff",
    "fresh lemongrass",
    "lemongrass",
    "galangal",
    "yuzu",
    "pandan",
    "edible flowers",
    "black garlic",
)

MEN_ONLY_ITEMS = ("herrskjorta", "herrbyxor", "dressmann", "men's", "mens ")
WOMEN_ONLY_ITEMS = ("klänning", "klanning", "kjol", "blouse", "dress", " Dam", "dam-")
DRESS_WORDS = ("klänning", "klanning", "kjol")
MENS_CUT_WORDS = ("herrkostym", "herrskjorta", "men's suit")

OUTDOOR_WORDS = ("löprunda ute", "ute och spring", "ute-löp", "friluft", "ute i skogen", "outdoor run")
GYM_WORDS = ("gymmet", "gå till gym", "maskinpark", "smith-maskin", "cable fly")
COLD_WORDS = ("linne", "linnebyxor", "sommarklänning", "shorts", "sandaler")
HOT_WORDS = ("ulltröja", "dunjacka", "vinterjacka", "fleece", "pjäxor")


@dataclass
class FeasibilityResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)
    execution: dict[str, Any] | None = None
    enriched: dict[str, Any] | None = None  # patched suggestion / shopping list etc.


def parse_profile(user: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize user row + context into a domain profile dict."""
    ctx = dict(context or {})
    raw = user.get("profile_json") or "{}"
    if isinstance(raw, str):
        try:
            profile = json.loads(raw)
        except json.JSONDecodeError:
            profile = {}
    else:
        profile = dict(raw or {})

    dietary = user.get("dietary_json") or "[]"
    if isinstance(dietary, str):
        try:
            dietary = json.loads(dietary)
        except json.JSONDecodeError:
            dietary = []

    wardrobe = user.get("wardrobe_json") or "[]"
    if isinstance(wardrobe, str):
        try:
            wardrobe = json.loads(wardrobe)
        except json.JSONDecodeError:
            wardrobe = []

    food = dict(profile.get("food") or {})
    clothes = dict(profile.get("clothes") or {})
    movie = dict(profile.get("movie") or {})
    workout = dict(profile.get("workout") or {})
    weekend = dict(profile.get("weekend") or {})

    # Defaults — executable V1 assumptions
    food.setdefault("store", ctx.get("store") or "ICA")
    food.setdefault("household_size", int(ctx.get("household_size") or 1))
    food.setdefault("allergies", list(dietary) if isinstance(dietary, list) else [])
    food.setdefault("diet", ctx.get("diet") or "omnivore")

    clothes.setdefault("section", ctx.get("clothing_section") or "båda")  # herr|dam|båda
    clothes.setdefault("sizes", ctx.get("sizes") or {"top": "M", "bottom": "32", "shoes": "42"})
    clothes.setdefault("styles", ctx.get("styles") or ["casual"])
    clothes.setdefault("wardrobe", wardrobe if isinstance(wardrobe, list) else [])
    try:
        import clothes_domain as cd

        clothes = cd.ensure_clothes_profile({"clothes": clothes}).get("clothes") or clothes
    except Exception:
        pass
    if ctx.get("clothing_section"):
        clothes["section"] = ctx["clothing_section"]
    if ctx.get("sizes") and isinstance(ctx.get("sizes"), dict):
        clothes["sizes"] = {**(clothes.get("sizes") or {}), **ctx["sizes"]}

    movie.setdefault(
        "services",
        ctx.get("streaming_services")
        or ["netflix", "svt_play"],
    )
    movie.setdefault("allow_rentals", bool(ctx.get("allow_rentals", False)))
    movie.setdefault("available_minutes", ctx.get("available_minutes") or 90)

    workout.setdefault("context", ctx.get("workout_context") or "home")  # gym|home|outdoors
    workout.setdefault("equipment", ctx.get("equipment") or ["none"])
    workout.setdefault("level", ctx.get("fitness_level") or "beginner")
    workout.setdefault("limitations", ctx.get("limitations") or "")
    workout.setdefault("default_minutes", int(ctx.get("workout_minutes") or 30))

    weekend.setdefault("household", ctx.get("household") or "solo")  # solo|partner|kids
    weekend.setdefault("kids_ages", ctx.get("kids_ages") or [])
    weekend.setdefault("has_car", bool(ctx.get("has_car", False)))
    weekend.setdefault("budget", user.get("budget") or ctx.get("budget") or "billigt")

    return {
        "language": user.get("language") or ctx.get("language") or "sv",
        "location": user.get("location") or ctx.get("location") or "Sverige",
        "budget": user.get("budget") or ctx.get("budget") or "medium",
        "food": food,
        "clothes": clothes,
        "movie": movie,
        "workout": workout,
        "weekend": weekend,
        "weather": ctx.get("weather") or "unknown",
        "temp_c": ctx.get("temp_c"),
        "hour": ctx.get("hour", datetime.now().hour),
        "weekday": ctx.get("weekday"),
        "time_of_day": ctx.get("time_of_day"),
        "is_weekend": ctx.get("is_weekend", False),
        "intent": ctx.get("intent"),  # e.g. wear vs buy for clothes
    }


def feasibility_check(
    candidate: dict[str, Any],
    *,
    domain: str,
    profile: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> FeasibilityResult:
    validators = {
        "food": _check_food,
        "clothes": _check_clothes,
        "movie": _check_movie,
        "workout": _check_workout,
        "weekend": _check_weekend,
    }
    fn = validators.get(domain)
    if not fn:
        return FeasibilityResult(ok=True)
    return fn(candidate, profile, context or {})


def filter_feasible(
    candidates: list[dict[str, Any]],
    *,
    domain: str,
    profile: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Keep only candidates that pass; attach execution + flags from validator."""
    survivors: list[dict[str, Any]] = []
    for c in candidates:
        result = feasibility_check(c, domain=domain, profile=profile, context=context)
        if not result.ok:
            continue
        enriched = dict(c)
        if result.enriched:
            enriched.update(result.enriched)
        if result.execution:
            enriched["execution"] = result.execution
        survivors.append(enriched)
    return survivors


# ---------------------------------------------------------------------------
# FOOD
# ---------------------------------------------------------------------------
def _check_food(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    context: dict[str, Any],
) -> FeasibilityResult:
    suggestion = str(candidate.get("suggestion") or "")
    text = f"{suggestion} {candidate.get('justification', '')} {json.dumps(candidate.get('meta') or {}, ensure_ascii=False)}".lower()
    reasons: list[str] = []

    for exotic in HARD_EXOTIC:
        if exotic in text:
            reasons.append(f"exotic_ingredient:{exotic}")

    allergies = [str(a).lower() for a in (profile.get("food") or {}).get("allergies") or []]
    for a in allergies:
        if a and a in text:
            reasons.append(f"allergy:{a}")

    diet = ((profile.get("food") or {}).get("diet") or "").lower()
    meat_words = ("lax", "kött", "kyckling", "bacon", "burgare", "köttfärs", "fläsk", "fisk", "räkor", "ost")
    if diet == "vegan" and any(w in text for w in meat_words + ("mjölk", "ägg", "grädde", "smör")):
        reasons.append("diet:vegan")
    elif diet == "vegetarian" and any(
        w in text for w in ("lax", "kött", "kyckling", "bacon", "burgare", "köttfärs", "fläsk", "fisk", "räkor")
    ):
        reasons.append("diet:vegetarian")

    # Eating out requires open + map — V1: assume open if location known and not flagged closed
    eating_out = bool((candidate.get("meta") or {}).get("eating_out")) or any(
        w in suggestion.lower() for w in ("restaurang", "beställ", "takeaway", "hämtmat")
    )
    store = (profile.get("food") or {}).get("store") or "ICA"
    is_weekend = bool(profile.get("is_weekend") or context.get("is_weekend"))
    max_min = 60 if is_weekend else 30
    active = (candidate.get("meta") or {}).get("active_minutes")
    if active is not None and int(active) > max_min:
        reasons.append("too_long")

    if reasons:
        return FeasibilityResult(ok=False, reasons=reasons)

    if eating_out:
        loc = profile.get("location") or "Sverige"
        execution = {
            "type": "map",
            "label": "Öppna karta",
            "url": f"https://www.google.com/maps/search/{suggestion}+nära+{loc}",
            "detail": f"Öppet nu · inom rimligt avstånd från {loc}",
        }
        return FeasibilityResult(ok=True, execution=execution)

    # Full list → split to_buy / assumed_at_home (hard completeness rule)
    shop = shopping.build_shopping(
        suggestion,
        meta=candidate.get("meta") or {},
        store=store,
    )
    if not shop or not shopping.shopping_valid(shop, suggestion):
        return FeasibilityResult(ok=False, reasons=["shopping_incomplete"])

    execution = {
        "type": "recipe",
        "label": "Handla & laga",
        "url": None,
        "detail": shopping.format_assumed_line(shop["assumed_at_home"]),
        "shopping": shop,
        "shopping_list": shop["to_buy"],  # legacy key for older UI/tests
        "recipe": shop.get("recipe")
        or shopping.build_recipe(suggestion, shop.get("ingredients")),
        "store": store,
        "max_active_minutes": max_min,
    }
    return FeasibilityResult(
        ok=True,
        execution=execution,
        enriched={
            "wildcard": bool(candidate.get("wildcard")),
            "meta": {
                **(candidate.get("meta") or {}),
                "ingredients": shop["ingredients"],
                "shopping": shop,
            },
        },
    )


def _default_shopping_list(suggestion: str) -> dict[str, list[str]]:
    """Deprecated shim — use shopping.build_shopping."""
    payload = shopping.build_shopping(suggestion)
    return (payload or {}).get("to_buy") or {}


def _format_shopping(shop_or_legacy: dict[str, Any] | None, store: str) -> str:
    if not shop_or_legacy:
        return f"Handla på {store}."
    if "to_buy" in shop_or_legacy:
        parts = [f"Inköpslista ({shop_or_legacy.get('store') or store}):"]
        for section, items in (shop_or_legacy.get("to_buy") or {}).items():
            if items:
                parts.append(f"{section}: {', '.join(items)}")
        assumed = shop_or_legacy.get("assumed_at_home") or []
        parts.append(shopping.format_assumed_line(list(assumed)))
        return " · ".join(parts)
    parts = [f"Inköpslista ({store}):"]
    for section, items in shop_or_legacy.items():
        if items:
            parts.append(f"{section}: {', '.join(items)}")
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# CLOTHES
# ---------------------------------------------------------------------------
def _check_clothes(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    context: dict[str, Any],
) -> FeasibilityResult:
    suggestion = str(candidate.get("suggestion") or "")
    low = suggestion.lower()
    clothes = profile.get("clothes") or {}
    section = (clothes.get("section") or "båda").lower()
    wardrobe = clothes.get("wardrobe") or []
    sizes = clothes.get("sizes") or {}
    intent = (profile.get("intent") or context.get("intent") or candidate.get("intent") or "").lower()
    if not intent:
        intent = "buy" if any(w in low for w in ("köp", "beställ", "handla")) else "wear"

    # Section hard constraints
    if section in ("herr", "men", "male"):
        if any(w in low for w in DRESS_WORDS):
            return FeasibilityResult(ok=False, reasons=["section:dress_for_mens"])
    if section in ("dam", "women", "female"):
        if any(w in low for w in MENS_CUT_WORDS):
            return FeasibilityResult(ok=False, reasons=["section:mens_cut_for_womens"])

    temp = profile.get("temp_c")
    season = _season_from_temp(temp, profile.get("weather"))
    if season == "cold" and any(w in low for w in COLD_WORDS):
        return FeasibilityResult(ok=False, reasons=["weather:too_cold_for_item"])
    if season == "warm" and any(w in low for w in HOT_WORDS):
        return FeasibilityResult(ok=False, reasons=["weather:too_warm_for_item"])

    if intent == "wear":
        if wardrobe:
            # Must draw only from registered wardrobe tokens
            tokens = [str(w).lower() for w in wardrobe]
            parts = re.split(r"\s*\+\s*|\s*,\s*", suggestion)
            for part in parts:
                p = part.strip().lower()
                if not p:
                    continue
                if not any(t in p or p in t for t in tokens):
                    return FeasibilityResult(ok=False, reasons=[f"wardrobe_missing:{p}"])
            execution = {
                "type": "wardrobe",
                "label": "Ta på dig nu",
                "url": None,
                "detail": suggestion,
            }
        else:
            # Category-only suggestion OK before wardrobe exists
            execution = {
                "type": "wardrobe",
                "label": "Bygg outfiten",
                "url": None,
                "detail": suggestion,
            }
        return FeasibilityResult(ok=True, execution=execution)

    # Buy intent — require mock stock
    size = sizes.get("top") or sizes.get("bottom") or list(sizes.values())[0] if sizes else "M"
    # Try each product-ish token
    parts = [p.strip() for p in re.split(r"\s*\+\s*|\s*,\s*", suggestion) if p.strip()]
    links = []
    for part in parts:
        stock = mocks.clothing_in_stock(part, size=str(size), section=_norm_section(section), season=season)
        if not stock:
            # category-only buy suggestions without catalog match fail closed for buy
            # but allow generic outfit language if not explicitly a product buy list
            continue
        links.append(stock)
    if not links and any(k in low for k in mocks.CLOTHING_CATALOG):
        return FeasibilityResult(ok=False, reasons=["out_of_stock"])
    if links:
        first = links[0]
        execution = {
            "type": "shop",
            "label": f"Köp hos {first['retailer']}",
            "url": first.get("url"),
            "detail": f"I lager · storlek {size} · {first['retailer']}",
            "stock": links,
        }
        return FeasibilityResult(ok=True, execution=execution)

    # Soft pass: category shopping tip without hard SKU (V1)
    execution = {
        "type": "shop",
        "label": "Hitta plagg",
        "url": f"https://www.zalando.se/catalog/?q={suggestion}",
        "detail": "Svenska kedjor · kontrollera storlek i kassan (V1-mock)",
    }
    return FeasibilityResult(ok=True, execution=execution)


def _norm_section(section: str) -> str:
    s = section.lower()
    if s in ("herr", "men", "male", "man"):
        return "herr"
    if s in ("dam", "women", "female", "kvinna"):
        return "dam"
    return "båda"


def _season_from_temp(temp_c: Any, weather: Any) -> str | None:
    try:
        t = float(temp_c) if temp_c is not None else None
    except (TypeError, ValueError):
        t = None
    if t is not None:
        if t <= 5:
            return "cold"
        if t >= 22:
            return "warm"
        return "all"
    w = str(weather or "").lower()
    if any(x in w for x in ("snow", "snö", "frost", "vinter", "cold")):
        return "cold"
    if any(x in w for x in ("heat", "heta", "sommar", "hot")):
        return "warm"
    return None


# ---------------------------------------------------------------------------
# MOVIE
# ---------------------------------------------------------------------------
def _check_movie(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    context: dict[str, Any],
) -> FeasibilityResult:
    suggestion = str(candidate.get("suggestion") or "")
    movie = profile.get("movie") or {}
    services = [mocks.normalize_service(s) for s in (movie.get("services") or [])]
    minutes = int(movie.get("available_minutes") or context.get("available_minutes") or 90)
    allow_rent = bool(movie.get("allow_rentals"))

    meta_title = (candidate.get("meta") or {}).get("title") or suggestion
    # Strip Swedish wrappers: "Titta på X", "Ett avsnitt av X"
    title = meta_title
    for prefix in ("titta på ", "watch ", "ett avsnitt av ", "filmen ", "serien "):
        if title.lower().startswith(prefix):
            title = title[len(prefix) :]
            break
    title = title.strip(" .")

    match = mocks.streaming_availability(
        title,
        user_services=services,
        max_minutes=minutes,
        allow_rentals=allow_rent,
    )
    if match:
        return FeasibilityResult(
            ok=True,
            execution={
                "type": "stream",
                "label": f"Öppna på {_service_label(match['service'])}",
                "url": match.get("url"),
                "detail": f"{match['runtime_min']} min · {_service_label(match['service'])}",
            },
            enriched={"meta": {**(candidate.get("meta") or {}), **match}},
        )

    # Generic suggestions without a catalog title: only OK if they don't name a paywalled title
    low = suggestion.lower()
    if any(x in low for x in ("hyr för", "rent for", "49 kr", "pay-per-view")) and not allow_rent:
        return FeasibilityResult(ok=False, reasons=["rental_not_allowed"])

    # If suggestion names a known title not on services → fail
    for known in mocks.STREAMING_CATALOG:
        if known in low:
            return FeasibilityResult(ok=False, reasons=[f"unavailable:{known}"])

    # Vague "watch a thriller" — pass with search on first service
    svc = services[0] if services else "netflix"
    return FeasibilityResult(
        ok=True,
        execution={
            "type": "stream",
            "label": f"Öppna {_service_label(svc)}",
            "url": _service_home(svc),
            "detail": f"Inom ~{minutes} min på dina tjänster",
        },
    )


def _service_label(svc: str) -> str:
    return {
        "netflix": "Netflix",
        "viaplay": "Viaplay",
        "hbo_max": "HBO Max",
        "disney_plus": "Disney+",
        "svt_play": "SVT Play",
        "prime": "Prime Video",
        "tv4_play": "TV4 Play",
    }.get(svc, svc)


def _service_home(svc: str) -> str:
    return {
        "netflix": "https://www.netflix.com/",
        "viaplay": "https://viaplay.se/",
        "hbo_max": "https://www.max.com/",
        "disney_plus": "https://www.disneyplus.com/",
        "svt_play": "https://www.svtplay.se/",
        "prime": "https://www.primevideo.com/",
        "tv4_play": "https://www.tv4play.se/",
    }.get(svc, "https://www.justwatch.com/se")


# ---------------------------------------------------------------------------
# WORKOUT
# ---------------------------------------------------------------------------
def _check_workout(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    context: dict[str, Any],
) -> FeasibilityResult:
    suggestion = str(candidate.get("suggestion") or "")
    low = suggestion.lower()
    wo = profile.get("workout") or {}
    ctx_mode = (wo.get("context") or "home").lower()
    equipment = [str(e).lower() for e in (wo.get("equipment") or ["none"])]
    limitations = str(wo.get("limitations") or "").lower()
    minutes = int(wo.get("default_minutes") or 30)
    meta_min = (candidate.get("meta") or {}).get("minutes")
    if meta_min is not None and int(meta_min) > minutes + 5:
        return FeasibilityResult(ok=False, reasons=["too_long"])

    if ctx_mode in ("home", "home_only") and any(w in low for w in GYM_WORDS):
        return FeasibilityResult(ok=False, reasons=["requires_gym"])

    if "none" in equipment or equipment == ["none"]:
        if any(w in low for w in ("hantel", "dumbbell", "skivstång", "kettlebell", "maskin")):
            return FeasibilityResult(ok=False, reasons=["missing_equipment"])

    # Outdoor + weather/darkness
    is_outdoor = any(w in low for w in OUTDOOR_WORDS) or "ute" in low and "promenad" in low
    if is_outdoor or ctx_mode == "outdoors":
        temp = profile.get("temp_c")
        hour = int(profile.get("hour") or 12)
        try:
            t = float(temp) if temp is not None else None
        except (TypeError, ValueError):
            t = None
        if t is not None and t <= -15:
            return FeasibilityResult(ok=False, reasons=["extreme_cold"])
        if hour < 7 or hour >= 20:
            # dark in winter latitudes — block outdoor run suggestions
            if "löp" in low or "spring" in low or "run" in low:
                return FeasibilityResult(ok=False, reasons=["dark_outdoor"])

    if limitations:
        # Absolute respect: knee → no jump/lunge heavy; back → no deadlift
        if "knä" in limitations or "knee" in limitations:
            if any(w in low for w in ("hopp", "jump", "utfall", "lunge", "burpee")):
                return FeasibilityResult(ok=False, reasons=["limitation:knee"])
        if "rygg" in limitations or "back" in limitations:
            if any(w in low for w in ("marklyft", "deadlift", "böj med stång")):
                return FeasibilityResult(ok=False, reasons=["limitation:back"])

    plan = (candidate.get("meta") or {}).get("plan") or _default_workout_plan(suggestion, minutes)
    execution = {
        "type": "workout",
        "label": "Starta passet",
        "url": None,
        "detail": plan,
    }
    return FeasibilityResult(ok=True, execution=execution, enriched={"meta": {**(candidate.get("meta") or {}), "plan": plan}})


def _default_workout_plan(suggestion: str, minutes: int) -> str:
    s = suggestion.lower()
    if "yoga" in s:
        return (
            f"Yogaflöde ~{minutes} min: 5 min andning → solhälsningar ×5 → "
            "krigarposition 3×30s/sida → hund och katt 2 min → avsluta i barnets pose."
        )
    if "hiit" in s or "tabata" in s:
        return (
            f"HIIT {min(minutes, 20)} min: 40s arbete / 20s vila × 8 — "
            "knäböj, armhävningar, mountain climbers, jumping jacks. Upprepa."
        )
    if "promenad" in s or "zon-2" in s or "zon 2" in s:
        return f"Zon-2-promenad {minutes} min: jämn takt där du kan prata. Ingen paus behövs."
    if "armhäv" in s or "knäböj" in s:
        return (
            "Stege: armhävningar 5-10-15, knäböj 10-15-20, vila 60s mellan. "
            "2 varv. Klart."
        )
    return (
        f"Helkropp ~{minutes} min: knäböj 3×12, armhävningar 3×8, planka 3×30s, "
        "utfall 3×10/ben (eller step-back om knän känsliga). Vila 45s."
    )


# ---------------------------------------------------------------------------
# WEEKEND
# ---------------------------------------------------------------------------
def _check_weekend(
    candidate: dict[str, Any],
    profile: dict[str, Any],
    context: dict[str, Any],
) -> FeasibilityResult:
    suggestion = str(candidate.get("suggestion") or "")
    low = suggestion.lower()
    we = profile.get("weekend") or {}
    has_car = bool(we.get("has_car"))
    budget = str(we.get("budget") or profile.get("budget") or "billigt").lower()
    household = str(we.get("household") or "solo").lower()
    kids_ages = we.get("kids_ages") or []
    month = datetime.now().month

    # No car → block long drives / far destinations
    if not has_car and any(w in low for w in ("bilresa", "kör till", "2 timmar bort", "flyg", "roadtrip")):
        return FeasibilityResult(ok=False, reasons=["needs_car"])

    # Season / opening hours heuristics
    if month in (10, 11, 12, 1, 2, 3) and any(w in low for w in ("utebad", "utesim", "badstrand", "utomhusbad")):
        return FeasibilityResult(ok=False, reasons=["season_closed"])
    if "museum" in low or "museum" in suggestion.lower():
        # Assume museums closed Mondays in V1 if weekday is Monday
        if str(profile.get("weekday") or "").lower().startswith("mon"):
            return FeasibilityResult(ok=False, reasons=["museum_closed_monday"])

    if household in ("kids", "family") or kids_ages:
        if any(w in low for w in ("bar", "nattklubb", "vinprovning", "after work")):
            return FeasibilityResult(ok=False, reasons=["not_age_appropriate"])

    if budget in ("gratis", "free", "0"):
        if any(w in low for w in ("spa", "konsert", "biljett", "restaurangmiddag", "högpris")):
            return FeasibilityResult(ok=False, reasons=["over_budget"])

    loc = profile.get("location") or "din ort"
    detail = (candidate.get("meta") or {}).get("execution_detail")
    if not detail:
        if any(w in low for w in ("park", "picknick", "promenad", "skog")):
            detail = "Ta med: vatten, sittunderlag, jacka efter väder."
        else:
            detail = f"Kolla öppettider · karta nära {loc}"

    execution = {
        "type": "activity",
        "label": "Öppna karta",
        "url": f"https://www.google.com/maps/search/{suggestion}+{loc}",
        "detail": detail,
    }
    return FeasibilityResult(ok=True, execution=execution)
