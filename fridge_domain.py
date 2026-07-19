# -*- coding: utf-8 -*-
"""
Fridge / pantry photo → ingredient inventory → cook-from-what-you-have.

Two steps (never fused):
  1) Vision invent → editable inventory
  2) Decision constrained to confirmed ingredients + assumed staples only
"""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import requests

import shopping

log = logging.getLogger("onechoice.fridge")

# Synonyms so "ägg" matches "äggula" / "äggvita" lightly via stem checks
_ALIASES: dict[str, tuple[str, ...]] = {
    "ägg": ("ägg", "egg", "äggula", "äggvita"),
    "mjölk": ("mjölk", "milk", "havremjölk", "mandelmjölk"),
    "ost": ("ost", "cheese", "cheddar", "parmesan", "mozzarella"),
    "paprika": ("paprika", "bell pepper"),
    "tomat": ("tomat", "tomater", "tomato", "cherry tomat"),
    "lök": ("lök", "gul lök", "rödlök", "onion"),
    "vitlök": ("vitlök", "garlic"),
    "smör": ("smör", "butter"),
    "bröd": ("bröd", "macka", "toast", "limpa", "bread", "knäckebröd", "knäcke"),
    "pasta": ("pasta", "spaghetti", "penne", "tagliatelle"),
    "ris": ("ris", "rice", "jasminris", "basmatiris"),
    "potatis": ("potatis", "potato", "potatisar"),
    "kyckling": ("kyckling", "kycklingfilé", "chicken"),
    "bacon": ("bacon", "sidfläsk"),
    "skinka": ("skinka", "ham"),
    "korv": ("korv", "falukorv", "prinskorv"),
    "färs": ("färs", "köttfärs", "nötfärs", "mixed mince"),
    "grädde": ("grädde", "vispgrädde", "matlagningsgrädde", "cream"),
    "yoghurt": ("yoghurt", "yogurt", "naturell yoghurt", "fil", "filmjölk"),
    "banan": ("banan", "banana"),
    "äpple": ("äpple", "apple"),
    "gurka": ("gurka", "cucumber"),
    "sallad": ("sallad", "salladsblad", "lettuce", "isbergssallad"),
    "morot": ("morot", "morötter", "carrot"),
    "spenat": ("spenat", "spinach"),
    "champinjon": ("champinjon", "svamp", "mushroom"),
    "tonfisk": ("tonfisk", "tuna"),
    "bönor": ("bönor", "vita bönor", "kidneybönor", "beans"),
    "linser": ("linser", "röda linser", "lentils"),
    "havregryn": ("havregryn", "oatmeal", "gröt"),
    "müsli": ("müsli", "muesli"),
    "risifrutti": ("risifrutti",),
    "majonnäs": ("majonnäs", "mayo"),
    "ketchup": ("ketchup",),
    "senap": ("senap", "mustard"),
    "soja": ("soja", "sojasås", "soy sauce"),
    "tortilla": ("tortilla", "wrap"),
    "avokado": ("avokado", "avocado"),
    "citron": ("citron", "lemon"),
    "lime": ("lime",),
    "persilja": ("persilja", "parsley"),
    "basilika": ("basilika", "basil"),
}


SOURCE = "fridge_photo"
MAX_PHOTOS = 3
# Vision-capable models only — NEVER text-only (e.g. grok-2-latest ignores images)
VISION_MODELS = ("grok-2-vision-1212", "grok-2-vision-latest", "grok-4.5")
MAX_IMAGE_EDGE = 1568  # long-edge cap before upload (phone photos are huge)
XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"
XAI_RESPONSES_URL = "https://api.x.ai/v1/responses"

# Filled by invent_from_images for debugging / tests (last attempt)
LAST_VISION_DEBUG: dict[str, Any] = {}


class FridgeVisionError(RuntimeError):
    """Vision invent failed — must surface to the user, never become []."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        raw: str | None = None,
        status: int | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.raw = raw
        self.status = status
        self.model = model


def usable_vision_key(key: str) -> bool:
    k = (key or "").strip()
    if len(k) < 8:
        return False
    low = k.lower()
    if low.startswith(("din_", "your_", "sk_test")):
        return False
    if low.endswith(("_här", "_har")) or "your_" in low or "nyckel" in low:
        return False
    if "placeholder" in low or k.startswith("YOUR_"):
        return False
    return True


def is_fridge_mode(context: dict[str, Any] | None) -> bool:
    ctx = context or {}
    return str(ctx.get("source") or "") == SOURCE


def normalize_name(name: str) -> str:
    n = (name or "").strip().lower()
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"^[\d\s.,/]+", "", n)
    return n.strip(" .,-")


def names_only(inventory: list[dict[str, Any]] | list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in inventory or []:
        if isinstance(item, dict):
            raw = item.get("name")
        else:
            raw = item
        n = normalize_name(str(raw or ""))
        if not n or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


# Staples assumed without being in the photo — stricter than shopping.ASSUMED_STAPLES
# (paprika/basilika are fresh produce in a fridge photo, not shelf spices)
FRIDGE_STAPLES = frozenset(
    {
        "salt",
        "peppar",
        "svartpeppar",
        "olja",
        "matolja",
        "rapsolja",
        "olivolja",
        "smör",
        "socker",
        "strösocker",
        "mjöl",
        "vetemjöl",
    }
)


def _is_staple(name: str) -> bool:
    n = normalize_name(name)
    if not n:
        return True
    if "färsk" in n or "fresh" in n:
        return False
    if n in FRIDGE_STAPLES:
        return True
    base = n.split("(")[0].strip()
    return base in FRIDGE_STAPLES


def _covers(need: str, available: set[str]) -> bool:
    """True if need is a staple or matched by an available ingredient."""
    need_n = normalize_name(need)
    if not need_n:
        return True
    if _is_staple(need_n):
        return True
    if need_n in available:
        return True
    for canonical, aliases in _ALIASES.items():
        cue_hit = any(a in need_n or need_n in a for a in aliases) or need_n == canonical
        if not cue_hit:
            continue
        for a in available:
            if a == canonical or any(al in a or a in al for al in aliases):
                return True
    if len(need_n) >= 4:
        for a in available:
            if need_n in a or (len(a) >= 4 and a in need_n):
                return True
    return False


def can_cook(required: list[str], available: list[str]) -> bool:
    """Every non-staple required ingredient must be covered by confirmed inventory."""
    avail = {normalize_name(x) for x in available if normalize_name(x)}
    needed = [normalize_name(x) for x in required if normalize_name(x)]
    if not needed:
        return False
    return all(_covers(n, avail) for n in needed)


def downscale_image(blob: bytes, mime: str = "image/jpeg") -> tuple[bytes, str]:
    """Resize to max MAX_IMAGE_EDGE on the long side; convert to jpeg (xAI: jpg/png)."""
    try:
        from io import BytesIO

        from PIL import Image

        im = Image.open(BytesIO(blob))
        im.load()
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        elif im.mode == "L":
            im = im.convert("RGB")
        w, h = im.size
        long_edge = max(w, h)
        if long_edge > MAX_IMAGE_EDGE:
            scale = MAX_IMAGE_EDGE / float(long_edge)
            im = im.resize(
                (max(1, int(w * scale)), max(1, int(h * scale))),
                Image.Resampling.LANCZOS,
            )
        out = BytesIO()
        im.save(out, format="JPEG", quality=85, optimize=True)
        return out.getvalue(), "image/jpeg"
    except Exception as exc:
        log.warning("fridge downscale failed (%s) — using original bytes", exc)
        if "webp" in (mime or "").lower():
            raise FridgeVisionError(
                "image_encode",
                f"Kunde inte konvertera webp-bild: {exc}",
            ) from exc
        return bytes(blob), (mime or "image/jpeg")


def invent_from_images(
    images: list[bytes],
    *,
    api_key: str = "",
    language: str = "sv",
    mime_types: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Vision call → [{name, confidence}]. Separate from decision generation.

    Raises FridgeVisionError on missing key, HTTP failure, or unparseable response.
    Never returns [] to hide a failed call.
    """
    global LAST_VISION_DEBUG
    LAST_VISION_DEBUG = {
        "models_tried": [],
        "raw_response": None,
        "http_status": None,
        "model": None,
        "image_bytes": [],
        "payload_chars": None,
        "parsed_n": None,
        "endpoint": None,
    }

    blobs = [b for b in (images or []) if isinstance(b, (bytes, bytearray)) and len(b) > 20]
    blobs = blobs[:MAX_PHOTOS]
    if not blobs:
        raise FridgeVisionError("no_image", "Ingen bild att skicka till vision-modellen.")

    key = (api_key or "").strip()
    if not usable_vision_key(key):
        log.error(
            "fridge invent ABORT — unusable GROK_API_KEY (len=%s, prefix=%r)",
            len(key),
            key[:6] if key else "",
        )
        raise FridgeVisionError(
            "missing_api_key",
            "GROK_API_KEY saknas eller är en placeholder — vision-anropet kördes aldrig.",
        )

    mimes = list(mime_types or [])
    while len(mimes) < len(blobs):
        mimes.append("image/jpeg")

    prepared: list[tuple[bytes, str]] = []
    for blob, mime in zip(blobs, mimes):
        raw_len = len(blob)
        scaled, out_mime = downscale_image(bytes(blob), str(mime or "image/jpeg"))
        prepared.append((scaled, out_mime))
        LAST_VISION_DEBUG["image_bytes"].append(
            {"raw": raw_len, "sent": len(scaled), "mime": out_mime}
        )
        log.info(
            "fridge image prepared: raw=%sB sent=%sB mime=%s",
            raw_len,
            len(scaled),
            out_mime,
        )

    lang = "Swedish" if language == "sv" else "English"
    prompt = (
        "List ONLY clearly visible food ingredients in these fridge/pantry photos. "
        f"Use everyday {lang} grocery names (e.g. ägg, mjölk, paprika — not brands). "
        "Do NOT invent items you cannot see. Do NOT include empty packaging or utensils. "
        'Return JSON only: {"ingredients":[{"name":"...","confidence":0.0-1.0}]}'
    )

    errors: list[str] = []
    for model in VISION_MODELS:
        LAST_VISION_DEBUG["models_tried"].append(model)
        try:
            raw, status, endpoint = _call_vision_model(
                model=model,
                api_key=key,
                images=prepared,
                prompt=prompt,
            )
            LAST_VISION_DEBUG["raw_response"] = raw
            LAST_VISION_DEBUG["http_status"] = status
            LAST_VISION_DEBUG["model"] = model
            LAST_VISION_DEBUG["endpoint"] = endpoint
            log.info(
                "fridge vision RAW model=%s status=%s endpoint=%s chars=%s\n%s",
                model,
                status,
                endpoint,
                len(raw or ""),
                (raw or "")[:4000],
            )
            parsed = parse_inventory_json(raw)
            LAST_VISION_DEBUG["parsed_n"] = len(parsed)
            log.info(
                "fridge vision PARSE model=%s received_chars=%s produced_n=%s names=%s",
                model,
                len(raw or ""),
                len(parsed),
                [p["name"] for p in parsed],
            )
            return parsed
        except FridgeVisionError as exc:
            log.error(
                "fridge vision FAILED model=%s code=%s status=%s: %s | raw=%s",
                model,
                exc.code,
                exc.status,
                exc,
                (exc.raw or "")[:1500],
            )
            errors.append(f"{model}:{exc.code}:{exc}")
            continue
        except Exception as exc:
            log.exception("fridge vision UNEXPECTED model=%s: %s", model, exc)
            errors.append(f"{model}:unexpected:{exc}")
            continue

    raise FridgeVisionError(
        "all_models_failed",
        "Vision-anropet misslyckades för alla modeller: " + " | ".join(errors[:3]),
        raw=str(LAST_VISION_DEBUG.get("raw_response") or "")[:2000],
        status=LAST_VISION_DEBUG.get("http_status"),  # type: ignore[arg-type]
        model=str(LAST_VISION_DEBUG.get("model") or ""),
    )


def _call_vision_model(
    *,
    model: str,
    api_key: str,
    images: list[tuple[bytes, str]],
    prompt: str,
) -> tuple[str, int, str]:
    """Try chat/completions first, then /responses. Returns (content, status, endpoint)."""
    content: list[dict[str, Any]] = []
    for blob, mime in images:
        b64 = base64.b64encode(blob).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{b64}",
                    "detail": "high",
                },
            }
        )
    content.append({"type": "text", "text": prompt})
    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You extract grocery inventories from photos. "
                    "Conservative: only clear items. JSON only."
                ),
            },
            {"role": "user", "content": content},
        ],
        "temperature": 0.1,
    }
    payload_chars = len(json.dumps(body))
    LAST_VISION_DEBUG["payload_chars"] = payload_chars
    log.info(
        "fridge vision REQUEST model=%s endpoint=chat/completions images=%s payload_chars=%s",
        model,
        len(images),
        payload_chars,
    )
    resp = requests.post(
        XAI_CHAT_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=90,
    )
    log.info(
        "fridge vision HTTP chat/completions model=%s status=%s body_prefix=%s",
        model,
        resp.status_code,
        (resp.text or "")[:500],
    )
    if resp.status_code < 400:
        payload = resp.json()
        choices = payload.get("choices") or []
        if not choices:
            raise FridgeVisionError(
                "empty_choices",
                "Tomt choices-fält från chat/completions",
                raw=resp.text,
                status=resp.status_code,
                model=model,
            )
        raw = str((choices[0].get("message") or {}).get("content") or "").strip()
        if not raw:
            raise FridgeVisionError(
                "empty_content",
                "Tomt message.content från vision-modellen",
                raw=resp.text,
                status=resp.status_code,
                model=model,
            )
        return raw, resp.status_code, "chat/completions"

    chat_err = f"{resp.status_code}:{(resp.text or '')[:400]}"
    log.error(
        "fridge chat/completions rejected model=%s %s — trying /responses",
        model,
        chat_err,
    )

    input_content: list[dict[str, Any]] = []
    for blob, mime in images:
        b64 = base64.b64encode(blob).decode("ascii")
        input_content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{b64}",
                "detail": "high",
            }
        )
    input_content.append({"type": "input_text", "text": prompt})
    body2 = {
        "model": model,
        "input": [{"role": "user", "content": input_content}],
    }
    log.info(
        "fridge vision REQUEST model=%s endpoint=responses images=%s",
        model,
        len(images),
    )
    resp2 = requests.post(
        XAI_RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body2,
        timeout=90,
    )
    log.info(
        "fridge vision HTTP responses model=%s status=%s body_prefix=%s",
        model,
        resp2.status_code,
        (resp2.text or "")[:500],
    )
    if resp2.status_code >= 400:
        raise FridgeVisionError(
            "http_error",
            f"Vision HTTP misslyckades chat={chat_err} responses={resp2.status_code}:{(resp2.text or '')[:300]}",
            raw=resp2.text,
            status=resp2.status_code,
            model=model,
        )
    payload2 = resp2.json()
    raw2 = _extract_responses_text(payload2)
    if not raw2:
        raise FridgeVisionError(
            "empty_content",
            "Tomt svar från /responses",
            raw=resp2.text,
            status=resp2.status_code,
            model=model,
        )
    return raw2, resp2.status_code, "responses"


def _extract_responses_text(payload: dict[str, Any]) -> str:
    """Pull assistant text from xAI Responses API payload shapes."""
    if not isinstance(payload, dict):
        return ""
    out = payload.get("output") or payload.get("outputs") or []
    chunks: list[str] = []
    if isinstance(out, list):
        for item in out:
            if not isinstance(item, dict):
                continue
            for part in item.get("content") or []:
                if isinstance(part, dict):
                    t = part.get("text") or part.get("output_text") or ""
                    if t:
                        chunks.append(str(t))
            if item.get("text"):
                chunks.append(str(item["text"]))
    if payload.get("output_text"):
        chunks.append(str(payload["output_text"]))
    if not chunks and isinstance(payload.get("response"), dict):
        return _extract_responses_text(payload["response"])
    return "\n".join(chunks).strip()


def parse_inventory_json(raw: str) -> list[dict[str, Any]]:
    """
    Parse model output into inventory rows.
    Raises FridgeVisionError if the model did not return usable JSON
    (silent prose→[] is forbidden).
    """
    text = (raw or "").strip()
    if not text:
        raise FridgeVisionError("parse_empty", "Vision-svar tomt — inget att parsa.")
    original = text
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        text = brace.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        log.error(
            "fridge PARSE failed — received=%r produced=ERROR (%s)",
            original[:800],
            exc,
        )
        raise FridgeVisionError(
            "parse_json",
            f"Vision-svar var inte JSON: {exc}",
            raw=original[:2000],
        ) from exc

    items = data.get("ingredients") if isinstance(data, dict) else data
    if not isinstance(items, list):
        log.error(
            "fridge PARSE failed — no ingredients list. received=%r produced={}",
            original[:800],
        )
        raise FridgeVisionError(
            "parse_shape",
            "Vision-JSON saknar ingredients-lista.",
            raw=original[:2000],
        )

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in items:
        if isinstance(row, str):
            name, conf = row, 0.7
        elif isinstance(row, dict):
            name = row.get("name") or row.get("ingredient") or ""
            try:
                conf = float(
                    row.get("confidence") if row.get("confidence") is not None else 0.7
                )
            except (TypeError, ValueError):
                conf = 0.7
        else:
            continue
        name_n = normalize_name(str(name))
        if not name_n or name_n in seen:
            continue
        seen.add(name_n)
        out.append({"name": name_n, "confidence": max(0.0, min(1.0, conf))})

    log.info(
        "fridge PARSE ok — received_chars=%s produced_n=%s names=%s",
        len(original),
        len(out),
        [x["name"] for x in out],
    )
    return out




def recipe_library(language: str = "sv") -> list[dict[str, Any]]:
    """Cook-from-inventory templates — only used when ingredients are covered."""
    sv = language == "sv"
    return [
        {
            "suggestion": "Omelett med paprika och ost" if sv else "Omelette with pepper and cheese",
            "justification": (
                "Du har ägg, paprika och ost — det blir omelett."
                if sv
                else "You have eggs, pepper and cheese — omelette it is."
            ),
            "meta": {
                "active_minutes": 12,
                "ingredients": ["ägg", "paprika", "ost", "smör", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Äggmackor" if sv else "Egg sandwiches",
            "justification": (
                "Du har ägg och bröd — klassiska äggmackor."
                if sv
                else "You have eggs and bread — egg sandwiches."
            ),
            "meta": {
                "active_minutes": 8,
                "ingredients": ["ägg", "bröd", "smör", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Stekt ägg med tomat" if sv else "Fried eggs with tomato",
            "justification": (
                "Du har ägg och tomat — klart på några minuter."
                if sv
                else "You have eggs and tomato — done in minutes."
            ),
            "meta": {
                "active_minutes": 8,
                "ingredients": ["ägg", "tomat", "smör", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Ost- och skinkmacka" if sv else "Ham and cheese sandwich",
            "justification": (
                "Du har bröd, ost och skinka — ingen matlagning."
                if sv
                else "You have bread, cheese and ham — no cooking."
            ),
            "meta": {
                "active_minutes": 3,
                "ingredients": ["bröd", "ost", "skinka", "smör"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Tomatpasta med vitlök" if sv else "Tomato pasta with garlic",
            "justification": (
                "Du har pasta och tomat — snabb vardagspasta."
                if sv
                else "You have pasta and tomato — quick weeknight pasta."
            ),
            "meta": {
                "active_minutes": 18,
                "ingredients": ["pasta", "tomat", "vitlök", "olja", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Kycklingwok på det du har" if sv else "Chicken stir-fry from what you have",
            "justification": (
                "Du har kyckling och grönt — en snabb wok."
                if sv
                else "You have chicken and veg — a quick stir-fry."
            ),
            "meta": {
                "active_minutes": 20,
                "ingredients": ["kyckling", "paprika", "lök", "olja", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Ris med ägg och grönsaker" if sv else "Rice with egg and vegetables",
            "justification": (
                "Du har ris, ägg och grönt — en enkel stekpanna."
                if sv
                else "You have rice, egg and veg — one pan."
            ),
            "meta": {
                "active_minutes": 20,
                "ingredients": ["ris", "ägg", "lök", "olja", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Yoghurtbowl med banan" if sv else "Yoghurt bowl with banana",
            "justification": (
                "Du har yoghurt och banan — ingen matlagning."
                if sv
                else "You have yoghurt and banana — no cooking."
            ),
            "meta": {
                "active_minutes": 2,
                "ingredients": ["yoghurt", "banan"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Havregrynsgröt" if sv else "Oatmeal porridge",
            "justification": (
                "Du har havregryn och mjölk — klassisk gröt."
                if sv
                else "You have oats and milk — classic porridge."
            ),
            "meta": {
                "active_minutes": 6,
                "ingredients": ["havregryn", "mjölk", "salt"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Tonfisksallad" if sv else "Tuna salad",
            "justification": (
                "Du har tonfisk och grönt — lätt och klart."
                if sv
                else "You have tuna and greens — light and done."
            ),
            "meta": {
                "active_minutes": 8,
                "ingredients": ["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Quesadilla med ost" if sv else "Cheese quesadilla",
            "justification": (
                "Du har tortilla och ost — stek ihop."
                if sv
                else "You have tortilla and cheese — pan-fry it."
            ),
            "meta": {
                "active_minutes": 8,
                "ingredients": ["tortilla", "ost", "olja"],
                "source": SOURCE,
            },
        },
        {
            "suggestion": "Stekt korv med potatis" if sv else "Fried sausage with potatoes",
            "justification": (
                "Du har korv och potatis — enkel stekpanna."
                if sv
                else "You have sausage and potatoes — one pan."
            ),
            "meta": {
                "active_minutes": 25,
                "ingredients": ["korv", "potatis", "olja", "salt", "peppar"],
                "source": SOURCE,
            },
        },
    ]


def justify_from_inventory(
    suggestion: str,
    available: list[str],
    language: str = "sv",
) -> str:
    """One-line justification that references what was seen in the photo."""
    names = names_only(available)[:5]
    if language == "sv":
        if not names:
            return f"{suggestion} — utifrån det du har hemma."
        if len(names) == 1:
            return f"Du har {names[0]} — det blir {suggestion.lower()}."
        if len(names) == 2:
            return f"Du har {names[0]} och {names[1]} — det blir {suggestion}."
        head = ", ".join(names[:-1])
        return f"Du har {head} och {names[-1]} — det blir {suggestion}."
    if not names:
        return f"{suggestion} — from what you have."
    joined = ", ".join(names[:-1]) + (f" and {names[-1]}" if len(names) > 1 else names[0])
    return f"You have {joined} — {suggestion}."


def fridge_candidates(
    available: list[str],
    *,
    language: str = "sv",
) -> list[dict[str, Any]]:
    """Candidates cookable ONLY from confirmed inventory + staples."""
    avail = names_only(available)
    out: list[dict[str, Any]] = []
    for dish in recipe_library(language):
        ings = list((dish.get("meta") or {}).get("ingredients") or [])
        if not can_cook(ings, avail):
            continue
        row = dict(dish)
        meta = dict(row.get("meta") or {})
        meta["available_ingredients"] = avail
        meta["source"] = SOURCE
        meta["assume_at_home_only"] = True
        # Prefer photo-aware justification when inventory is rich enough
        used = [i for i in ings if not _is_staple(i)]
        if used:
            row["justification"] = justify_from_inventory(
                str(row["suggestion"]), used, language
            )
        row["meta"] = meta
        out.append(row)
    return out


def fridge_fallback(
    available: list[str],
    *,
    language: str = "sv",
) -> dict[str, Any]:
    """
    ONE honest fallback when nothing viable cooks from the inventory.
    Offers egg sandwiches if eggs are visible, else honesty + shopping escape hatch.
    """
    avail = names_only(available)
    avail_set = set(avail)
    sv = language == "sv"
    has_eggs = _covers("ägg", avail_set)
    if has_eggs:
        suggestion = "Äggmackor" if sv else "Egg sandwiches"
        justification = (
            "Med det här blir det äggmackor — eller vill du ha ett förslag med en kort inköpslista?"
            if sv
            else "With this, it’s egg sandwiches — or want a suggestion with a short shopping list?"
        )
        return {
            "suggestion": suggestion,
            "justification": justification,
            "meta": {
                "active_minutes": 8,
                "ingredients": ["ägg", "bröd", "smör", "salt", "peppar"],
                "source": SOURCE,
                "fridge_fallback": True,
                "offers_shopping": True,
                "available_ingredients": avail,
                "assume_at_home_only": True,
            },
        }
    suggestion = "Inget klart utan inköp" if sv else "Nothing ready without shopping"
    justification = (
        "Med det här räcker det inte till en rätt — vill du ha ett förslag med en kort inköpslista?"
        if sv
        else "This isn’t enough for a dish — want a suggestion with a short shopping list?"
    )
    return {
        "suggestion": suggestion,
        "justification": justification,
        "meta": {
            "active_minutes": 0,
            "ingredients": [],
            "source": SOURCE,
            "fridge_fallback": True,
            "offers_shopping": True,
            "no_cook_empty": True,
            "available_ingredients": avail,
            "assume_at_home_only": True,
        },
    }


def apply_fridge_execution(
    suggestion: str,
    execution: dict[str, Any] | None,
    *,
    ingredients: list[str],
    language: str = "sv",
    fallback: bool = False,
) -> dict[str, Any]:
    """No shopping list — recipe from confirmed ingredients only."""
    out = dict(execution or {})
    out["shopping"] = None
    out["shopping_list"] = None
    out["type"] = "recipe"
    out["url"] = None
    out["source"] = SOURCE
    ings = names_only(ingredients)
    if fallback and not ings:
        out["label"] = "Föreslå med inköpslista" if language == "sv" else "Suggest with shopping list"
        out["detail"] = (
            "Ingen receptvy — för lite synligt i kylen."
            if language == "sv"
            else "No recipe — too little visible in the fridge."
        )
        out["recipe"] = None
        return out
    out["label"] = "Laga nu" if language == "sv" else "Cook now"
    out["detail"] = (
        "Bara det du har — ingen inköpslista."
        if language == "sv"
        else "Only what you have — no shopping list."
    )
    recipe = shopping.build_recipe(suggestion, ings or None)
    if isinstance(recipe, dict):
        # Force recipe ingredients to confirmed + staples used in dish
        recipe = dict(recipe)
        if ings:
            recipe["ingredients"] = list(ings)
    out["recipe"] = recipe
    return out
