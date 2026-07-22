# -*- coding: utf-8 -*-
"""
OneChoice — one everyday decision. Never a list.
Premium mobile-first Streamlit UI.

---------------------------------------------------------------------------
STATE DIAGRAM (pages / session_state / buttons) — keep code in sync
---------------------------------------------------------------------------

Pages:
  auth              → login / signup / guest
  home              → time-aware hero + domain cards + optional free text
  fridge            → photo capture → invent confirm → decide (source=fridge_photo)
  ambiguous         → domain pick after free-text AMBIGUOUS
  not_a_decision    → soft refuse (not a decision question)
  result            → ONE decision card (food / other domains)
  execute           → food: shopping+recipe OR fridge recipe-only; workout player
  history | profile | lista

Session keys (all set via setdefault in init_state):
  page                  str   current page name
  current               dict  DecisionResult.to_dict() for active decision
  decision_id           int|None  mirror of current["decision_id"] (explicit)
  accepted              bool  True after "Handla & laga" accept (permanent lock)
  shopping_checks       dict  {f"{decision_id}:{item}": bool} checkbox state
  reroll_index          int
  last_question         str
  last_domain_hint      str|None
  route_log_id          int|None
  pending_free_text     str|None
  force_route_domain    str|None
  user_id, language, guest_mode, auth tokens, …

Button → transition:
  [home] "Bestäm åt mig" / domain chip
        → run_decision → page=result  (current set, accepted=False)

  [result] food primary "Välj"  (accepted is False)
        → accept_decision(decision_id)  # DB status=accepted
        → current.locked=True, accepted=True, disable rerolls
        → page=execute directly (one tap — no intermediate lock card)

  [result] food locked card "Handla & laga"  (returning from execute)
        → page=execute only (no second DB write; lock already permanent)

  [result] non-food primary (link / "Gör det nu")
        → accept_decision if decision_id; toast; stay on result

  [result] "Nytt förslag"  (only if not accepted and not reroll-locked)
        → run_decision(reroll=True)

  [execute] food: checklist selection → "Lägg till i handlingslista (N)" merges checked items
        → badge when merged; "Öppna listan" → page=lista
        → deferred accept also merges shopping from context (after shop is stored)

  [execute] "Tillbaka"
        → page=result  (shows Låst: <suggestion> + only Handla & laga)

  [history] "Öppna" on a row
        → restore decision; accepted food/workout → execute, else result

  [lista] toggle buttons check off bought items

  [any] error boundary catch
        → log full traceback server-side; user sees Swedish retry UI
---------------------------------------------------------------------------
"""

from __future__ import annotations

import html
import logging
import re
import traceback
import uuid
import urllib.parse
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import streamlit as st

from pathlib import Path

import db
import pipeline

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("onechoice")

st.set_page_config(
    page_title="OneChoice",
    page_icon="\u25cb",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Design tokens — premium minimal (accent ONLY on CTA, tagline dot, active nav)
BG = "#FAFAF7"
INK = "#1A1A1A"
MUTED = "#6B6B66"
BORDER = "#E5E5E0"
ACCENT = "#3B3BC4"
# Legacy aliases (non-accent UI — never use ACCENT except CTA / tag dot / active nav)
PRIMARY = INK
PRIMARY_SOFT = "#F0F0EB"
BG_SOFT = BG
NAVY = INK
SHADOW = "none"

# Lucide-style inline SVGs (stroke icons — no emoji)
ICON_HOME = (
    '<svg class="oc-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/></svg>'
)
ICON_CLOCK = (
    '<svg class="oc-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>'
)
ICON_USER = (
    '<svg class="oc-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<circle cx="12" cy="8" r="3.5"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/></svg>'
)
ICON_LIST = (
    '<svg class="oc-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M8 6h13"/><path d="M8 12h13"/><path d="M8 18h13"/>'
    '<path d="M3 6h.01"/><path d="M3 12h.01"/><path d="M3 18h.01"/></svg>'
)

# Server-side only — never render in the consumer UI
BUILD_ID = "favorite-kwarg-reload-v49-20260722"

APP_LOCAL_TZ = ZoneInfo("Europe/Stockholm")

I18N = {
    "sv": {
        "tagline": "Ett beslut. Klart.",
        "ask": "Vad behöver du bestämma?",
        "decide": "Bestäm åt mig",
        "home_or_choose": "Eller välj själv",
        "home_free_placeholder": "Skriv ditt beslut…",
        "home_free_submit": "Bestäm",
        "home_fridge_card": "Fota kylen",
        "new": "Nytt förslag",
        "lock_msg": "Det är {suggestion}. Kör.",
        "do_it": "Gör det nu",
        "go_for_it": "Gör det",
        "food_choose": "Välj",
        "handla_laga": "Handla & laga",
        "accepted": "Sparat — bra val.",
        "food_meta_buy": "{n} varor att köpa",
        "food_meta_portion_one": "1 portion",
        "food_meta_portions": "{n} portioner",
        "workout_go": "Kör",
        "workout_next": "Nästa",
        "workout_next_set": "Nästa set",
        "workout_skip": "Hoppa över",
        "workout_done_title": "Klart.",
        "workout_rest": "Vila",
        "workout_overview": "Översikt",
        "workout_awake_note": "Håll skärmen vaken under passet (bäst i PWA/native).",
        "workout_feedback_q": "Hur kändes passet?",
        "recipe_mins": "Ca {mins} min",
        "locked_title": "Låst: {suggestion}",
        "shop_title": "Inköpslista",
        "list_nav": "Lista",
        "list_title": "Inköpslista",
        "list_empty": "Listan är tom. Bestäm middag, bocka i vad du behöver och tryck Skapa lista.",
        "list_add_placeholder": "Lägg till...",
        "list_done": "Klart",
        "list_clear_done": "Rensa klara",
        "list_added_badge": "Tillagt i din lista ✓",
        "list_go": "Öppna listan",
        "list_create": "Skapa lista",
        "list_create_hint": "Bocka i det du behöver",
        "list_add_n": "Lägg till i handlingslista ({n})",
        "list_added_open": "Tillagt ✓ · Öppna listan",
        "list_skip_hint": "hoppa över om du har",
        "list_mark_all": "Markera alla",
        "list_created": "Inköpslistan är uppdaterad.",
        "list_error": "Kunde inte spara listan just nu. Försök igen.",
        "list_local_note": "Listan sparas lokalt på den här enheten (molntabellen shopping_items saknas ännu).",
        "list_guest_login_hint": "Logga in för att spara listan.",
        "list_open_history": "Se dina beslut",
        "history_open": "Öppna",
        "history_hint": "Här ser du beslut du tagit — öppna för recept och lista.",
        "history_seg_favorites": "Favoriter",
        "history_seg_history": "Historik",
        "history_favorites_empty": "Inga favoriter ännu — tryck hjärtat på en rätt.",
        "favorite_add": "Spara som favorit",
        "favorite_remove": "Ta bort favorit",
        "cook_tonight": "Laga ikväll",
        "deciding": "Bestämmer…",
        "history_status_shown": "Visat",
        "history_status_accepted": "Genomfört",
        "history_status_rejected": "Avböjt",
        "history_status_locked": "Låst",
        "recipe_title": "Recept",
        "ingredients_title": "Ingredienser",
        "steps_title": "Gör så här",
        "nutrition_section": "Näringsvärden",
        "nutrition_title": "Visa näringsvärden",
        "nutrition_hint": "Ca-värden (kcal / protein) under receptet på alla matsidor — aldrig på beslutskortet. På som standard.",
        "nutrition_recipe_toggle": "Visa ca-värden (kcal / protein)",
        "nutrition_missing": "Näringsvärden saknas",
        "nutrition_saved": "Sparat.",
        "back_to_decision": "Tillbaka",
        "error_friendly": "Något gick fel — försök igen",
        "retry": "Försök igen",
        "occasion_title": "Vart ska du?",
        "occasion_hint": "Ett tryck — sen tar jag outfiten.",
        "clothes_profile_title": "Dina kläder",
        "clothes_section": "Var handlar du / vilken avdelning?",
        "clothes_sizes": "Storlekar",
        "clothes_save": "Spara klädprofil",
        "clothes_saved": "Klädprofil sparad.",
        "refuse": "Onechoice tar vardagsbesluten. Det här beslutet är ditt.",
        "home": "Hem",
        "history": "Historik",
        "profile": "Profil",
        "history_title": "Din historik",
        "history_empty": "Inga beslut ännu.",
        "domains": {
            "food": "Mat",
            "clothes": "Kläder",
            "movie": "Film",
            "workout": "Träning",
            "weekend": "Helg",
        },
        "pro_title": "OneChoice Pro",
        "pro_desc": "Obegränsad historik och skarpare preferenser.",
        "pro_price": "49 kr/mån",
        "pro_cta": "Uppgradera",
        "pro_demo": "Aktivera Pro (demo)",
        "pro_on": "Pro aktivt",
        "empty": "Skriv en fråga eller välj en kategori.",
        "loading": "Väljer åt dig…",
        "rerolls_left": "{n} omval kvar",
        "locked_label": "Låst",
        "login_title": "Logga in",
        "signup_title": "Skapa konto",
        "email": "E-post",
        "password": "Lösenord",
        "login_cta": "Logga in",
        "signup_cta": "Registrera",
        "logout": "Logga ut",
        "privacy_link": "Integritetspolicy",
        "privacy_consent": "Jag har läst och godkänner integritetspolicyn",
        "privacy_consent_required": "Du måste godkänna integritetspolicyn för att skapa konto.",
        "gdpr_title": "Dina data",
        "gdpr_export": "Ladda ner min data",
        "gdpr_export_hint": "JSON med allt vi sparat om dig (artikel 20).",
        "gdpr_delete": "Radera mitt konto",
        "gdpr_delete_confirm": "Detta raderar allt permanent — konto, historik, preferenser och foton. Går inte att ångra.",
        "gdpr_delete_yes": "Ja, radera allt",
        "gdpr_delete_done": "Ditt konto och all data är raderade.",
        "gdpr_guest_note": "Gästläge: data finns bara lokalt i den här enheten tills du rensar den.",

        "guest": "Fortsätt som gäst (lokal demo)",
        "auth_hint": "",
        "no_supabase": "Molninloggning saknas — kör i lokalt demläge.",
        "auth_cloud_ok": "Molnet: inloggning tillgänglig",
        "auth_cloud_off": "Molnet: saknas — bara lokal demo",
        "auth_login_prompt": "Logga in för att spara dina beslut.",
        "logged_in_as": "Inloggad som",
        "too_long": "Max 200 tecken.",
        "ambiguous": "Välj vad det handlar om — så tar jag beslutet.",
        "other": "Annat",
        "not_a_decision": "Jag tar beslut, inte frågor. Vad behöver du bestämma?",
        "share": "Dela",
        "share_copied": "Kopierat!",
        "share_list": "Dela listan",
        "share_list_empty": "Inget att dela — listan är tom.",
        "share_cta": "Låt OneChoice bestämma åt dig",
        "share_landing_sub": "Ett beslut. Klart.",
        "share_open_recipe": "Recept & lista",
        "share_open_workout": "Passet",
        "fridge_cta": "Vad finns i kylen?",
        "fridge_title": "Kylskåp & skafferi",
        "fridge_hint": "Fotografera kylen — upp till 3 bilder. Bekräfta listan innan jag bestämmer.",
        "fridge_camera": "Ta foto",
        "fridge_camera_tip": "Håll telefonen upprätt så hyllan syns.",
        "fridge_photos_count": "{n} av {max} foton",
        "fridge_add_another": "Rensa kameran och ta nästa bild (t.ex. annan hylla).",
        "fridge_photos_full": "Max 3 foton — ta bort ett om du vill byta.",
        "fridge_clear_photos": "Rensa foton",
        "fridge_upload": "Ladda upp i stället",
        "fridge_scan": "Läs av",
        "fridge_scanning": "Tittar i kylen…",
        "fridge_confirm_title": "Jag ser",
        "fridge_confirm_q": "Stämmer?",
        "fridge_confirm": "Ja — bestäm rätt",
        "fridge_add": "Lägg till",
        "fridge_add_placeholder": "t.ex. ägg",
        "fridge_empty_scan": (
            "Jag kunde inte läsa av kylen — testa ett ljusare foto taget rakt framifrån. "
            "Eller lägg till råvaror manuellt nedan."
        ),
        "fridge_need_items": "Lägg till minst en råvara innan jag bestämmer — annars gissar jag bara.",
        "fridge_need_photo": "Lägg till minst ett foto.",
        "fridge_vision_error": "Kunde inte läsa fotot",
        "fridge_api_ok": "Grok API: kopplad",
        "fridge_api_missing": "Grok API: saknas — vision körs inte. Secrets → GROK_API_KEY = \"xai-...\"",
        "fridge_api_diag": "Secrets-diagnos: {detail}",
        "fridge_scan_took": "Klart på {secs}s · {n} varor",
        "fridge_manual": "Fortsätt och lägg till själv",
        "fridge_cook": "Laga nu",
        "fridge_shop_alt": "Föreslå med inköpslista",
        "fridge_remove": "Ta bort",
    },
    "en": {
        "tagline": "One decision. Done.",
        "ask": "What do you need decided?",
        "decide": "Decide for me",
        "home_or_choose": "Or choose yourself",
        "home_free_placeholder": "Type your decision…",
        "home_free_submit": "Decide",
        "home_fridge_card": "Snap the fridge",
        "new": "New suggestion",
        "lock_msg": "It’s {suggestion}. Go.",
        "do_it": "Do it now",
        "go_for_it": "Do it",
        "food_choose": "Choose",
        "handla_laga": "Shop & cook",
        "accepted": "Saved — good call.",
        "food_meta_buy": "{n} items to buy",
        "food_meta_portion_one": "1 serving",
        "food_meta_portions": "{n} servings",
        "workout_go": "Go",
        "workout_next": "Next",
        "workout_next_set": "Next set",
        "workout_skip": "Skip",
        "workout_done_title": "Done.",
        "workout_rest": "Rest",
        "workout_overview": "Overview",
        "workout_awake_note": "Keep the screen awake during the session (best in PWA/native).",
        "workout_feedback_q": "How did it feel?",
        "recipe_mins": "About {mins} min",
        "locked_title": "Locked: {suggestion}",
        "shop_title": "Shopping list",
        "list_nav": "List",
        "list_title": "Shopping list",
        "list_empty": "Your list is empty. Pick dinner, check what you need, then Create list.",
        "list_add_placeholder": "Add...",
        "list_done": "Done",
        "list_clear_done": "Clear done",
        "list_added_badge": "Added to your list ✓",
        "list_go": "Open list",
        "list_create": "Create list",
        "list_create_hint": "Check what you need",
        "list_add_n": "Add to shopping list ({n})",
        "list_added_open": "Added ✓ · Open list",
        "list_skip_hint": "skip if you have it",
        "list_mark_all": "Select all",
        "list_created": "Shopping list updated.",
        "list_error": "Could not save the list right now. Try again.",
        "list_local_note": "List is saved on this device (cloud table shopping_items is not set up yet).",
        "list_guest_login_hint": "Sign in to save your list.",
        "list_open_history": "See your decisions",
        "history_open": "Open",
        "history_hint": "Decisions you took — open for recipe and list.",
        "history_seg_favorites": "Favorites",
        "history_seg_history": "History",
        "history_favorites_empty": "No favorites yet — tap the heart on a dish.",
        "favorite_add": "Save favorite",
        "favorite_remove": "Remove favorite",
        "cook_tonight": "Cook tonight",
        "deciding": "Deciding…",
        "history_status_shown": "Shown",
        "history_status_accepted": "Done",
        "history_status_rejected": "Rejected",
        "history_status_locked": "Locked",
        "recipe_title": "Recipe",
        "ingredients_title": "Ingredients",
        "steps_title": "Steps",
        "nutrition_section": "Nutrition",
        "nutrition_title": "Show nutrition estimates",
        "nutrition_hint": "Approx. kcal / protein under the recipe on all food pages — never on the decision card. On by default.",
        "nutrition_recipe_toggle": "Show approx. nutrition (kcal / protein)",
        "nutrition_missing": "Nutrition unavailable",
        "nutrition_saved": "Saved.",
        "back_to_decision": "Back",
        "error_friendly": "Something went wrong — try again",
        "retry": "Try again",
        "occasion_title": "Where are you going?",
        "occasion_hint": "One tap — then I’ll pick the outfit.",
        "clothes_profile_title": "Your clothes",
        "clothes_section": "Which section do you shop?",
        "clothes_sizes": "Sizes",
        "clothes_save": "Save clothes profile",
        "clothes_saved": "Clothes profile saved.",
        "refuse": "Onechoice handles everyday decisions. This one is yours.",
        "home": "Home",
        "history": "History",
        "profile": "Profile",
        "history_title": "Your history",
        "history_empty": "No decisions yet.",
        "domains": {
            "food": "Food",
            "clothes": "Clothes",
            "movie": "Movie",
            "workout": "Workout",
            "weekend": "Weekend",
        },
        "pro_title": "OneChoice Pro",
        "pro_desc": "Unlimited history and sharper preferences.",
        "pro_price": "$5/mo",
        "pro_cta": "Upgrade",
        "pro_demo": "Activate Pro (demo)",
        "pro_on": "Pro active",
        "empty": "Enter a question or pick a category.",
        "loading": "Choosing for you…",
        "rerolls_left": "{n} rerolls left",
        "locked_label": "Locked",
        "login_title": "Log in",
        "signup_title": "Create account",
        "email": "Email",
        "password": "Password",
        "login_cta": "Log in",
        "signup_cta": "Sign up",
        "logout": "Log out",
        "privacy_link": "Privacy policy",
        "privacy_consent": "I have read and accept the privacy policy",
        "privacy_consent_required": "You must accept the privacy policy to create an account.",
        "gdpr_title": "Your data",
        "gdpr_export": "Download my data",
        "gdpr_export_hint": "JSON of everything we store about you (Article 20).",
        "gdpr_delete": "Delete my account",
        "gdpr_delete_confirm": "This permanently deletes everything — account, history, preferences and photos. Cannot be undone.",
        "gdpr_delete_yes": "Yes, delete everything",
        "gdpr_delete_done": "Your account and all data have been deleted.",
        "gdpr_guest_note": "Guest mode: data stays only on this device until you clear it.",

        "guest": "Continue as guest (local demo)",
        "auth_hint": "",
        "no_supabase": "Cloud sign-in missing — running local demo.",
        "auth_cloud_ok": "Cloud: sign-in available",
        "auth_cloud_off": "Cloud: missing — local demo only",
        "auth_login_prompt": "Sign in to save your decisions.",
        "logged_in_as": "Signed in as",
        "too_long": "Max 200 characters.",
        "ambiguous": "Pick what this is about — then I’ll decide.",
        "other": "Other",
        "not_a_decision": "I make decisions, not answer questions. What do you need decided?",
        "share": "Share",
        "share_copied": "Copied!",
        "share_list": "Share list",
        "share_list_empty": "Nothing to share — the list is empty.",
        "share_cta": "Let OneChoice decide for you",
        "share_landing_sub": "One decision. Done.",
        "share_open_recipe": "Recipe & list",
        "share_open_workout": "The workout",
        "fridge_cta": "What’s in the fridge?",
        "fridge_title": "Fridge & pantry",
        "fridge_hint": "Photograph the fridge — up to 3 photos. Confirm the list before I decide.",
        "fridge_camera": "Take photo",
        "fridge_camera_tip": "Hold the phone upright so the shelf is visible.",
        "fridge_photos_count": "{n} of {max} photos",
        "fridge_add_another": "Clear the camera and take the next photo (e.g. another shelf).",
        "fridge_photos_full": "Max 3 photos — remove one to replace.",
        "fridge_clear_photos": "Clear photos",
        "fridge_upload": "Upload instead",
        "fridge_scan": "Scan",
        "fridge_scanning": "Looking in the fridge…",
        "fridge_confirm_title": "I see",
        "fridge_confirm_q": "Looks right?",
        "fridge_confirm": "Yes — pick a dish",
        "fridge_add": "Add",
        "fridge_add_placeholder": "e.g. eggs",
        "fridge_empty_scan": (
            "I couldn’t read the fridge — try a brighter photo straight on. "
            "Or add ingredients manually below."
        ),
        "fridge_need_items": "Add at least one ingredient before I decide — otherwise I’m just guessing.",
        "fridge_need_photo": "Add at least one photo.",
        "fridge_vision_error": "Couldn’t read the photo",
        "fridge_api_ok": "Grok API: connected",
        "fridge_api_missing": "Grok API: missing — vision won’t run. Secrets → GROK_API_KEY = \"xai-...\"",
        "fridge_api_diag": "Secrets diagnosis: {detail}",
        "fridge_scan_took": "Done in {secs}s · {n} items",
        "fridge_manual": "Continue and add manually",
        "fridge_cook": "Cook now",
        "fridge_shop_alt": "Suggest with shopping list",
        "fridge_remove": "Remove",
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("language", "sv")
    return I18N.get(lang, I18N["sv"]).get(key, key)


def domain_label(domain: str) -> str:
    lang = st.session_state.get("language", "sv")
    if domain in ("other", "annat"):
        return t("other")
    return I18N.get(lang, I18N["sv"])["domains"].get(domain, domain)


def _movie_kind_header_label(ctx: dict[str, Any], language: str) -> str:
    """
    Card header label must reflect the suggestion format:
      - series + avsnitt  -> AVSNITT
      - series + ny_serie -> NY SERIE
      - film -> FILM
    Never show FILM for series suggestions.
    """
    import movie_domain as md

    fmt = md.normalize_format(ctx.get("format") or st.session_state.get("movie_format") or "avsnitt")
    ctx_kind = str(ctx.get("kind") or "").lower()
    kind = ctx_kind if ctx_kind in ("series", "film") else md.format_kind(fmt)

    if kind == "series":
        if fmt == "avsnitt":
            return "AVSNITT" if language == "sv" else "EPISODE"
        if fmt == "ny_serie":
            return "NY SERIE" if language == "sv" else "NEW SERIES"
        # Fallback for other series time windows
        row = md.FORMATS.get(fmt) or {}
        label = str(row.get(language) or row.get("sv") or fmt)
        return label.upper()
    if kind == "film":
        return "FILM" if language == "sv" else "FILM"
    row = md.FORMATS.get(fmt) or {}
    label = str(row.get(language) or row.get("sv") or fmt)
    return label.upper()


def _movie_service_label(service: str) -> str:
    return {
        "netflix": "Netflix",
        "viaplay": "Viaplay",
        "hbo_max": "HBO Max",
        "disney_plus": "Disney+",
        "svt_play": "SVT Play",
        "prime": "Prime Video",
        "tv4_play": "TV4 Play",
    }.get(service, service)


def _movie_vote_line(vote_average: Any) -> str | None:
    if vote_average is None:
        return None
    try:
        v = float(vote_average)
    except (TypeError, ValueError):
        return None
    # Swedish decimal comma, one decimal digit.
    v_s = f"{v:.1f}".replace(".", ",")
    return f"★ {v_s}"


def _movie_rating_line(ctx: dict[str, Any]) -> str | None:
    star = _movie_vote_line(ctx.get("movie_tmdb_vote_average"))
    if not star:
        return None
    runtime = ctx.get("movie_runtime_min")
    service = ctx.get("movie_service")
    parts = [star]
    if runtime is not None:
        try:
            parts.append(f"{int(runtime)} min")
        except (TypeError, ValueError):
            pass
    if service:
        parts.append(_movie_service_label(str(service)))
    return " · ".join(parts)


def _render_movie_card_html(
    *,
    language: str,
    suggestion: str,
    justification: str,
    ctx: dict[str, Any],
    lock_label_html: str | None = None,
    lock_body_html: str | None = None,
    share_corner_html: str = "",
) -> str:
    import movie_domain as md  # noqa: F401  (used for label helper)

    header = _movie_kind_header_label(ctx, language)
    poster_url = ctx.get("movie_poster_url")
    year = ctx.get("movie_tmdb_year")
    rating = _movie_rating_line(ctx)

    poster_html = ""
    if poster_url:
        poster_html = (
            f'<img class="oc-movie-poster" src="{html.escape(str(poster_url))}" alt=""/>'
        )

    year_html = ""
    if year is not None and str(year).strip():
        year_html = f'<div class="oc-movie-year">{html.escape(str(year))}</div>'

    just_html = ""
    if lock_body_html:
        # lock_body_html already includes a <p>…</p> wrapper; force our class.
        just_html = lock_body_html.replace("<p>", '<p class="oc-movie-just">', 1)
    elif justification:
        just_html = f'<p class="oc-movie-just">{html.escape(justification)}</p>'

    rating_html = ""
    if rating:
        rating_html = f'<p class="oc-movie-rating">{html.escape(rating)}</p>'

    lock_html = f"{lock_label_html}" if lock_label_html else ""
    share_html = share_corner_html or ""

    return (
        '<div class="oc-decision oc-movie-decision">'
        f"{share_html}"
        '<div class="oc-movie-row">'
        f"{poster_html}"
        '<div class="oc-movie-col">'
        f'<div class="label oc-movie-kind">{html.escape(header)}</div>'
        f"<h1>{html.escape(suggestion)}</h1>"
        f"{year_html}"
        f"{just_html}"
        f"{rating_html}"
        "</div>"
        "</div>"
        f"{lock_html}"
        "</div>"
    )


def _food_meta_line(
    *,
    language: str,
    ctx: dict[str, Any],
    shop: dict[str, Any] | None = None,
    recipe: dict[str, Any] | None = None,
) -> str:
    """One muted line: ⏱ min · portions · N varor att köpa."""
    bits: list[str] = []
    mins = None
    if isinstance(recipe, dict):
        mins = recipe.get("active_minutes") or recipe.get("total_minutes")
    if mins is None:
        mins = ctx.get("active_minutes")
    if mins is None and isinstance(ctx.get("recipe"), dict):
        mins = ctx["recipe"].get("active_minutes") or ctx["recipe"].get("total_minutes")
    if mins is not None:
        try:
            bits.append(f"⏱ {int(mins)} min")
        except (TypeError, ValueError):
            pass

    portions = None
    if isinstance(recipe, dict):
        portions = recipe.get("portioner") or recipe.get("portions")
    if portions is None and isinstance(ctx.get("recipe"), dict):
        portions = ctx["recipe"].get("portioner") or ctx["recipe"].get("portions")
    if portions is None:
        portions = 1
    try:
        n_p = int(portions)
        if n_p <= 1:
            bits.append(t("food_meta_portion_one"))
        else:
            bits.append(t("food_meta_portions").format(n=n_p))
    except (TypeError, ValueError):
        bits.append(t("food_meta_portion_one"))

    n_buy = _shop_item_count(shop if isinstance(shop, dict) else ctx.get("shopping"))
    if n_buy > 0:
        bits.append(t("food_meta_buy").format(n=n_buy))
    return " · ".join(bits)


def _render_food_card_html(
    *,
    language: str,
    suggestion: str,
    justification: str,
    ctx: dict[str, Any],
    lock_label_html: str | None = None,
    lock_body_html: str | None = None,
    share_corner_html: str = "",
) -> str:
    """Pre-lock / lock food card: category image + title + justification + meta."""
    import base64

    import food_categories as fcat

    cat = fcat.infer_dish_category(
        suggestion,
        meta={
            **(ctx if isinstance(ctx, dict) else {}),
            "dish_category": (ctx or {}).get("dish_category"),
        },
    )
    img_html = ""
    raw = fcat.dish_image_bytes(cat)
    if raw:
        b64 = base64.b64encode(raw).decode("ascii")
        img_html = (
            f'<img class="oc-food-img" src="data:image/jpeg;base64,{b64}" alt=""/>'
        )

    shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
    recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
    if not recipe and shop:
        recipe = shop.get("recipe") if isinstance(shop.get("recipe"), dict) else None
    meta = _food_meta_line(language=language, ctx=ctx, shop=shop, recipe=recipe)

    just_html = ""
    if lock_body_html:
        just_html = lock_body_html.replace("<p>", '<p class="oc-food-just">', 1)
    elif justification:
        just_html = f'<p class="oc-food-just">{html.escape(justification)}</p>'

    meta_html = (
        f'<p class="oc-food-meta">{html.escape(meta)}</p>' if meta else ""
    )
    lock_html = lock_label_html or ""
    share_html = share_corner_html or ""

    return (
        '<div class="oc-decision oc-food-decision">'
        f"{share_html}"
        f"{img_html}"
        '<div class="oc-food-body">'
        f"<h1>{html.escape(suggestion)}</h1>"
        f"{just_html}"
        f"{meta_html}"
        f"{lock_html}"
        "</div>"
        "</div>"
    )


def _domain_card_button_css() -> str:
    """Per-domain SVG icons as ::before on session-safe card buttons."""
    rules: list[str] = []
    for domain, svg in _DOMAIN_CARD_ICONS.items():
        uri = urllib.parse.quote(svg.replace("\n", " ").strip())
        rules.append(
            f"""
[class*="st-key-home_domain_{domain}"] div.stButton > button::before {{
    content: "";
    display: inline-block;
    width: 20px;
    height: 20px;
    flex: 0 0 20px;
    margin-right: 8px;
    background: center / contain no-repeat url("data:image/svg+xml,{uri}");
}}"""
        )
    return "\n".join(rules)


def inject_css() -> None:
    st.markdown(
        f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Sora:wght@600;700&display=swap");
:root {{
    --oc-bg: {BG};
    --oc-ink: {INK};
    --oc-muted: {MUTED};
    --oc-border: {BORDER};
    --oc-accent: {ACCENT};
}}
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > .main,
section.main, .main .block-container {{
    background: var(--oc-bg) !important;
    background-color: var(--oc-bg) !important;
    background-image: none !important;
}}
html, body, .stApp, [data-testid="stAppViewContainer"] {{
    font-family: "Inter", "Helvetica Neue", sans-serif !important;
    font-weight: 400;
    color: var(--oc-ink) !important;
    -webkit-font-smoothing: antialiased;
}}
h1, h2, h3, h4, h5, h6, .oc-logo, .oc-decision h1, .oc-pro h2 {{
    font-family: "Sora", "Inter", sans-serif !important;
}}
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], .stDeployButton,
[data-testid="stSidebar"], [data-testid="stHeader"] {{ display: none !important; }}
footer {{ visibility: hidden !important; }}
section.main, [data-testid="stAppViewContainer"] > .main {{
    padding-top: 0 !important;
}}
.block-container {{
    max-width: 420px !important;
    padding: calc(52px + env(safe-area-inset-top) + 40px) 20px calc(88px + env(safe-area-inset-bottom)) !important;
    margin: 0 auto !important;
}}
@media (max-width: 768px) {{
    .block-container {{ padding: calc(52px + env(safe-area-inset-top) + 40px) 20px calc(88px + env(safe-area-inset-bottom)) !important; }}
}}
/* Collapse in-flow chrome wrappers — fixed header/lang must not reserve vertical space */
div[data-testid="element-container"]:has(.oc-header),
div[data-testid="element-container"]:has(.st-key-oc_lang_bar) {{
    margin: 0 !important;
    padding: 0 !important;
    min-height: 0 !important;
    height: 0 !important;
    overflow: visible !important;
}}
/* Fridge camera */
.block-container:has([data-testid="stCameraInput"]) {{
    max-width: min(100vw, 480px) !important;
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    padding-top: 0.4rem !important;
}}
.block-container:has([data-testid="stCameraInput"]) .oc-logo {{
    font-size: 1.2rem !important;
    margin: 0.1rem 0 0 !important;
}}
.block-container:has([data-testid="stCameraInput"]) .oc-tagline {{
    font-size: 0.95rem !important;
    margin: 0 0 0.25rem !important;
}}
div[data-testid="stCameraInput"] {{ width: 100% !important; }}
div[data-testid="stCameraInputWebcamComponent"],
div[data-testid="stCameraInput"] > div {{
    width: 100% !important; height: auto !important;
    min-height: 0 !important; max-height: none !important; aspect-ratio: auto !important;
}}
div[data-testid="stCameraInputWebcamStyledBox"] {{
    width: 100% !important;
    height: min(48vh, 380px) !important;
    min-height: min(48vh, 380px) !important;
    max-height: min(48vh, 380px) !important;
    aspect-ratio: auto !important; display: flex !important;
    overflow: hidden !important; border-radius: 12px 12px 0 0 !important;
    border: 1px solid var(--oc-border) !important; box-shadow: none !important;
}}
div[data-testid="stCameraInputWebcamStyledBox"] video,
div[data-testid="stCameraInputWebcamStyledBox"] img,
div[data-testid="stCameraInputWebcamStyledBox"] canvas {{
    width: 100% !important; height: 100% !important;
    object-fit: cover !important; object-position: center center !important;
}}
div[data-testid="stCameraInputButton"],
div[data-testid="stCameraInput"] button {{
    width: 100% !important; min-height: 3.1rem !important;
    margin-top: 0 !important; position: relative !important; z-index: 6 !important;
}}
/* Wordmark — solid ink, Sora, no two-tone */
.oc-logo {{
    text-align: center;
    font-family: "Sora", "Inter", sans-serif !important;
    font-weight: 700 !important;
    font-size: 1.65rem !important;
    letter-spacing: -0.03em !important;
    color: var(--oc-ink) !important;
    margin: 0.6rem 0 0.35rem !important;
}}
.oc-logo em {{ font-style: normal !important; color: var(--oc-ink) !important; }}
.oc-tagline {{
    text-align: center;
    color: var(--oc-muted) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 1rem !important;
    font-weight: 400 !important;
    margin: 0 0 48px !important;
    letter-spacing: -0.01em;
}}
.oc-tag-dot {{ color: var(--oc-accent) !important; }}
/* Language: text link SV · EN */
.oc-lang {{
    position: fixed !important;
    top: max(0.85rem, env(safe-area-inset-top)) !important;
    right: 1rem !important;
    z-index: 1100 !important;
    display: flex !important;
    align-items: center !important;
    gap: 0.35rem !important;
    font-family: "Inter", sans-serif !important;
    font-size: 14px !important;
    line-height: 1 !important;
}}
.oc-lang a {{
    color: var(--oc-muted) !important;
    text-decoration: none !important;
    font-weight: 500 !important;
    box-shadow: none !important;
    background: transparent !important;
    border: none !important;
    width: auto !important; height: auto !important;
    border-radius: 0 !important;
    padding: 0 !important;
}}
.oc-lang a.active {{ color: var(--oc-ink) !important; font-weight: 600 !important; }}
.oc-lang .oc-lang-sep {{ color: var(--oc-muted) !important; user-select: none; }}
/* Textarea */
div[data-testid="stTextArea"] > div, .stTextArea > div, .stTextArea [data-baseweb="textarea"] {{
    background: transparent !important; border: none !important; box-shadow: none !important;
}}
.stTextArea textarea {{
    background: #fff !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 16px !important;
    min-height: 110px !important;
    font-size: 1.02rem !important;
    padding: 1rem 1.1rem !important;
    box-shadow: none !important;
    color: var(--oc-ink) !important;
    font-family: "Inter", sans-serif !important;
}}
.stTextArea textarea:focus {{
    border-color: var(--oc-accent) !important;
    box-shadow: none !important;
    outline: none !important;
}}
div.stButton {{ display: flex !important; justify-content: center !important; }}
/* CTA — only place with accent fill + visual weight */
div.stButton > button[data-testid="baseButton-primary"],
div.stButton > button[kind="primary"],
button[data-testid="baseButton-primary"] {{
    background: {ACCENT} !important;
    background-color: {ACCENT} !important;
    background-image: none !important;
    color: #fff !important;
    border: none !important;
    border-radius: 999px !important;
    font-weight: 600 !important;
    font-size: 1.02rem !important;
    height: auto !important;
    min-height: 0 !important;
    padding: 16px 1.5rem !important;
    width: 100% !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
}}
/* Secondary buttons — quiet by default (NO underline). Link-style only via .oc-link-wrap. */
div.stButton > button[data-testid="baseButton-secondary"],
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="stBaseButton-secondary"] {{
    background: transparent !important; color: var(--oc-muted) !important;
    border: none !important; box-shadow: none !important;
    border-radius: 0 !important; font-weight: 500 !important;
    min-height: 36px !important; width: auto !important;
    font-size: 0.95rem !important; text-decoration: none !important;
    font-family: "Inter", sans-serif !important;
}}
/* Intentional text-link secondaries (Nytt förslag / mode switch) */
.oc-link-wrap + div[data-testid="element-container"] div.stButton > button,
div[data-testid="element-container"]:has(.oc-link-wrap) + div[data-testid="element-container"] div.stButton > button {{
    text-decoration: underline !important;
    text-underline-offset: 3px !important;
}}
/* Occasion / meal chip rows ONLY — never nav, never lista, never domain cards */
.st-key-clothes_occasion [data-testid="stHorizontalBlock"] div.stButton > button,
.st-key-clothes_occasion [data-testid="stHorizontalBlock"] div.stButton > button[data-testid="baseButton-secondary"],
.st-key-clothes_occasion [data-testid="stHorizontalBlock"] div.stButton > button[data-testid="baseButton-primary"],
.st-key-meal_chips [data-testid="stHorizontalBlock"] div.stButton > button,
.st-key-meal_chips [data-testid="stHorizontalBlock"] div.stButton > button[data-testid="baseButton-secondary"],
.st-key-meal_chips [data-testid="stHorizontalBlock"] div.stButton > button[data-testid="baseButton-primary"] {{
    background: transparent !important;
    color: var(--oc-ink) !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    min-height: 2.5rem !important;
    height: auto !important;
    width: 100% !important;
    text-decoration: none !important;
    padding: 0.5rem 0.75rem !important;
    font-family: "Inter", sans-serif !important;
}}
.st-key-clothes_occasion [data-testid="stHorizontalBlock"] div.stButton > button[data-testid="baseButton-primary"],
.st-key-meal_chips [data-testid="stHorizontalBlock"] div.stButton > button[data-testid="baseButton-primary"] {{
    background: transparent !important;
    color: var(--oc-ink) !important;
    font-weight: 600 !important;
    border-color: var(--oc-ink) !important;
    box-shadow: none !important;
}}
/* Domain/meal chips keep oval chrome via scoped rules below — NOT global ButtonGroup */
/* Fixed app header — one frosted bar; lang pills overlay the right slot */
.oc-header {{
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    z-index: 1100 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: calc(12px + env(safe-area-inset-top)) max(20px, env(safe-area-inset-right)) 12px max(20px, env(safe-area-inset-left)) !important;
    margin: 0 !important;
    box-sizing: border-box !important;
    min-height: 52px !important;
    background: rgba(250, 250, 247, 0.72) !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.05) !important;
    pointer-events: none !important;
}}
.oc-header-wordmark, .oc-header .oc-logo {{
    position: absolute !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    margin: 0 !important;
    padding: 0 !important;
    font-family: "Sora", "Inter", sans-serif !important;
    font-size: 22px !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    color: var(--oc-ink) !important;
    text-align: center !important;
    line-height: 1.1 !important;
    width: max-content !important;
    pointer-events: none !important;
}}
/* Home hero — single centered wrapper (headline + CTA share one axis) */
.st-key-home_hero,
.st-key-home_hero [data-testid="stVerticalBlock"],
.st-key-home_hero [data-testid="stVerticalBlockBorderWrapper"],
.st-key-home_hero [data-testid="stMarkdownContainer"] {{
    gap: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}}
.st-key-home_hero {{
    position: relative !important;
    width: 100% !important;
    margin: 0 0 48px !important;
    padding: 0 !important;
    max-height: none !important;
    min-height: 0 !important;
    overflow: visible !important;
    box-sizing: border-box !important;
}}
.oc-hero {{
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 420px;
    margin: 0 auto;
    padding: 0 20px;
    box-sizing: border-box;
    text-align: center;
}}
.st-key-home_hero .oc-hero-orb {{
    position: absolute;
    left: 50%;
    top: 0;
    width: 55vw;
    height: 55vw;
    max-width: 280px;
    max-height: 280px;
    margin: 0;
    background: radial-gradient(circle, rgba(79, 70, 229, 0.9) 0%, rgba(79, 70, 229, 0) 68%);
    filter: blur(60px);
    opacity: 0.12;
    pointer-events: none;
    z-index: 0;
    transform: translateX(-50%) translateY(-42%);
    animation: oc-orb-breathe 8s ease-in-out infinite alternate;
    overflow: hidden;
    clip-path: inset(-40% -20% 20% -20%);
}}
.oc-hero-orb {{
    z-index: 0 !important;
}}
.oc-header, .st-key-oc_lang_bar {{
    z-index: 1100 !important;
}}
@keyframes oc-orb-breathe {{
    from {{ transform: translateX(-50%) translateY(-42%) scale(1); }}
    to {{ transform: translateX(-50%) translateY(-42%) scale(1.06); }}
}}
.oc-hero-title {{
    position: relative;
    z-index: 1;
    display: block;
    font-family: "Sora", "Inter", sans-serif !important;
    font-size: clamp(38px, 10vw, 52px) !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
    line-height: 1.05 !important;
    color: var(--oc-ink) !important;
    text-align: center !important;
    margin: 0 0 28px !important;
    padding: 0 !important;
    width: 100% !important;
}}
.st-key-home_hero [data-testid="stHeaderActionElements"],
.st-key-home_hero a.header-anchor {{
    display: none !important;
}}
/* oc-cta — hero primary button (replaces anchor href navigation) */
.st-key-home_hero div.stButton {{
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
}}
.st-key-home_hero div.stButton > button,
.st-key-home_hero div.stButton > button[data-testid="baseButton-primary"],
.st-key-home_hero div.stButton > button[kind="primary"] {{
    display: block !important;
    width: 100% !important;
    box-sizing: border-box !important;
    margin: 0 !important;
    padding: 16px 1.5rem !important;
    background: {ACCENT} !important;
    background-color: {ACCENT} !important;
    color: #fff !important;
    border: none !important;
    border-radius: 999px !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 600 !important;
    font-size: 1.02rem !important;
    line-height: 1.2 !important;
    text-align: center !important;
    text-decoration: none !important;
    box-shadow: none !important;
    transition: opacity 150ms ease !important;
    min-height: 52px !important;
}}
.st-key-home_hero div.stButton > button:hover,
.st-key-home_hero div.stButton > button:focus {{
    color: #fff !important;
    opacity: 0.92 !important;
    background: {ACCENT} !important;
}}
.st-key-home_weekend_alt {{
    margin: 8px 0 0 !important;
    text-align: center !important;
    width: 100% !important;
}}
.oc-section-label {{
    display: block !important;
    font-size: 11px !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--oc-muted) !important;
    font-weight: 600 !important;
    text-align: center !important;
    margin: 0 0 12px !important;
    padding: 0 !important;
    font-family: "Inter", sans-serif !important;
}}
.st-key-home_domains {{
    margin: 0 0 20px !important;
    padding: 0 !important;
    width: 100% !important;
}}
.st-key-home_domains [data-testid="stMarkdownContainer"],
.st-key-home_domains [data-testid="stMarkdownContainer"] p {{
    margin: 0 !important;
    padding: 0 !important;
}}
.st-key-home_domains [data-testid="stHorizontalBlock"] {{
    gap: 10px !important;
    margin-bottom: 10px !important;
}}
/* Domain cards — button IS the card (no nested pill / no outer shell) */
.st-key-home_domains [class*="st-key-home_domain_"],
[class*="st-key-home_domain_"] {{
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}}
.st-key-home_domains [class*="st-key-home_domain_"] [data-testid="stVerticalBlockBorderWrapper"],
.st-key-home_domains [class*="st-key-home_domain_"] [data-testid="stVerticalBlock"] {{
    gap: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}}
[class*="st-key-home_domain_"] div.stButton {{
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
}}
[class*="st-key-home_domain_"] div.stButton > button,
[class*="st-key-home_domain_"] div.stButton > button[data-testid="baseButton-secondary"],
[class*="st-key-home_domain_"] div.stButton > button[kind="secondary"],
[class*="st-key-home_domain_"] button[data-testid="stBaseButton-secondary"] {{
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 0 !important;
    width: 100% !important;
    min-height: 52px !important;
    height: 52px !important;
    max-height: 52px !important;
    background: #fff !important;
    background-color: #fff !important;
    border-radius: 14px !important;
    border: 1px solid rgba(0, 0, 0, 0.06) !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
    box-sizing: border-box !important;
    color: var(--oc-ink) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    line-height: 1.2 !important;
    text-align: left !important;
    padding: 0 14px !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    text-decoration: none !important;
    text-underline-offset: unset !important;
    transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease !important;
    -webkit-tap-highlight-color: transparent !important;
}}
[class*="st-key-home_domain_"] div.stButton > button:hover,
[class*="st-key-home_domain_"] div.stButton > button:focus,
[class*="st-key-home_domain_"] div.stButton > button[data-testid="baseButton-secondary"]:hover,
[class*="st-key-home_domain_"] div.stButton > button[kind="secondary"]:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06) !important;
    border-color: rgba(0, 0, 0, 0.1) !important;
    background: #fff !important;
    background-color: #fff !important;
    color: var(--oc-ink) !important;
    text-decoration: none !important;
}}
{_domain_card_button_css()}
.oc-domain-card-icon {{
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 20px !important;
    height: 20px !important;
    flex: 0 0 20px !important;
    line-height: 0 !important;
    color: var(--oc-ink) !important;
}}
.oc-domain-card-icon svg {{
    width: 20px !important;
    height: 20px !important;
    stroke: currentColor !important;
    stroke-width: 1.5 !important;
    fill: none !important;
}}
.oc-domain-card-label {{
    font-family: "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    flex: 1 1 auto !important;
    min-width: 0 !important;
}}
.st-key-home_free_form {{
    margin: 24px 0 20px !important;
    padding: 0 !important;
    width: 100% !important;
}}
.st-key-home_free_form [data-testid="stForm"] {{
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
}}
.st-key-home_free_form [data-testid="stHorizontalBlock"] {{
    align-items: flex-end !important;
    gap: 8px !important;
}}
.st-key-home_free_form [data-testid="stHorizontalBlock"] > div[data-testid="stColumn"]:first-child {{
    min-width: 72% !important;
}}
.st-key-home_free_form [data-testid="stWidgetLabel"] {{
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
}}
.st-key-home_free_form [data-testid="stTextInput"] {{
    margin: 0 !important;
}}
.st-key-home_free_form [data-testid="stTextInput"] input {{
    border-radius: 12px !important;
    min-height: 48px !important;
    height: 48px !important;
    font-size: 16px !important;
    padding: 12px 14px !important;
    border: 1px solid var(--oc-border) !important;
    transition: border-color 150ms ease !important;
}}
.st-key-home_free_form [data-testid="stTextInput"] input:focus {{
    border-color: var(--oc-accent) !important;
    box-shadow: none !important;
}}
.st-key-home_free_form [data-testid="stFormSubmitButton"] {{
    display: flex !important;
    align-items: flex-end !important;
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
}}
.st-key-home_free_form [data-testid="stFormSubmitButton"] button {{
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    width: 100% !important;
    min-width: 0 !important;
    min-height: 48px !important;
    height: 48px !important;
    margin: 0 !important;
    padding: 0 18px !important;
    border-radius: 12px !important;
    background: {ACCENT} !important;
    color: #fff !important;
    border: none !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 600 !important;
    line-height: 1 !important;
    white-space: nowrap !important;
}}
.st-key-home_free_form [data-testid="stFormSubmitButton"] button:hover {{
    opacity: 0.92 !important;
}}
.st-key-home_weekend_alt div.stButton > button {{
    background: transparent !important;
    color: var(--oc-muted) !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    text-decoration: underline !important;
    text-underline-offset: 3px !important;
    min-height: 2rem !important;
    padding: 0.25rem 0.5rem !important;
    width: auto !important;
    transition: color 150ms ease !important;
}}
.st-key-home_weekend_alt div.stButton > button:hover {{
    color: var(--oc-ink) !important;
    background: transparent !important;
}}
/* Language — fixed inside header row, top-right SV · EN */
.st-key-oc_lang_bar {{
    position: fixed !important;
    top: 0 !important;
    right: 20px !important;
    left: auto !important;
    z-index: 1000 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-end !important;
    height: calc(52px + env(safe-area-inset-top)) !important;
    padding: env(safe-area-inset-top) 0 0 !important;
    width: auto !important;
    max-width: none !important;
    background: transparent !important;
    margin: 0 !important;
    box-sizing: border-box !important;
    pointer-events: auto !important;
}}
.st-key-oc_lang_bar [data-testid="stButtonGroup"],
.st-key-oc_lang_pills [data-testid="stButtonGroup"],
.st-key-oc_lang_bar [data-testid="stPills"],
.st-key-oc_lang_pills {{
    display: flex !important;
    justify-content: flex-end !important;
    gap: 0.15rem !important;
    background: transparent !important;
}}
.st-key-oc_lang_bar button,
.st-key-oc_lang_pills button,
.st-key-oc_lang_bar [data-testid="stButtonGroup"] button,
.st-key-oc_lang_pills [data-testid="stButtonGroup"] button {{
    background: transparent !important;
    border: none !important;
    border-radius: 6px !important;
    box-shadow: none !important;
    outline: none !important;
    color: var(--oc-muted) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    min-height: 2rem !important;
    height: auto !important;
    padding: 0.35rem 0.55rem !important;
    width: auto !important;
    transition: color 150ms ease, background 150ms ease !important;
}}
.st-key-oc_lang_bar button[aria-checked="true"],
.st-key-oc_lang_pills button[aria-checked="true"] {{
    color: var(--oc-ink) !important;
    font-weight: 600 !important;
}}
/* Bottom nav — frosted glass bar */
.st-key-oc_nav_bar,
.st-key-oc_nav_pills {{
    position: fixed !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    z-index: 999 !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0.35rem 0.4rem max(0.55rem, env(safe-area-inset-bottom)) !important;
    background: rgba(250, 250, 247, 0.72) !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    border-top: 1px solid rgba(0, 0, 0, 0.05) !important;
    box-sizing: border-box !important;
}}
.st-key-oc_nav_bar [data-testid="stHorizontalBlock"] {{
    gap: 0.15rem !important;
    align-items: stretch !important;
}}
[class*="st-key-nav_"] div.stButton {{
    margin: 0 !important;
    width: 100% !important;
}}
[class*="st-key-nav_"] div.stButton > button {{
    width: 100% !important;
    background: transparent !important;
    border: none !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    min-height: 3rem !important;
    padding: 0.3rem 0.35rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.15rem !important;
    line-height: 1.1 !important;
}}
[class*="st-key-nav_"] div.stButton > button::before {{
    content: "" !important;
    display: block !important;
    width: 22px !important;
    height: 22px !important;
    background: center / contain no-repeat !important;
    opacity: 0.72 !important;
}}
.st-key-nav_home div.stButton > button::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z'/%3E%3C/svg%3E") !important;
}}
.st-key-nav_lista div.stButton > button::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01'/%3E%3C/svg%3E") !important;
}}
.st-key-nav_history div.stButton > button::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 8v5l3 2'/%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3C/svg%3E") !important;
}}
.st-key-nav_profile div.stButton > button::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M5 20a7 7 0 0 1 14 0'/%3E%3C/svg%3E") !important;
}}
[class*="st-key-nav_"] div.stButton > button[kind="primary"],
[class*="st-key-nav_"] div.stButton > button[data-testid="baseButton-primary"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
    background: rgba(59, 59, 196, 0.12) !important;
}}
[class*="st-key-nav_"] div.stButton > button[kind="primary"]::before,
[class*="st-key-nav_"] div.stButton > button[data-testid="baseButton-primary"]::before {{
    opacity: 1 !important;
}}
.st-key-nav_home div.stButton > button[kind="primary"]::before,
.st-key-nav_home div.stButton > button[data-testid="baseButton-primary"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z'/%3E%3C/svg%3E") !important;
}}
.st-key-nav_lista div.stButton > button[kind="primary"]::before,
.st-key-nav_lista div.stButton > button[data-testid="baseButton-primary"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01'/%3E%3C/svg%3E") !important;
}}
.st-key-nav_history div.stButton > button[kind="primary"]::before,
.st-key-nav_history div.stButton > button[data-testid="baseButton-primary"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 8v5l3 2'/%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3C/svg%3E") !important;
}}
.st-key-nav_profile div.stButton > button[kind="primary"]::before,
.st-key-nav_profile div.stButton > button[data-testid="baseButton-primary"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M5 20a7 7 0 0 1 14 0'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stPills"],
.st-key-oc_nav_pills [data-testid="stPills"],
.st-key-oc_nav_bar [data-testid="stButtonGroup"],
.st-key-oc_nav_pills [data-testid="stButtonGroup"] {{
    display: flex !important;
    justify-content: space-around !important;
    width: 100% !important;
    gap: 0.15rem !important;
    background: transparent !important;
}}
.st-key-oc_nav_bar button,
.st-key-oc_nav_pills button,
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button {{
    flex: 1 1 0 !important;
    background: transparent !important;
    border: none !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    min-height: 3rem !important;
    padding: 0.3rem 0.35rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.15rem !important;
    line-height: 1.1 !important;
    transition: background 150ms ease, color 150ms ease !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button::before {{
    content: "" !important;
    display: block !important;
    width: 22px !important;
    height: 22px !important;
    background: center / contain no-repeat !important;
    opacity: 0.72 !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(1)::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(1)::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(2)::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(2)::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(3)::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(3)::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 8v5l3 2'/%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(4)::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(4)::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236B6B66' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M5 20a7 7 0 0 1 14 0'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar button[aria-checked="true"],
.st-key-oc_nav_pills button[aria-checked="true"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
    background: rgba(59, 59, 196, 0.12) !important;
    border: none !important;
}}
.st-key-oc_nav_bar button[aria-checked="true"]::before,
.st-key-oc_nav_pills button[aria-checked="true"]::before {{
    opacity: 1 !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(1)[aria-checked="true"]::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(1)[aria-checked="true"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 11.5 12 5l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(2)[aria-checked="true"]::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(2)[aria-checked="true"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(3)[aria-checked="true"]::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(3)[aria-checked="true"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 8v5l3 2'/%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3C/svg%3E") !important;
}}
.st-key-oc_nav_bar [data-testid="stButtonGroup"] button:nth-child(4)[aria-checked="true"]::before,
.st-key-oc_nav_pills [data-testid="stButtonGroup"] button:nth-child(4)[aria-checked="true"]::before {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233B3BC4' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='8' r='4'/%3E%3Cpath d='M5 20a7 7 0 0 1 14 0'/%3E%3C/svg%3E") !important;
}}
.oc-decision {{
    position: relative;
    background: #fff; border-radius: 24px;
    padding: 2.2rem 1.5rem 2rem;
    box-shadow: none !important; text-align: center;
    margin: 1.1rem 0 1.35rem;
    border: 1px solid var(--oc-border);
}}
.oc-decision .label {{
    font-size: 0.72rem; color: var(--oc-muted); letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 1.15rem; font-weight: 600;
    font-family: "Inter", sans-serif !important;
}}
.oc-decision h1 {{
    font-family: "Sora", "Inter", sans-serif !important;
    font-size: clamp(2rem, 7vw, 2.35rem); font-weight: 700;
    letter-spacing: -0.03em; line-height: 1.12; margin: 0 0 1.1rem; color: var(--oc-ink);
}}
.oc-decision p {{
    font-size: 1.02rem; color: var(--oc-muted); line-height: 1.45; margin: 0;
    max-width: 22rem; margin-left: auto; margin-right: auto;
    font-family: "Inter", sans-serif !important;
}}
.oc-share-corner {{
    position: absolute;
    top: 8px;
    right: 8px;
    z-index: 4;
}}
.st-key-exec_food_host {{
    position: relative !important;
}}
.st-key-exec_fav_corner {{
    position: absolute !important;
    top: 8px !important;
    left: 8px !important;
    z-index: 5 !important;
    width: 40px !important;
    margin: 0 !important;
    padding: 0 !important;
}}
.st-key-exec_fav_corner div.stButton > button,
.st-key-exec_fav_corner button {{
    width: 40px !important;
    min-width: 40px !important;
    height: 40px !important;
    min-height: 40px !important;
    margin: 0 !important;
    padding: 0 !important;
    border: none !important;
    border-radius: 12px !important;
    background-color: rgba(255, 255, 255, 0.92) !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235c5c57' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: center !important;
    background-size: 20px 20px !important;
    color: transparent !important;
    font-size: 0 !important;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06) !important;
}}
.st-key-exec_fav_corner[data-fav="1"] div.stButton > button,
.st-key-exec_fav_corner[data-fav="1"] button,
.st-key-exec_food_host:has(.oc-fav-on) .st-key-exec_fav_corner div.stButton > button {{
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%231a1a1a' stroke='%231a1a1a' stroke-width='1.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z'/%3E%3C/svg%3E") !important;
}}
.st-key-hist_seg {{
    margin: 0 0 12px !important;
}}
.oc-fav-card {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
    border-bottom: 1px solid var(--oc-border);
}}
.oc-fav-card img {{
    width: 56px;
    height: 56px;
    object-fit: cover;
    border-radius: 10px;
    flex: 0 0 56px;
}}
.oc-fav-card .oc-fav-meta {{
    flex: 1;
    min-width: 0;
}}
.oc-fav-card .oc-fav-meta strong {{
    display: block;
    font-size: 1rem;
    color: var(--oc-ink);
}}
.oc-fav-card .oc-fav-meta span {{
    font-size: 0.85rem;
    color: var(--oc-muted);
}}
.oc-share-icon-btn {{
    width: 40px;
    height: 40px;
    margin: 0;
    padding: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: 12px;
    background-color: rgba(255, 255, 255, 0.92);
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235c5c57' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 14V3'/%3E%3Cpath d='M8 7l4-4 4 4'/%3E%3Cpath d='M5 11v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: center;
    background-size: 20px 20px;
    color: transparent;
    font-size: 0;
    line-height: 0;
    cursor: pointer;
    -webkit-tap-highlight-color: transparent;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}}
.oc-share-icon-btn:active {{
    opacity: 0.7;
}}
.oc-share-icon-btn img {{
    width: 20px;
    height: 20px;
    display: block;
    pointer-events: none;
}}
.oc-share-lista-wrap {{
    display: flex;
    justify-content: flex-end;
    align-items: center;
    min-height: 40px;
}}
.oc-share-lista-wrap .oc-share-corner {{
    position: static;
}}
.oc-share-lista-wrap .oc-share-icon-btn {{
    background-color: transparent;
    box-shadow: none;
}}
.oc-movie-decision {{
    text-align: left !important;
    padding-left: 1.3rem !important;
    padding-right: 1.3rem !important;
}}
.oc-movie-row {{
    display: flex !important;
    gap: 1rem !important;
    align-items: flex-start !important;
}}
.oc-movie-col {{
    flex: 1 1 auto !important;
    min-width: 0 !important;
}}
.oc-movie-poster {{
    flex: 0 0 auto !important;
    width: 112px !important;
    max-height: 40% !important;
    border-radius: 14px !important;
    object-fit: cover !important;
    background: #fff !important;
}}
.oc-movie-kind {{
    margin-bottom: 0.7rem !important;
}}
.oc-movie-year {{
    color: var(--oc-muted) !important;
    font-size: 1rem !important;
    margin: -0.35rem 0 0.85rem !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 600 !important;
}}
.oc-movie-just {{
    max-width: none !important;
    margin: 0 !important;
    text-align: left !important;
}}
.oc-movie-rating {{
    max-width: none !important;
    margin: 0.75rem 0 0 !important;
    text-align: left !important;
    color: var(--oc-muted) !important;
    font-weight: 500 !important;
}}
.oc-food-decision {{
    text-align: center !important;
    padding: 0 0 1.35rem !important;
    overflow: hidden !important;
}}
.oc-food-img {{
    display: block !important;
    width: 100% !important;
    aspect-ratio: 16 / 10 !important;
    object-fit: cover !important;
    border-radius: 24px 24px 0 0 !important;
    background: #eee !important;
}}
.oc-food-body {{
    padding: 1.15rem 1.35rem 0 !important;
}}
.oc-food-decision h1 {{
    margin-bottom: 0.65rem !important;
}}
.oc-food-just {{
    max-width: 22rem !important;
    margin: 0 auto !important;
}}
.oc-food-meta {{
    margin: 0.85rem auto 0 !important;
    max-width: 22rem !important;
    color: var(--oc-muted) !important;
    font-size: 0.92rem !important;
    font-weight: 500 !important;
    line-height: 1.35 !important;
    font-family: "Inter", sans-serif !important;
}}
.oc-lock {{
    display: inline-block; margin-top: 1.1rem;
    background: transparent;
    color: var(--oc-ink); font-weight: 600; font-size: 0.8rem;
    padding: 0.3rem 0.75rem; border-radius: 999px;
    border: 1px solid var(--oc-border);
}}
/* Public share landing — wordmark only, no lang bar / bottom nav */
.oc-header.oc-share-landing {{
    pointer-events: none !important;
}}
.oc-share-landing-marker {{ display: none !important; height: 0 !important; margin: 0 !important; }}
body:has(.oc-share-landing) .st-key-oc_lang_bar,
body:has(.oc-share-landing) .st-key-oc_nav_bar,
.block-container:has(.oc-share-landing) ~ * .st-key-oc_nav_bar {{
    display: none !important;
}}
.oc-share-landing .oc-decision h1 {{ font-size: 1.65rem; }}
.oc-share-cta-note {{
    text-align: center; color: var(--oc-muted); font-size: 0.92rem;
    margin: 0.2rem 0 0.9rem;
}}
.oc-refuse {{
    background: #fff; border-radius: 24px; padding: 1.6rem 1.3rem;
    text-align: center; box-shadow: none !important; color: var(--oc-muted); font-size: 1.05rem;
    line-height: 1.45; margin: 1rem 0; border: 1px solid var(--oc-border);
}}
.oc-meta {{ text-align: center; color: var(--oc-muted); font-size: 1rem; margin: 0.4rem 0 0.8rem; }}
.oc-rerolls {{
    display: flex; justify-content: center; gap: 0.45rem;
    margin: 0.15rem 0 1.15rem;
}}
.oc-rerolls i {{
    display: block; width: 7px; height: 7px; border-radius: 50%;
    background: var(--oc-ink); opacity: 1;
    transition: opacity 0.25s ease; box-shadow: none !important;
}}
.oc-rerolls i.used {{ opacity: 0.22; background: var(--oc-muted); }}
.oc-rerolls i.current {{ opacity: 1; background: var(--oc-ink); box-shadow: none !important; }}
.oc-shop, .oc-recipe, .oc-error, .oc-hist, .oc-pro {{
    background: #fff; border-radius: 20px;
    box-shadow: none !important;
    border: 1px solid var(--oc-border);
}}
.oc-shop {{
    padding: 1.25rem 1.2rem 1.1rem; margin: 0 0 1.25rem; text-align: left;
}}
.oc-shop .oc-shop-title, .oc-recipe .oc-shop-title {{
    font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600; margin: 0 0 0.85rem;
    font-family: "Inter", sans-serif !important;
}}
.oc-shop .oc-sec, .oc-recipe .oc-sec {{
    font-size: 0.68rem; letter-spacing: 0.09em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600; margin: 0.95rem 0 0.4rem;
}}
.oc-shop .oc-sec:first-of-type {{ margin-top: 0; }}
.oc-shop ul {{ list-style: none; margin: 0; padding: 0; }}
.oc-shop li {{
    display: flex; align-items: flex-start; gap: 0.65rem;
    font-size: 1rem; color: var(--oc-ink); line-height: 1.4; padding: 0.38rem 0;
}}
.oc-shop li::before {{
    content: ""; flex: 0 0 1.05rem; width: 1.05rem; height: 1.05rem;
    margin-top: 0.12rem; border-radius: 50%;
    border: 1.5px solid var(--oc-border); box-sizing: border-box;
}}
.oc-shop .oc-assumed {{
    margin: 1rem 0 0; padding-top: 0.75rem;
    border-top: 1px solid var(--oc-border);
    font-size: 0.92rem; color: var(--oc-muted); line-height: 1.4;
}}
.oc-recipe {{
    padding: 1.25rem 1.2rem 1.2rem; margin: 0 0 1.25rem; text-align: left;
}}
.oc-recipe ol {{
    margin: 0; padding-left: 1.2rem; color: var(--oc-ink); font-size: 1rem; line-height: 1.45;
}}
.oc-recipe ol li {{ margin: 0.45rem 0; }}
.oc-recipe ul {{ list-style: none; margin: 0; padding: 0; }}
.oc-recipe ul li {{
    font-size: 1rem; color: var(--oc-ink); line-height: 1.4; padding: 0.28rem 0;
}}
.oc-recipe .oc-nutrition,
.oc-nutrition {{
    margin: 0.65rem 0 0.15rem; padding: 0.55rem 0.75rem;
    font-size: 0.95rem; color: var(--oc-ink) !important; line-height: 1.35;
    font-weight: 600; letter-spacing: 0; text-transform: none;
    font-family: "Inter", sans-serif !important;
    background: #fff !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 12px !important;
}}
.oc-nutrition.missing {{
    color: var(--oc-muted) !important; font-weight: 400 !important;
}}
/* Collapsed labels must stay hidden (home textarea, meal pills) */
div[data-testid="stTextArea"] [data-testid="stWidgetLabel"],
div[data-testid="stPills"] [data-testid="stWidgetLabel"],
div[data-testid="stTextArea"] label[data-testid="stWidgetLabel"],
div[data-testid="stPills"] label[data-testid="stWidgetLabel"] {{
    display: none !important;
    visibility: hidden !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}}
[data-testid="stMarkdownContainer"] .oc-nutrition {{
    display: block !important;
    visibility: visible !important;
    opacity: 1 !important;
}}
/* Profile / checkbox labels remain readable */
div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] p,
div[data-testid="stCheckbox"] label p {{
    display: block !important;
    color: var(--oc-ink) !important;
    font-size: 0.95rem !important;
    font-family: "Inter", sans-serif !important;
}}
.oc-error {{
    padding: 1.8rem 1.4rem; text-align: center; margin: 2rem 0 1rem;
}}
.oc-error p {{ color: var(--oc-muted); font-size: 1.1rem; margin: 0 0 0.4rem; }}
.oc-link-wrap {{ text-align: center; margin: 0.35rem 0 0.9rem; }}
.oc-checks [data-testid="stWidgetLabel"],
div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {{
    display: flex !important;
}}
div[data-testid="stCheckbox"] label {{
    font-family: "Inter", sans-serif !important;
    color: var(--oc-ink) !important; font-size: 1rem !important;
}}
.oc-sec-label {{
    font-size: 0.68rem; letter-spacing: 0.09em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600; margin: 0.85rem 0 0.35rem;
}}
.oc-hist {{
    padding: 1rem 1.1rem; margin-bottom: 0.7rem;
}}
.oc-hist strong {{ display: block; font-size: 1.05rem; margin-bottom: 0.2rem; color: var(--oc-ink); }}
.oc-hist span {{ font-size: 0.9rem; color: var(--oc-muted); }}
.oc-pro {{
    padding: 2rem 1.5rem; text-align: center; margin-top: 1.5rem;
}}
.oc-pro h2 {{
    margin: 0 0 0.5rem; letter-spacing: -0.03em;
    font-family: "Sora", "Inter", sans-serif !important; color: var(--oc-ink);
}}
.oc-price {{
    font-size: 1.6rem; font-weight: 700; color: var(--oc-ink); margin: 1.1rem 0;
    font-family: "Sora", "Inter", sans-serif !important;
}}
/* Bottom nav — white bar, top border, accent only on active */
.oc-nav {{
    position: fixed !important; left: 0 !important; right: 0 !important;
    transform: none !important;
    bottom: 0 !important;
    width: 100% !important; max-width: none !important;
    z-index: 1100 !important;
    display: grid !important; grid-template-columns: repeat(4, 1fr) !important;
    gap: 0 !important;
    background: #fff !important;
    border-radius: 0 !important;
    padding: 0.55rem 0.5rem max(0.55rem, env(safe-area-inset-bottom)) !important;
    box-shadow: none !important;
    border: none !important;
    border-top: 1px solid var(--oc-border) !important;
}}
.oc-nav a, .oc-nav .oc-nav-item {{
    display: flex !important; flex-direction: column; align-items: center; justify-content: center;
    gap: 0.2rem; text-decoration: none; color: var(--oc-muted) !important;
    font-size: 0.68rem; font-weight: 500;
    padding: 0.35rem 0.15rem; border-radius: 0; line-height: 1.2;
    background: transparent !important;
    font-family: "Inter", sans-serif !important;
}}
.oc-nav a.active, .oc-nav .oc-nav-item.active {{
    background: transparent !important;
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
}}
.oc-nav .oc-ico {{ width: 1.15rem; height: 1.15rem; display: block; }}
/* Bottom nav buttons — fixed bar, icon+label, no pill chrome */
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] {{
    position: fixed !important;
    left: 0 !important; right: 0 !important; bottom: 0 !important;
    z-index: 1100 !important;
    background: #fff !important;
    border-top: 1px solid var(--oc-border) !important;
    padding: 0.45rem 0.35rem max(0.45rem, env(safe-area-inset-bottom)) !important;
    margin: 0 !important;
}}
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] div[data-testid="stHorizontalBlock"] {{
    gap: 0 !important;
}}
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] div.stButton > button,
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] button[data-testid="baseButton-secondary"],
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] button[data-testid="baseButton-primary"] {{
    background: transparent !important;
    color: var(--oc-muted) !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    outline: none !important;
    font-family: "Inter", sans-serif !important;
    font-size: 0.68rem !important;
    font-weight: 500 !important;
    min-height: 2.85rem !important;
    padding: 0.25rem 0.1rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.15rem !important;
    white-space: normal !important;
    line-height: 1.15 !important;
}}
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] button[data-testid="baseButton-primary"],
div[data-testid="element-container"]:has(.oc-nav-btns-marker) + div[data-testid="element-container"] div.stButton > button[kind="primary"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
}}
/* Fallback if :has() unavailable — still kill borders on bottom-looking buttons */
.oc-nav-btns-marker {{ display: none !important; }}
/* Domain / meal pills — ghost chip look (scoped; never style nav/lang) */
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"],
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] {{
    display: flex !important;
    justify-content: center !important;
    width: 100% !important;
}}
.oc-chip-row + div[data-testid="stPills"],
.oc-chip-row + [data-testid="stButtonGroup"],
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] div[data-testid="stPills"],
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] [data-testid="stButtonGroup"],
.oc-sec-label + div[data-testid="stPills"],
.oc-sec-label + [data-testid="stButtonGroup"],
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] div[data-testid="stPills"],
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] [data-testid="stButtonGroup"],
.st-key-home_domain_pills [data-testid="stButtonGroup"],
.st-key-meal_pills [data-testid="stButtonGroup"],
.st-key-movie_format_pills [data-testid="stButtonGroup"],
.st-key-movie_mood_pills [data-testid="stButtonGroup"],
.st-key-ambig_domain_pills [data-testid="stButtonGroup"] {{
    display: flex !important;
    flex-wrap: wrap !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 8px !important;
    margin: 0 auto 1.25rem !important;
    width: 100% !important;
    max-width: 100% !important;
}}
.oc-chip-row + div[data-testid="stPills"] button,
.oc-chip-row + [data-testid="stButtonGroup"] button,
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] div[data-testid="stPills"] button,
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] [data-testid="stButtonGroup"] button,
.oc-sec-label + div[data-testid="stPills"] button,
.oc-sec-label + [data-testid="stButtonGroup"] button,
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] div[data-testid="stPills"] button,
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] [data-testid="stButtonGroup"] button,
.st-key-home_domain_pills [data-testid="stButtonGroup"] button,
.st-key-meal_pills [data-testid="stButtonGroup"] button,
.st-key-movie_format_pills [data-testid="stButtonGroup"] button,
.st-key-movie_mood_pills [data-testid="stButtonGroup"] button,
.st-key-ambig_domain_pills [data-testid="stButtonGroup"] button {{
    background: transparent !important;
    color: var(--oc-ink) !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    padding: 8px 20px !important;
    min-height: 0 !important;
    height: auto !important;
    width: auto !important;
    flex: 0 0 auto !important;
}}
.oc-chip-row + div[data-testid="stPills"] button[aria-checked="true"],
.oc-chip-row + [data-testid="stButtonGroup"] button[aria-checked="true"],
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] div[data-testid="stPills"] button[aria-checked="true"],
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] [data-testid="stButtonGroup"] button[aria-checked="true"],
.oc-sec-label + div[data-testid="stPills"] button[aria-checked="true"],
.oc-sec-label + [data-testid="stButtonGroup"] button[aria-checked="true"],
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] div[data-testid="stPills"] button[aria-checked="true"],
div[data-testid="element-container"]:has(.oc-sec-label) + div[data-testid="element-container"] [data-testid="stButtonGroup"] button[aria-checked="true"],
.oc-chip-row + div[data-testid="stPills"] button[kind="primary"],
.oc-chip-row + [data-testid="stButtonGroup"] button[kind="primary"],
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] div[data-testid="stPills"] button[kind="primary"],
div[data-testid="element-container"]:has(.oc-chip-row) + div[data-testid="element-container"] [data-testid="stButtonGroup"] button[kind="primary"] {{
    background: transparent !important;
    border-color: var(--oc-ink) !important;
    color: var(--oc-ink) !important;
}}
/* Domain / meal pills — ghost chip look (scoped; never style nav/lang) */
.oc-chip-row {{
    display: flex !important;
    flex-wrap: wrap !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 8px !important;
    margin: 0 0 0.25rem !important;
    min-height: 0 !important;
}}
a.oc-chip {{
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    background: transparent !important;
    color: var(--oc-ink) !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    text-decoration: none !important;
    padding: 8px 20px !important;
}}
a.oc-chip:hover, a.oc-chip:focus {{
    border-color: var(--oc-ink) !important;
    color: var(--oc-ink) !important;
}}
[data-testid="stWidgetLabel"] {{ display: none !important; }}
div[data-testid="stTextInput"] [data-testid="stWidgetLabel"],
div[data-testid="stSelectbox"] [data-testid="stWidgetLabel"],
div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"],
div[data-testid="stCheckbox"] label[data-testid="stWidgetLabel"],
div[data-testid="stCheckbox"] label {{
    display: flex !important;
    visibility: visible !important;
}}
div[data-testid="stHorizontalBlock"] {{
    display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important;
}}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    min-width: 0 !important; flex: 1 1 0 !important;
}}
div[data-testid="stHorizontalBlock"] div.stButton {{
    width: 100% !important; min-height: 2.5rem !important;
}}
/* Domain chips — auto-width ghost pills (match pre-auth-fix look) */
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] {{
    display: flex !important;
    flex-wrap: wrap !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 8px !important;
    margin: 0 0 1.25rem !important;
}}
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: fit-content !important;
}}
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton {{
    width: auto !important;
}}
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button {{
    width: auto !important;
    background: transparent !important;
    color: var(--oc-ink) !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    min-height: 0 !important;
    height: auto !important;
    padding: 8px 20px !important;
}}
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button:hover {{
    border-color: var(--oc-ink) !important;
    color: var(--oc-ink) !important;
    background: transparent !important;
}}
/* Legacy oc-nav-pills / oc-lang-pills marker CSS removed — use .st-key-oc_nav_bar / .st-key-oc_lang_bar above */
/* Bottom nav — fixed bar, text only, accent on active (no pill borders) */
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] {{
    position: fixed !important;
    left: 0 !important; right: 0 !important; bottom: 0 !important;
    width: 100% !important;
    z-index: 1100 !important;
    background: #fff !important;
    border-top: 1px solid var(--oc-border) !important;
    padding: 0.55rem 0.5rem max(0.55rem, env(safe-area-inset-bottom)) !important;
    margin: 0 !important;
    gap: 0 !important;
}}
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    padding: 0 !important;
}}
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button,
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button[kind="secondary"],
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button[kind="primary"],
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-secondary"],
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"] {{
    background: transparent !important;
    color: var(--oc-muted) !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    outline: none !important;
    font-family: "Inter", sans-serif !important;
    font-size: 0.68rem !important;
    font-weight: 500 !important;
    min-height: 2.6rem !important;
    padding: 0.35rem 0.15rem !important;
}}
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button[kind="primary"],
.oc-nav-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
}}
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-secondary"],
.oc-chip-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"] {{
    width: auto !important;
    background: transparent !important;
    color: var(--oc-ink) !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    min-height: 0 !important;
    height: auto !important;
    padding: 8px 20px !important;
}}
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-secondary"],
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"] {{
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    min-height: 1.6rem !important;
    padding: 0.15rem 0.35rem !important;
    width: auto !important;
}}
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
}}
/* Language — compact SV · EN text, not oval buttons */
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] {{
    display: flex !important;
    justify-content: flex-end !important;
    gap: 0.15rem !important;
    margin: 0 0 0.35rem !important;
}}
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    flex: 0 0 auto !important;
    width: auto !important;
    min-width: fit-content !important;
}}
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton {{
    width: auto !important;
}}
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button,
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button[kind="secondary"],
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button[kind="primary"] {{
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    min-height: 1.6rem !important;
    height: auto !important;
    padding: 0.15rem 0.35rem !important;
    width: auto !important;
}}
.oc-lang-btns-marker + div[data-testid="stHorizontalBlock"] div.stButton > button[kind="primary"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
}}
/* Home domain chips — HTML flex row (kept for tests / fallback) */
.oc-chip-row {{
    display: flex !important;
    flex-wrap: wrap !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 8px !important;
    margin: 0 0 1.25rem !important;
}}
a.oc-chip {{
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    background: transparent !important;
    color: var(--oc-ink) !important;
    border: 1px solid var(--oc-border) !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-weight: 500 !important;
    font-size: 14px !important;
    line-height: 1.2 !important;
    white-space: nowrap !important;
    text-decoration: none !important;
    padding: 8px 20px !important;
}}
a.oc-chip:hover, a.oc-chip:focus {{
    border-color: var(--oc-ink) !important;
    color: var(--oc-ink) !important;
}}
/* Kill Streamlit default chrome / shadows */
[data-testid="stAppViewContainer"] * {{
    --secondary-background-color: var(--oc-bg);
    --primary-color: {ACCENT};
}}
div[data-baseweb="base-input"],
div[data-baseweb="textarea"],
div[data-baseweb="input"] {{
    box-shadow: none !important;
    background: transparent !important;
}}
/* iOS Safari: inputs <16px trigger auto-zoom that never resets */
input, textarea, select,
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {{
    font-size: 16px !important;
}}
.oc-shop-list {{
    margin: 0.5rem 0 1rem;
}}
.oc-shop-row {{
    display: flex !important;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    min-height: 3rem;
    padding: 0.85rem 1rem;
    margin: 0.35rem 0;
    border: 1px solid var(--oc-border);
    border-radius: 12px;
    background: #fff !important;
    color: var(--oc-ink) !important;
    text-decoration: none !important;
    font-size: 1rem;
    line-height: 1.3;
    box-sizing: border-box;
}}
.oc-shop-row.checked {{
    color: var(--oc-muted) !important;
    text-decoration: line-through;
    opacity: 0.72;
}}
.oc-shop-row .oc-chk {{
    width: 1.35rem;
    height: 1.35rem;
    border: 2px solid var(--oc-border);
    border-radius: 6px;
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
    line-height: 1;
}}
.oc-shop-row.checked .oc-chk {{
    border-color: var(--oc-accent);
    color: var(--oc-accent);
}}
/* Executable shopping — quiet checklist rows (indigo reserved for ONE CTA) */
.oc-shop-pick {{
    background: #fff;
    border-radius: 14px;
    border: 1px solid rgba(0, 0, 0, 0.06);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
    padding: 12px 0 8px;
    margin: 0 0 1.1rem;
    text-align: left;
    overflow: hidden;
}}
.oc-shop-pick .oc-shop-title {{
    font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600; margin: 0 16px 8px;
    font-family: "Inter", sans-serif !important;
}}
.oc-shop-pick .oc-sec-label {{
    font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600;
    margin: 14px 16px 4px;
    font-family: "Inter", sans-serif !important;
}}
.oc-shop-pick .oc-sec-label:first-of-type {{
    margin-top: 4px;
}}
.oc-shop-pick .oc-assumed {{
    margin: 10px 16px 8px; padding-top: 10px;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
    font-size: 13px; color: var(--oc-muted); line-height: 1.4;
}}
a.oc-shop-row {{
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    width: 100% !important;
    height: 44px !important;
    min-height: 44px !important;
    max-height: 44px !important;
    padding: 0 16px !important;
    margin: 0 !important;
    box-sizing: border-box !important;
    background: #fff !important;
    color: var(--oc-ink) !important;
    text-decoration: none !important;
    border: none !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
}}
a.oc-shop-row:last-of-type {{
    border-bottom: none !important;
}}
a.oc-shop-row .oc-chk {{
    flex: 0 0 22px;
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1.5px solid rgba(0, 0, 0, 0.18);
    box-sizing: border-box;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    color: transparent;
    font-size: 12px;
    line-height: 1;
}}
a.oc-shop-row.checked .oc-chk {{
    background: {ACCENT};
    border-color: {ACCENT};
    color: #fff;
}}
a.oc-shop-row .oc-shop-name {{
    flex: 1 1 auto;
    min-width: 0;
    font-size: 16px;
    font-weight: 500;
    line-height: 1.2;
    color: var(--oc-ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}}
a.oc-shop-row .oc-shop-amt {{
    flex: 0 0 auto;
    font-size: 14px;
    font-weight: 400;
    color: var(--oc-muted);
    white-space: nowrap;
}}
a.oc-shop-row .oc-shop-hint {{
    display: block;
    font-size: 12px;
    font-weight: 400;
    color: var(--oc-muted);
    line-height: 1.2;
    margin-top: 2px;
}}
a.oc-shop-row.checked {{
    opacity: 1;
}}
a.oc-shop-row.checked .oc-shop-name {{
    text-decoration: none;
    color: var(--oc-ink);
    font-weight: 500;
}}
/* Execute selection checklist — st.checkbox rows (no strikethrough) */
.st-key-exec_shop_card {{
    background: #fff !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] {{
    min-height: 44px !important;
    display: flex !important;
    align-items: center !important;
    padding: 0 8px !important;
    margin: 0 !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06) !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] label {{
    display: flex !important;
    align-items: center !important;
    gap: 12px !important;
    width: 100% !important;
    font-family: "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    color: var(--oc-ink) !important;
    line-height: 1.25 !important;
    text-decoration: none !important;
    opacity: 1 !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] label p {{
    font-size: 16px !important;
    font-weight: 500 !important;
    color: var(--oc-ink) !important;
    text-decoration: none !important;
    margin: 0 !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {{
    display: flex !important;
    visibility: visible !important;
    height: auto !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] span[data-baseweb="checkbox"] {{
    margin-right: 4px !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] span[data-baseweb="checkbox"] > div {{
    width: 22px !important;
    height: 22px !important;
    min-width: 22px !important;
    border-radius: 50% !important;
    border: 1.5px solid rgba(0, 0, 0, 0.18) !important;
    background: #fff !important;
}}
.st-key-exec_shop_card [data-testid="stCheckbox"] input:checked + div,
.st-key-exec_shop_card [data-testid="stCheckbox"] [data-checked="true"] > div,
.st-key-exec_shop_card [data-testid="stCheckbox"] span[data-baseweb="checkbox"][data-checked="true"] > div {{
    background: {ACCENT} !important;
    border-color: {ACCENT} !important;
}}
.st-key-exec_shop_card [data-testid="stHorizontalBlock"] {{
    align-items: center !important;
    margin: 0 8px 4px !important;
}}
.st-key-exec_shop_card [data-testid="stHorizontalBlock"] div.stButton > button {{
    background: transparent !important;
    color: var(--oc-muted) !important;
    border: none !important;
    box-shadow: none !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    text-decoration: underline !important;
    text-underline-offset: 2px !important;
    min-height: 28px !important;
    padding: 0.2rem 0.4rem !important;
    width: auto !important;
}}
/* Persistent Lista tab — Klart section + shared checklist chrome */
/* Streamlit bordered container used as premium shop card */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) {{
    background: #fff !important;
    border: 1px solid rgba(0, 0, 0, 0.06) !important;
    border-radius: 14px !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04) !important;
    padding: 0 0 2px !important;
    margin: 0 0 1.1rem !important;
}}
.oc-shop-pick-marker {{ display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }}
/* Kill phantom gap from hidden marker element-container (execute + lista) */
div[data-testid="element-container"]:has(.oc-shop-pick-marker) {{
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: hidden !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) .oc-shop-title {{
    font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600; margin: 8px 16px 4px;
    font-family: "Inter", sans-serif !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) .oc-assumed {{
    margin: 8px 16px 10px; padding-top: 10px;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
    font-size: 13px; color: var(--oc-muted); line-height: 1.4;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) .oc-sec-label {{
    font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--oc-muted); font-weight: 600;
    margin: 12px 16px 2px;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) .oc-sec-label:first-of-type,
.st-key-lista_shop_card .oc-sec-label:first-of-type {{
    margin-top: 4px !important;
}}
.st-key-lista_shop_card .oc-klart-label {{
    margin-top: 16px !important;
    padding-top: 10px;
    border-top: 1px solid rgba(0, 0, 0, 0.06);
}}
/* Shared checklist rows (execute + lista) — 44px, left-aligned, no link chrome */
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) [data-testid="stCheckbox"],
.st-key-lista_shop_card [data-testid="stCheckbox"],
.st-key-exec_shop_card [data-testid="stCheckbox"] {{
    min-height: 44px !important;
    margin: 0 !important;
    padding: 0 16px !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06) !important;
    display: flex !important;
    align-items: center !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) [data-testid="stCheckbox"] label,
.st-key-lista_shop_card [data-testid="stCheckbox"] label,
.st-key-exec_shop_card [data-testid="stCheckbox"] label {{
    font-family: "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    color: var(--oc-ink) !important;
    text-decoration: none !important;
    width: 100% !important;
    justify-content: flex-start !important;
}}
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) [data-testid="stCheckbox"] label[data-checked="true"] p,
.st-key-lista_shop_card [data-testid="stCheckbox"] label[data-checked="true"] p,
.st-key-lista_shop_card [data-testid="stCheckbox"]:has(input:checked) label p,
.st-key-exec_shop_card [data-testid="stCheckbox"]:has(input:checked) label p,
div[data-testid="stVerticalBlockBorderWrapper"]:has(.oc-shop-pick-marker) [data-testid="stCheckbox"]:has(input:checked) label p {{
    text-decoration: line-through !important;
    color: var(--oc-muted) !important;
    opacity: 0.5 !important;
}}
.st-key-lista_add_row {{
    margin: 0 0 12px !important;
    padding: 0 !important;
}}
.st-key-lista_add_row [data-testid="stForm"] {{
    border: none !important;
    padding: 0 !important;
}}
.st-key-lista_add_row [data-testid="stWidgetLabel"],
.st-key-lista_add_row label[data-testid="stWidgetLabel"],
.st-key-lista_add_row [data-baseweb="form-control-label"] {{
    display: none !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}}
.st-key-lista_add_row [data-testid="stHorizontalBlock"] {{
    gap: 8px !important;
    align-items: center !important;
}}
.st-key-lista_add_row [data-testid="stTextInput"] input,
.st-key-lista_add_row input {{
    min-height: 48px !important;
    height: 48px !important;
}}
.st-key-lista_add_row div.stButton > button,
.st-key-lista_add_row [data-testid="stFormSubmitButton"] button {{
    text-decoration: none !important;
    border-radius: 12px !important;
    min-height: 48px !important;
    height: 48px !important;
    border: 1px solid rgba(0, 0, 0, 0.08) !important;
    background: #fff !important;
    color: var(--oc-ink) !important;
}}
.st-key-lista_klart_hdr {{
    margin: 0 !important;
    padding: 0 !important;
}}
.st-key-lista_klart_hdr [data-testid="stHorizontalBlock"] {{
    align-items: center !important;
    gap: 8px !important;
}}
.st-key-lista_clear_done {{
    margin: 8px 0 12px !important;
    padding: 0 !important;
}}
.st-key-lista_clear_done [data-testid="stForm"] {{
    border: none !important;
    padding: 0 !important;
}}
.st-key-lista_clear_done div.stButton,
.st-key-lista_clear_done [data-testid="stFormSubmitButton"] {{
    width: 100% !important;
    margin: 0 !important;
}}
.st-key-lista_clear_done div.stButton > button,
.st-key-lista_clear_done [data-testid="stFormSubmitButton"] button,
.st-key-lista_clear_done button[data-testid="baseButton-secondary"],
.st-key-lista_clear_done button[data-testid="stBaseButton-secondary"],
.st-key-lista_clear_done button[data-testid="baseButton-primary"],
.st-key-lista_clear_done button[data-testid="stBaseButton-primary"] {{
    background: #fff !important;
    border: 1px solid rgba(0, 0, 0, 0.14) !important;
    box-shadow: none !important;
    color: var(--oc-ink) !important;
    text-decoration: none !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    min-height: 48px !important;
    height: 48px !important;
    padding: 0.65rem 1rem !important;
    justify-content: center !important;
    width: 100% !important;
    border-radius: 12px !important;
    cursor: pointer !important;
    pointer-events: auto !important;
    -webkit-tap-highlight-color: transparent !important;
    position: relative !important;
    z-index: 20 !important;
}}
/* legacy narrow-column clear btn styles kept harmless */
.st-key-lista_klart_hdr div.stButton > button,
.st-key-lista_klart_hdr button[data-testid="baseButton-secondary"],
.st-key-lista_klart_hdr button[data-testid="stBaseButton-secondary"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    text-decoration: underline !important;
    text-underline-offset: 3px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    min-height: 44px !important;
    height: auto !important;
    padding: 0.55rem 0.5rem !important;
    justify-content: flex-end !important;
    width: 100% !important;
    cursor: pointer !important;
    -webkit-tap-highlight-color: transparent !important;
}}
/* Legacy toggle markers kept for persistent lista page */
.oc-shop-tog-marker {{ display: none !important; height: 0 !important; margin: 0 !important; padding: 0 !important; }}
.oc-shop-tog-marker + div[data-testid="stHorizontalBlock"],
div[data-testid="element-container"]:has(.oc-shop-tog-marker) + div[data-testid="element-container"] {{
    margin: 0 !important;
}}
.oc-shop-tog-marker + div[data-testid="stHorizontalBlock"] div.stButton > button,
.oc-shop-tog-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-secondary"],
.oc-shop-tog-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"],
div[data-testid="element-container"]:has(.oc-shop-tog-marker) + div[data-testid="element-container"] div.stButton > button,
div[data-testid="element-container"]:has(.oc-shop-tog-marker) + div[data-testid="element-container"] button[data-testid="baseButton-secondary"],
div[data-testid="element-container"]:has(.oc-shop-tog-marker) + div[data-testid="element-container"] button[data-testid="baseButton-primary"] {{
    width: 100% !important;
    display: flex !important;
    align-items: center !important;
    justify-content: flex-start !important;
    gap: 12px !important;
    min-height: 44px !important;
    height: 44px !important;
    padding: 0 16px !important;
    margin: 0 !important;
    border: none !important;
    border-bottom: 1px solid rgba(0, 0, 0, 0.06) !important;
    border-radius: 0 !important;
    background: #fff !important;
    background-color: #fff !important;
    background-image: none !important;
    color: var(--oc-ink) !important;
    box-shadow: none !important;
    font-family: "Inter", sans-serif !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    line-height: 1.2 !important;
    text-align: left !important;
}}
.oc-shop-tog-marker + div[data-testid="stHorizontalBlock"] button[kind="primary"],
.oc-shop-tog-marker + div[data-testid="stHorizontalBlock"] button[data-testid="baseButton-primary"],
div[data-testid="element-container"]:has(.oc-shop-tog-marker) + div[data-testid="element-container"] button[kind="primary"],
div[data-testid="element-container"]:has(.oc-shop-tog-marker) + div[data-testid="element-container"] button[data-testid="baseButton-primary"] {{
    background: #fff !important;
    background-color: #fff !important;
    color: var(--oc-muted) !important;
    text-decoration: line-through !important;
    opacity: 0.5 !important;
    border-color: transparent !important;
}}
.oc-list-badge {{
    display: none;
}}
.oc-decision.oc-exec-lock {{
    position: relative;
    max-height: 160px;
    overflow: hidden;
    padding: 1rem 1.1rem 0.9rem !important;
    margin: 0 0 0.75rem !important;
}}
.oc-decision.oc-share-host {{
    position: relative;
    overflow: visible !important;
    max-height: none !important;
}}
.oc-decision.oc-exec-lock h1 {{
    font-size: 1.35rem !important;
    margin: 0.35rem 0 0.5rem !important;
    line-height: 1.15 !important;
}}
.oc-exec-meta {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem 0.75rem;
    align-items: center;
    margin: 0 0 1rem;
    font-family: "Inter", sans-serif !important;
    font-size: 14px;
    color: var(--oc-muted);
    line-height: 1.35;
}}
.oc-exec-meta .oc-nutrition {{
    margin: 0 !important;
    padding: 0 !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: var(--oc-muted) !important;
}}
.oc-recipe.oc-recipe-steps-only .oc-sec:first-of-type {{
    margin-top: 0;
}}
.st-key-exec_sticky_cta {{
    position: fixed !important;
    left: 0 !important;
    right: 0 !important;
    bottom: calc(58px + env(safe-area-inset-bottom)) !important;
    z-index: 998 !important;
    width: 100% !important;
    max-width: 420px !important;
    margin: 0 auto !important;
    padding: 10px 20px !important;
    box-sizing: border-box !important;
    background: rgba(250, 250, 247, 0.92) !important;
    backdrop-filter: blur(10px) !important;
    -webkit-backdrop-filter: blur(10px) !important;
    border-top: 1px solid rgba(0, 0, 0, 0.05) !important;
}}
.st-key-exec_sticky_cta div.stButton {{
    margin: 0 !important;
    width: 100% !important;
}}
.st-key-exec_sticky_cta .oc-list-confirm {{
    text-align: center;
    margin: 0;
    padding: 12px 8px;
    font-family: "Inter", sans-serif !important;
    font-size: 15px;
    font-weight: 500;
    color: var(--oc-ink);
}}
.st-key-exec_sticky_cta .oc-list-confirm a {{
    color: var(--oc-accent);
    text-decoration: underline;
    text-underline-offset: 3px;
}}
.block-container:has(.oc-shop-pick-marker),
.block-container:has(.st-key-exec_sticky_cta) {{
    padding-bottom: calc(160px + env(safe-area-inset-bottom)) !important;
}}
/* Final win: keyed lang/nav over any leftover chip chrome */
.st-key-oc_lang_bar button,
.st-key-oc_lang_pills button {{
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    text-decoration: none !important;
}}
.st-key-oc_lang_bar button[aria-checked="true"],
.st-key-oc_lang_pills button[aria-checked="true"] {{
    color: var(--oc-ink) !important;
    font-weight: 600 !important;
}}
/* Glass nav MUST win over global secondary/underline + any column pill chrome */
.st-key-oc_nav_bar,
.st-key-oc_nav_bar [data-testid="stHorizontalBlock"],
.st-key-oc_nav_bar [data-testid="stVerticalBlock"],
.st-key-oc_nav_bar [data-testid="stVerticalBlockBorderWrapper"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    gap: 0.15rem !important;
}}
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton,
.st-key-oc_nav_bar [class*="st-key-nav_"] {{
    margin: 0 !important;
    padding: 0 !important;
    width: 100% !important;
    background: transparent !important;
    border: none !important;
}}
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button,
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[data-testid="baseButton-secondary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[data-testid="baseButton-primary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[data-testid="stBaseButton-secondary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[data-testid="stBaseButton-primary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[kind="secondary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[kind="primary"] {{
    width: 100% !important;
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
    border-radius: 999px !important;
    box-shadow: none !important;
    color: var(--oc-muted) !important;
    font-family: "Inter", sans-serif !important;
    font-size: 11px !important;
    font-weight: 500 !important;
    min-height: 3rem !important;
    height: auto !important;
    padding: 0.3rem 0.35rem !important;
    display: flex !important;
    flex-direction: column !important;
    align-items: center !important;
    justify-content: center !important;
    gap: 0.15rem !important;
    line-height: 1.1 !important;
    text-decoration: none !important;
    text-underline-offset: unset !important;
}}
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[kind="primary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[data-testid="baseButton-primary"],
.st-key-oc_nav_bar [class*="st-key-nav_"] div.stButton > button[data-testid="stBaseButton-primary"] {{
    color: var(--oc-accent) !important;
    font-weight: 600 !important;
    background: rgba(59, 59, 196, 0.12) !important;
    background-color: rgba(59, 59, 196, 0.12) !important;
}}
/* Lista unchecked-count badge (trailing · N in label) */
.st-key-nav_lista div.stButton > button {{
    position: relative !important;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


def _is_authenticated() -> bool:
    return bool(
        st.session_state.get("access_token")
        and st.session_state.get("refresh_token")
        and st.session_state.get("user_id")
        and not st.session_state.get("guest_mode")
    )


def _apply_auth_session(sess: dict[str, Any]) -> None:
    """Mirror Supabase session into session_state + DB."""
    import auth_cookie as ac

    st.session_state.user_id = sess["user_id"]
    st.session_state.user_email = sess.get("email")
    st.session_state.access_token = sess["access_token"]
    st.session_state.refresh_token = sess["refresh_token"]
    st.session_state.guest_mode = False
    _clear_guest_query_param()
    db.set_auth(sess["access_token"], sess["refresh_token"])
    db.ensure_user(
        sess["user_id"],
        language=st.session_state.language,
        email=sess.get("email"),
    )
    ac.set_auth_cookie(sess["access_token"], sess["refresh_token"])


def _clear_auth_everywhere() -> None:
    """Logout / guest — wipe session_state, DB auth context, and cookie."""
    import auth_cookie as ac

    db.clear_auth()
    ac.clear_auth_cookie()
    for key in (
        "user_id",
        "user_email",
        "access_token",
        "refresh_token",
        "current",
        "decision_id",
    ):
        st.session_state[key] = None
    st.session_state["accepted"] = False
    st.session_state["guest_mode"] = False


def _try_restore_auth_from_cookie() -> bool:
    """
    Restore Supabase session from browser cookie after a full page reload.

    Returns True when the cookie component is still loading (caller should stop).
    """
    import auth_cookie as ac
    import supabase_client as sb

    if not sb.is_configured():
        st.session_state["_auth_cookie_checked"] = True
        return False
    if _is_authenticated():
        st.session_state["_auth_cookie_checked"] = True
        return False
    if st.session_state.get("guest_mode") or _guest_query_active():
        st.session_state["_auth_cookie_checked"] = True
        return False
    if st.session_state.get("_auth_cookie_checked"):
        return False

    stored = ac.read_auth_cookie()
    if stored is None:
        return True
    st.session_state["_auth_cookie_checked"] = True

    rt = (stored or {}).get("rt")
    if not rt:
        return False
    try:
        sess = sb.refresh_session(rt)
        _apply_auth_session(sess)
    except Exception as exc:
        log.warning("auth cookie refresh failed: %s", exc)
        ac.clear_auth_cookie()
    return False


def init_state() -> None:
    defaults: dict[str, Any] = {
        "language": "sv",
        "page": "home",
        "user_id": None,
        "user_email": None,
        "access_token": None,
        "refresh_token": None,
        "auth_mode": "login",  # login | signup
        "is_pro": False,
        "current": None,
        "decision_id": None,  # explicit mirror of current["decision_id"]
        "accepted": False,  # permanent after Handla & laga
        "shopping_checks": {},  # checkbox state keyed by decision_id:item
        "shopping_merged_for": None,  # decision_id last successfully merged into list
        "shopping_list_error": None,  # last shopping DB error (shown in UI)
        "reroll_index": 0,
        "last_question": "",
        "last_domain_hint": None,
        "guest_mode": False,
        "route_log_id": None,
        "pending_free_text": None,
        "force_route_domain": None,
        "ui_error": None,  # set by error boundary; cleared on retry
        "clothes_occasion": None,  # jobb|vardag|fest|middag|traffa|barnkalas
        "pending_clothes_question": "",
        "occasion_by_hour": {},  # remembered most-common occasion per hour bucket
        "food_meal_type": None,  # frukost|lunch|middag|kvallsmal — inferred, confirmable
        "movie_format": None,  # avsnitt|film|ny_serie
        "movie_mood": None,  # avkopplat|spanning|skratta|lar_mig|med_barnen
        "movie_in_progress_series": None,  # grounded series name for Nästa avsnitt
        "pending_db_accept": False,
        "pending_open_execute": False,
        "_last_ui_error": None,
        # Workout player (execute view)
        "workout_phase": "overview",  # overview|play|rest|done
        "workout_block_i": 0,
        "workout_set_i": 0,
        "workout_timer_end": None,  # epoch seconds
        "workout_timer_total": 0,
        "shared_token": None,
        "shared_payload": None,
        "shared_ref": None,
        # Fridge photo flow (capture → confirm → decide)
        "fridge_step": "capture",  # capture | confirm
        "fridge_inventory": [],  # [{name, confidence}]
        "fridge_photos": [],  # unused mirror; widgets hold bytes
        "fridge_mode": False,
        "shopping_list_cache": None,  # optimistic mirror of db.list_shopping_items
        "shopping_pending_writes": [],  # [{id, checked}] write-behind queue
        "_auth_cookie_checked": False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    if _try_restore_auth_from_cookie():
        return

    # Restore Supabase auth context for RLS-backed writes
    if st.session_state.access_token and st.session_state.refresh_token:
        db.set_auth(st.session_state.access_token, st.session_state.refresh_token)
    else:
        db.clear_auth()

    import supabase_client as sb

    # Public share landing is the distribution channel — no login wall
    if _peek_share_token() and not st.session_state.user_id:
        st.session_state.guest_mode = True

    # Auth gate BEFORE guest bootstrap — first view is login unless guest chosen
    if (
        sb.is_configured()
        and not _is_authenticated()
        and not st.session_state.guest_mode
        and not _guest_query_active()
    ):
        st.session_state.page = "auth"
        _clear_action_query_params()
        return

    _bootstrap_guest_session()

    # Local / guest fallback when Supabase is off (or explicit guest)
    if not st.session_state.user_id:
        db.init_db()
        st.session_state.user_id = str(uuid.uuid4())
        st.session_state.guest_mode = True
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        db.clear_auth()
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)
    elif st.session_state.guest_mode:
        db.clear_auth()


def get_secret(name: str, default: str = "") -> str:
    """Read a Streamlit secret; also searches one level of nested TOML tables."""
    try:
        raw = st.secrets.get(name, None)
        if raw is not None and not isinstance(raw, dict):
            return str(raw)
    except Exception:
        pass
    try:
        # Nested: [api] GROK_API_KEY = "..." → st.secrets["api"]["GROK_API_KEY"]
        for section in st.secrets.keys():  # type: ignore[attr-defined]
            try:
                block = st.secrets[section]
            except Exception:
                continue
            if isinstance(block, dict) and name in block:
                val = block.get(name)
                if val is not None and not isinstance(val, dict):
                    return str(val)
    except Exception:
        pass
    return default


def _normalize_secret_value(value: str) -> str:
    k = (value or "").strip()
    # Strip wrapping quotes (including curly phone-keyboard quotes)
    for _ in range(2):
        if len(k) >= 2 and k[0] == k[-1] and k[0] in "\"'“”‘’":
            k = k[1:-1].strip()
    # Common paste: Bearer xai-...
    if k.lower().startswith("bearer "):
        k = k[7:].strip()
    return k


def _usable_grok_secret(key: str) -> bool:
    k = _normalize_secret_value(key)
    if len(k) < 12:
        return False
    low = k.lower()
    if low.startswith(("din_", "your_", "sk_test", "xxx", "paste")):
        return False
    if "placeholder" in low or "your_project" in low:
        return False
    if low.endswith(("_här", "_har")) or "nyckel_här" in low:
        return False
    if low.startswith("xai-") and len(k) >= 16:
        return True
    return len(k) >= 32 and "nyckel" not in low


def _secret_leaf_map() -> dict[str, str]:
    """Flatten top-level + one-level nested secrets to {KEY: value} (strings only)."""
    out: dict[str, str] = {}
    try:
        for key in st.secrets.keys():  # type: ignore[attr-defined]
            try:
                val = st.secrets[key]
            except Exception:
                continue
            if isinstance(val, dict):
                for k2, v2 in val.items():
                    if v2 is not None and not isinstance(v2, dict):
                        out[str(k2)] = str(v2)
            elif val is not None:
                out[str(key)] = str(val)
    except Exception:
        pass
    return out


def diagnose_grok_secret() -> dict[str, Any]:
    """Safe diagnostics for fridge UI — never includes the full secret."""
    import os

    leaves = _secret_leaf_map()
    # Case-insensitive name match
    found_name = None
    found_raw = ""
    for want in ("GROK_API_KEY", "XAI_API_KEY"):
        for name, val in leaves.items():
            if name.upper() == want:
                found_name = name
                found_raw = val
                break
        if found_name:
            break
    if not found_raw:
        found_raw = (
            os.environ.get("GROK_API_KEY", "")
            or os.environ.get("XAI_API_KEY", "")
            or ""
        )
        if found_raw:
            found_name = "env"
    norm = _normalize_secret_value(found_raw)
    names = sorted(leaves.keys())
    return {
        "secret_names": names,
        "has_grok_name": any(n.upper() == "GROK_API_KEY" for n in names),
        "has_xai_name": any(n.upper() == "XAI_API_KEY" for n in names),
        "found_name": found_name,
        "len": len(norm),
        "prefix": norm[:4] if norm else "",
        "startswith_xai": norm.lower().startswith("xai-"),
        "usable": _usable_grok_secret(norm),
        "value": norm,
    }


def resolve_grok_api_key() -> str:
    """
    GROK_API_KEY or XAI_API_KEY from Streamlit secrets / env.

    Resolution lives in app.py (not only fridge_domain) so a stale Cloud
    module cache cannot AttributeError on resolve_vision_api_key.
    """
    diag = diagnose_grok_secret()
    if diag.get("usable"):
        return str(diag.get("value") or "")
    # Fall through fridge_domain helper if present
    import os

    candidates = (
        get_secret("GROK_API_KEY"),
        get_secret("XAI_API_KEY"),
        os.environ.get("GROK_API_KEY", ""),
        os.environ.get("XAI_API_KEY", ""),
        str(diag.get("value") or ""),
    )
    try:
        import fridge_domain as fr
        import importlib

        if not hasattr(fr, "resolve_vision_api_key"):
            fr = importlib.reload(fr)
        if hasattr(fr, "resolve_vision_api_key"):
            got = fr.resolve_vision_api_key(*candidates)
            if _usable_grok_secret(got):
                return got
    except Exception as exc:
        log.warning("fridge_domain key resolve unavailable: %s", exc)

    for raw in candidates:
        k = _normalize_secret_value(str(raw or ""))
        if _usable_grok_secret(k):
            return k
    return ""


def _peek_share_token() -> str | None:
    try:
        raw = st.query_params.get("share")
        if isinstance(raw, (list, tuple)):
            raw = raw[0] if raw else None
        tok = str(raw or "").strip()
        return tok or None
    except Exception:
        return None


def _app_base_url() -> str:
    return (get_secret("APP_URL") or "").rstrip("/")


def _as_dict(value: Any) -> dict[str, Any]:
    """Coerce session/DB context to a dict (Cloud may leave JSON strings)."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            import json as _json

            parsed = _json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def build_share_bundle(cur: dict[str, Any]) -> dict[str, str]:
    """Ensure public snapshot exists; return text + url for the native share sheet."""
    import share_domain as sd

    language = st.session_state.get("language", "sv")
    cur = cur if isinstance(cur, dict) else {}
    # Mirror decision_id onto payload for attribution in URL
    if cur.get("decision_id") is None and st.session_state.get("decision_id") is not None:
        cur = dict(cur)
        cur["decision_id"] = st.session_state.get("decision_id")
    # Never let nested JSON-string context break snapshot creation
    if "context" in cur:
        cur = dict(cur)
        cur["context"] = _as_dict(cur.get("context"))
    ctx = _as_dict(cur.get("context"))
    share = db.ensure_public_share(cur, language=language)
    token = str(share.get("token") or "")
    did = share.get("decision_id")
    text = sd.share_message(
        domain=str(cur.get("domain") or share.get("domain") or ""),
        suggestion=str(cur.get("suggestion") or share.get("suggestion") or ""),
        language=language,
        year=ctx.get("movie_tmdb_year"),
    )
    base = _app_base_url()
    if base:
        url = sd.absolute_share_url(base, token=token, decision_id=did)
    else:
        # Relative — JS resolves against window.location.origin
        url = sd.share_path(token=token, decision_id=did)
    return {"text": text, "url": url, "token": token}


def _session_pop(key: str, default: Any = None) -> Any:
    """session_state.pop — safe across Streamlit versions."""
    try:
        val = st.session_state[key]
    except Exception:
        return default
    try:
        del st.session_state[key]
    except Exception:
        try:
            st.session_state[key] = default
        except Exception:
            pass
    return val


def _share_icon_button_html(
    *,
    title: str,
    text: str,
    url: str = "",
    key: str,
    log_list: bool = False,
) -> str:
    """Corner share control — HTML button with sync click (preserves user gesture)."""
    import base64
    import json as _json

    safe_key = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in key)
    payload = {
        "title": title or "OneChoice",
        "text": text or "",
        "url": url or "",
        "log_list": bool(log_list),
    }
    payload_b64 = base64.b64encode(
        _json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    payload_json = _json.dumps(payload, ensure_ascii=False)
    aria = html.escape(t("share"))
    # Icon is CSS background-image (inline SVG is stripped by DOMPurify → white box).
    # Payload also registered in JS map in case data-* attrs are sanitized away.
    return (
        f'<script>(function(){{window.__ocSharePayloads=window.__ocSharePayloads||{{}};'
        f'window.__ocSharePayloads[{_json.dumps(safe_key)}]={payload_json};'
        f'}})();</script>'
        f'<span class="oc-share-corner">'
        f'<button type="button" class="oc-share-icon-btn" data-oc-share="icon" '
        f'data-oc-share-key="{html.escape(safe_key)}" data-payload="{payload_b64}" '
        f'aria-label="{aria}"></button></span>'
    )


def _oc_share_runtime_html() -> str:
    """Parent-frame JS: native share in the tap handler + transient clipboard toast."""
    import json as _json

    copied = _json.dumps(t("share_copied"), ensure_ascii=False)
    clear_list_cookie = False
    try:
        if "_clear_oc_list_shared" in st.session_state:
            clear_list_cookie = bool(st.session_state["_clear_oc_list_shared"])
            del st.session_state["_clear_oc_list_shared"]
    except Exception:
        clear_list_cookie = False
    clear_js = "true" if clear_list_cookie else "false"
    return f"""<script>
(function() {{
  if ({clear_js}) {{
    try {{ document.cookie = "oc_list_shared=; path=/; max-age=0; SameSite=Lax"; }} catch (e) {{}}
  }}
  try {{
    document.querySelectorAll("iframe").forEach(function(f) {{
      var a = f.getAttribute("allow") || "";
      if (a.indexOf("web-share") < 0) {{
        f.setAttribute("allow", a ? (a + "; web-share") : "web-share");
      }}
    }});
  }} catch (e) {{}}
  window.ocShareToast = function() {{
    try {{
      var doc = document;
      var existing = doc.getElementById("oc-share-toast");
      if (existing) existing.remove();
      var el = doc.createElement("div");
      el.id = "oc-share-toast";
      el.setAttribute("role", "status");
      el.textContent = {copied};
      el.style.cssText = "position:fixed;left:50%;bottom:5.5rem;transform:translateX(-50%);z-index:99999;background:#1a1a1a;color:#fff;padding:0.65rem 1.15rem;border-radius:999px;font:600 0.9rem Inter,system-ui,sans-serif;opacity:1;transition:opacity .35s ease;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.18);";
      doc.body.appendChild(el);
      setTimeout(function() {{
        el.style.opacity = "0";
        setTimeout(function() {{ try {{ el.remove(); }} catch (e) {{}} }}, 400);
      }}, 1500);
    }} catch (e) {{}}
  }};
  window.ocCopyShare = function(full) {{
    var done = function() {{ window.ocShareToast && window.ocShareToast(); }};
    if (navigator.clipboard && navigator.clipboard.writeText) {{
      navigator.clipboard.writeText(full || "").then(done).catch(function() {{
        try {{
          var ta = document.createElement("textarea");
          ta.value = full || "";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
        }} catch (e) {{}}
        done();
      }});
    }} else {{
      try {{
        var ta2 = document.createElement("textarea");
        ta2.value = full || "";
        document.body.appendChild(ta2);
        ta2.select();
        document.execCommand("copy");
        ta2.remove();
      }} catch (e) {{}}
      done();
    }}
  }};
  window.ocNativeShare = function(el) {{
    var payload = {{}};
    var key = el.getAttribute("data-oc-share-key") || "";
    try {{
      if (window.__ocSharePayloads && key && window.__ocSharePayloads[key]) {{
        payload = window.__ocSharePayloads[key];
      }} else {{
        payload = JSON.parse(atob(el.getAttribute("data-payload") || ""));
      }}
    }} catch (e) {{ payload = {{}}; }}
    var shareUrl = payload.url || "";
    if (shareUrl.indexOf("?") === 0) shareUrl = window.location.origin + "/" + shareUrl;
    else if (shareUrl.indexOf("/") === 0) shareUrl = window.location.origin + shareUrl;
    var full = (payload.text || "") + (shareUrl ? ("\\n" + shareUrl) : "");
    if (payload.log_list) {{
      try {{ document.cookie = "oc_list_shared=1; path=/; max-age=600; SameSite=Lax"; }} catch (e) {{}}
    }}
    if (typeof navigator.share === "function") {{
      var data = {{ title: payload.title || "OneChoice", text: payload.text || "" }};
      if (shareUrl) data.url = shareUrl;
      // Must start share inside the click stack — never after a Streamlit rerun.
      var p = navigator.share(data);
      if (p && p.catch) {{
        p.catch(function(err) {{
          if (err && err.name === "AbortError") return;
          window.ocCopyShare(full);
        }});
      }}
      return false;
    }}
    window.ocCopyShare(full);
    return false;
  }};
  if (!window.__ocShareClickBound) {{
    window.__ocShareClickBound = true;
    document.addEventListener("click", function(e) {{
      var t = e.target;
      if (!t || !t.closest) return;
      var el = t.closest("[data-oc-share=\\"icon\\"]");
      if (!el) return;
      e.preventDefault();
      e.stopPropagation();
      if (window.ocNativeShare) window.ocNativeShare(el);
    }}, true);
  }}
}})();
</script>"""


def _paint_html(body: str) -> None:
    """Render interactive HTML in the parent document (not an iframe)."""
    try:
        st.html(
            _oc_share_runtime_html() + (body or ""),
            unsafe_allow_javascript=True,
        )
    except TypeError:
        # Older Streamlit without unsafe_allow_javascript
        st.html(_oc_share_runtime_html() + (body or ""))
    except Exception:
        # Last resort — markdown strips handlers; still show static corner if present
        try:
            st.markdown(body or "", unsafe_allow_html=True)
        except Exception:
            pass


def decision_share_button_html(cur: dict[str, Any], *, key: str) -> str:
    """Eagerly build public snapshot + return corner icon HTML (no Streamlit button)."""
    try:
        bundle = build_share_bundle(cur if isinstance(cur, dict) else {})
        return _share_icon_button_html(
            title="OneChoice",
            text=str(bundle.get("text") or ""),
            url=str(bundle.get("url") or ""),
            key=key,
        )
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("share button html failed: %s", exc)
        return ""


def _safe_decision_share_button_html(cur: dict[str, Any], *, key: str) -> str:
    try:
        return decision_share_button_html(cur, key=key)
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("share render failed: %s", exc)
        return ""


def render_share(
    *,
    title: str,
    text: str,
    url: str = "",
    key: str,
    label: str | None = None,
    icon: bool = False,
    on_shared: Any = None,
    log_list: bool = False,
    wrap_class: str = "",
) -> None:
    """Universal share icon — native sheet on iOS, clipboard toast elsewhere."""
    del label, icon  # canonical control is icon-only
    btn = _share_icon_button_html(
        title=title,
        text=text,
        url=url,
        key=key,
        log_list=log_list,
    )
    if wrap_class:
        btn = f'<div class="{html.escape(wrap_class)}">{btn}</div>'
    if callable(on_shared) and not log_list:
        # Python hooks cannot run inside the native gesture; list uses cookie drain.
        pass
    _paint_html(btn)


def render_share_for_decision(
    cur: dict[str, Any], *, key: str, icon: bool = False
) -> None:
    """Paint a standalone share icon (execute headers that aren't full cards)."""
    del icon
    html_btn = _safe_decision_share_button_html(cur, key=key)
    if not html_btn:
        return
    # Absolute corner needs a relative host — minimal shell when not embedded in a card
    _paint_html(
        f'<div class="oc-decision oc-share-host" style="padding:0;margin:0 0 0.35rem;'
        f'min-height:40px;border:none;background:transparent;box-shadow:none;">'
        f"{html_btn}</div>"
    )


def _safe_render_share_for_decision(
    cur: dict[str, Any], *, key: str, icon: bool = False
) -> None:
    """Outer guard so a broken share never takes down Handla / execute / result."""
    try:
        render_share_for_decision(cur, key=key, icon=icon)
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("share render failed: %s", exc)


def _drain_list_share_cookie() -> None:
    """Lista share logging — cookie set in the tap handler, drained on next run."""
    try:
        cookies = getattr(st.context, "cookies", None)
        raw = cookies.get("oc_list_shared") if cookies is not None else None
    except Exception:
        raw = None
    if not raw:
        return
    st.session_state["_clear_oc_list_shared"] = True
    try:
        uid = st.session_state["user_id"]
    except Exception:
        uid = None
    if not uid:
        return
    try:
        n = db.record_list_share(str(uid))
        st.session_state["list_share_count"] = n
    except Exception as exc:
        log.warning("list share counter failed: %s", exc)


def render_share_list() -> None:
    """Lista tab — share unchecked items as Messenger/SMS-ready plain text."""
    import share_domain as sd

    _drain_list_share_cookie()
    language = st.session_state.get("language", "sv")
    try:
        items = _load_shopping_items()
    except Exception:
        items = []
    unchecked = [r for r in items if isinstance(r, dict) and not bool(r.get("checked"))]
    if not unchecked:
        return

    text = sd.format_list_share_text(items, language=language)
    render_share(
        title="OneChoice",
        text=text,
        url="",
        key="lista_share",
        log_list=True,
        wrap_class="oc-share-lista-wrap",
    )


def require_auth_context() -> None:
    if st.session_state.access_token and st.session_state.refresh_token:
        db.set_auth(st.session_state.access_token, st.session_state.refresh_token)


def _go_to_auth_page(*, mode: str = "login") -> None:
    """Clear guest session and open login — used from Profil."""
    _clear_auth_everywhere()
    st.session_state["auth_mode"] = mode
    _clear_guest_query_param()
    _clear_action_query_params()
    st.session_state["page"] = "auth"


def page_auth() -> None:
    _clear_action_query_params()
    render_top_chrome()
    # No vendor / infra eyebrow on the login surface

    import supabase_client as sb

    if not sb.is_configured():
        st.warning(t("no_supabase"))
        if st.button(t("guest"), type="primary", use_container_width=True):
            import auth_cookie as ac

            ac.clear_auth_cookie()
            db.init_db()
            st.session_state.guest_mode = True
            st.session_state.user_id = str(uuid.uuid4())
            db.ensure_user(st.session_state.user_id, language=st.session_state.language)
            st.session_state.access_token = None
            st.session_state.refresh_token = None
            db.clear_auth()
            _set_guest_query_param()
            st.session_state.page = "home"
            st.rerun()
        return

    mode = st.session_state.auth_mode
    title = t("login_title") if mode == "login" else t("signup_title")
    st.markdown(
        f'<div class="oc-decision"><h1 style="font-size:1.4rem">{html.escape(title)}</h1></div>',
        unsafe_allow_html=True,
    )

    email = st.text_input(t("email"), key="auth_email")
    password = st.text_input(t("password"), type="password", key="auth_password")

    if mode == "login":
        if st.button(t("login_cta"), type="primary", use_container_width=True):
            try:
                with st.spinner(t("loading")):
                    sess = sb.sign_in(email.strip(), password)
                    _apply_auth_session(sess)
                st.session_state.page = "home"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if st.button(t("signup_title"), use_container_width=True):
            st.session_state.auth_mode = "signup"
            st.rerun()
    else:
        import gdpr as gdpr_mod

        privacy_url = gdpr_mod.privacy_policy_url() or "?privacy=1"
        st.markdown(
            f'<p style="font-size:0.9rem;margin:0.4rem 0">'
            f'<a href="{html.escape(privacy_url)}" target="_blank" rel="noopener">'
            f'{html.escape(t("privacy_link"))}</a></p>',
            unsafe_allow_html=True,
        )
        consent = st.checkbox(t("privacy_consent"), key="signup_privacy_consent")
        if st.button(t("signup_cta"), type="primary", use_container_width=True):
            if not consent:
                st.error(t("privacy_consent_required"))
            else:
                try:
                    sess = sb.sign_up(
                        email.strip(), password, language=st.session_state.language
                    )
                    if sess.get("access_token") and sess.get("refresh_token"):
                        _apply_auth_session(sess)
                        st.session_state.page = "home"
                        st.success("Konto skapat.")
                        st.rerun()
                    else:
                        st.info(
                            "Konto skapat. Bekräfta e-post om det krävs, sedan logga in."
                        )
                        st.session_state.auth_mode = "login"
                except Exception as exc:
                    st.error(str(exc))
        if st.button(t("login_title"), use_container_width=True):
            st.session_state.auth_mode = "login"
            st.rerun()

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    if st.button(t("guest"), use_container_width=True):
        import auth_cookie as ac

        ac.clear_auth_cookie()
        db.clear_auth()
        db.init_db()
        st.session_state.guest_mode = True
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.user_id = str(uuid.uuid4())
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)
        _set_guest_query_param()
        st.session_state.page = "home"
        st.rerun()


def _clear_action_query_params() -> None:
    """Drop ?domain= / ?nav= params that cause reload loops after auth loss."""
    for key in ("domain", "pick", "nav", "shop_toggle", "shop_check", "occasion", "meal", "lang"):
        try:
            del st.query_params[key]
        except Exception:
            pass


def lang_bar() -> None:
    """Compact SV · EN — session-safe pills in keyed fixed top-right container."""
    lang = st.session_state.language
    if lang not in ("sv", "en"):
        lang = "sv"
        st.session_state.language = lang

    mirrored = st.session_state.get("_oc_lang_mirror")
    pending = st.session_state.get("oc_lang_pills")
    if mirrored is None:
        st.session_state.oc_lang_pills = lang
        st.session_state._oc_lang_mirror = lang
    elif mirrored != lang:
        st.session_state.oc_lang_pills = lang
        st.session_state._oc_lang_mirror = lang
    elif pending in ("sv", "en") and pending != lang:
        st.session_state.language = pending
        st.session_state._oc_lang_mirror = pending
        if st.session_state.user_id and not st.session_state.get("guest_mode"):
            try:
                db.update_user(st.session_state.user_id, language=pending)
            except Exception:
                pass
        st.rerun()
        return

    with st.container(key="oc_lang_bar", horizontal=True, horizontal_alignment="right"):
        st.pills(
            "lang",
            options=["sv", "en"],
            format_func=lambda x: "SV" if x == "sv" else "EN",
            selection_mode="single",
            key="oc_lang_pills",
            label_visibility="collapsed",
            width="content",
        )


def _unchecked_shopping_count() -> int:
    """Unchecked items on the persistent list — drives Lista nav badge."""
    try:
        items = _load_shopping_items()
    except Exception:
        return 0
    return sum(1 for r in items if not bool(r.get("checked")))


def _resume_decision_page() -> str | None:
    """If a locked decision is in play, return execute/result — never the home chooser."""
    cur = st.session_state.get("current")
    if not isinstance(cur, dict) or not cur.get("suggestion"):
        return None
    accepted = bool(
        st.session_state.get("accepted")
        or cur.get("accepted")
        or cur.get("locked")
    )
    if not accepted:
        return None
    domain = (cur.get("domain") or "").strip()
    if (
        _is_food_cook(cur)
        or domain == "workout"
        or cur.get("execution_type") == "workout"
    ):
        return "execute"
    return "result"


def _go_home_chooser() -> None:
    """Explicit start-over — show Mat/Kläder chooser, don't resume the last lock."""
    _clear_fridge_session()
    st.session_state["_force_home_chooser"] = True
    st.session_state.page = "home"
    st.rerun()


def nav() -> None:
    """Fixed bottom glass nav — ONE shared component; no view may restyle it."""
    page = st.session_state.page
    highlight = "home" if page in ("home", "result", "execute", "fridge", "ambiguous") else page
    options = ("home", "lista", "history", "profile")
    if highlight not in options:
        highlight = "home"
    unchecked = _unchecked_shopping_count() if highlight != "auth" else 0
    labels = {
        "home": t("home"),
        "lista": (
            f"{t('list_nav')} · {unchecked}" if unchecked > 0 else t("list_nav")
        ),
        "history": t("history"),
        "profile": t("profile"),
    }

    with st.container(key="oc_nav_bar"):
        # Marker so AppTest can assert identical nav chrome across pages
        st.markdown(
            '<div class="oc-nav-chrome" data-oc-nav="glass" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(len(options), gap="small")
        for col, key in zip(cols, options):
            with col:
                is_active = highlight == key
                if st.button(
                    labels[key],
                    key=f"nav_{key}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    if key == "home":
                        # Always the domain chooser — never resume execute/result.
                        _go_home_chooser()
                        return
                    st.session_state.page = {
                        "lista": "lista",
                        "history": "history",
                        "profile": "profile",
                    }[key]
                    st.rerun()


def _start_domain_decision(domain: str) -> None:
    """Start a domain chip decision without ?domain= navigation (keeps auth session)."""
    if domain == "clothes":
        st.session_state.last_domain_hint = "clothes"
        st.session_state.pending_clothes_question = pipeline._default_question(
            "clothes", st.session_state.get("language", "sv")
        )
        st.session_state.clothes_occasion = None
        st.session_state.page = "clothes_occasion"
        st.rerun()
        return
    if domain == "food":
        import food_domain as fd

        if st.session_state.get("food_meal_type") not in fd.MEAL_TYPES:
            st.session_state.food_meal_type = fd.default_meal_type()
    if domain == "movie":
        _ensure_movie_chips_defaults()
    run_decision(question="", domain_hint=domain, reroll=False, via_router=False)


def _pick_ambiguous_domain(pick: str) -> None:
    pending = st.session_state.pending_free_text or st.session_state.last_question or ""
    st.session_state.force_route_domain = pick
    st.session_state.last_domain_hint = pick
    st.session_state.pending_free_text = None
    if pick == "clothes":
        st.session_state.pending_clothes_question = pending
        st.session_state.clothes_occasion = None
        st.session_state.page = "clothes_occasion"
        st.rerun()
        return
    run_decision(
        question=pending,
        domain_hint=pick,
        reroll=False,
        via_router=True,
    )


def render_domain_chips(*, key_prefix: str = "home") -> None:
    """Ghost domain chips via st.pills — original chip look, keeps login session."""
    domains = ("food", "clothes", "movie", "workout", "weekend")
    labels = " · ".join(domain_label(d) for d in domains)
    st.markdown(
        f'<div class="oc-chip-row" aria-label="{html.escape(labels)}"></div>',
        unsafe_allow_html=True,
    )
    pill_key = f"{key_prefix}_domain_pills"
    if st.session_state.get("_clear_domain_pills"):
        st.session_state.pop(pill_key, None)
        st.session_state.pop(f"_{pill_key}_prev", None)
        st.session_state._clear_domain_pills = False

    choice = st.pills(
        "domain_chips",
        options=list(domains),
        format_func=lambda d: domain_label(d),
        selection_mode="single",
        key=pill_key,
        label_visibility="collapsed",
    )
    prev = st.session_state.get(f"_{pill_key}_prev")
    if choice and choice != prev:
        st.session_state[f"_{pill_key}_prev"] = choice
        st.session_state._clear_domain_pills = True
        _start_domain_decision(str(choice))


_DOMAIN_CARD_ICONS: dict[str, str] = {
    "food": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 11h16"/>'
        '<path d="M7 11V9a5 5 0 0 1 10 0v2"/>'
        '<path d="M6 15c0 2.5 2.7 4 6 4s6-1.5 6-4"/>'
        '<path d="M3 3v5"/><path d="M3 5.5h2"/>'
        '<path d="M21 3v5"/><path d="M19 5.5h2"/>'
        "</svg>"
    ),
    "clothes": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M12 6a2 2 0 1 0-2 2"/>'
        '<path d="M4 9l8-4 8 4"/>'
        '<path d="M6 9v10h12V9"/>'
        "</svg>"
    ),
    "movie": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="m10 8 6 4-6 4V8z"/>'
        "</svg>"
    ),
    "workout": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 10h3v4H4z"/>'
        '<path d="M17 10h3v4h-3z"/>'
        '<path d="M7 12h10"/>'
        "</svg>"
    ),
    "weekend": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<circle cx="12" cy="12" r="9"/>'
        '<path d="m16 8-4 8-4-8 8 4 8-4z"/>'
        "</svg>"
    ),
    "fridge": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round" aria-hidden="true">'
        '<path d="M4 8h3l2-2h6l2 2h3v10H4z"/>'
        '<circle cx="12" cy="13" r="3"/>'
        "</svg>"
    ),
}


def _stockholm_now() -> datetime:
    """Sweden-local clock for home hero (avoid hard dependency on food_domain.local_now)."""
    return datetime.now(APP_LOCAL_TZ)


def infer_home_hero(
    now: datetime | None = None,
    *,
    language: str = "sv",
) -> dict[str, Any]:
    """Infer proactive home headline from local clock (meal windows + weekend alt)."""
    import food_domain as fd

    if now is None:
        local_fn = getattr(fd, "local_now", None)
        now = local_fn() if callable(local_fn) else _stockholm_now()
    meal_type = fd.default_meal_type(now=now)
    meal_name = fd.meal_label(meal_type, language)
    weekend_label = I18N.get(language, I18N["sv"])["domains"]["weekend"]
    is_weekend = now.weekday() >= 5
    return {
        "headline": f"{meal_name}?",
        "domain": "food",
        "meal_type": meal_type,
        "weekend_alternate": is_weekend,
        "weekend_headline": f"{weekend_label}?",
    }


def _run_inferred_home_decision(inferred: dict[str, Any]) -> None:
    import food_domain as fd

    domain = str(inferred.get("domain") or "food")
    if domain == "food":
        meal = inferred.get("meal_type")
        if meal in fd.MEAL_TYPES:
            st.session_state.food_meal_type = meal
        run_decision(question="", domain_hint="food", reroll=False, via_router=False)
        return
    if domain == "weekend":
        run_decision(question="", domain_hint="weekend", reroll=False, via_router=False)


def _start_fridge_flow() -> None:
    """Open fridge capture — session-safe (no ?fridge= navigation)."""
    st.session_state.fridge_step = "capture"
    st.session_state.fridge_inventory = []
    st.session_state.fridge_mode = False
    st.session_state.page = "fridge"
    st.rerun()


def render_home_hero(inferred: dict[str, Any]) -> None:
    headline = html.escape(str(inferred.get("headline") or ""))
    st.markdown(
        '<div class="oc-hero-orb" aria-hidden="true"></div>'
        f'<div class="oc-hero">'
        f'<div class="oc-hero-title" role="heading" aria-level="1">{headline}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    if st.button(
        t("decide"),
        key="home_hero_cta",
        type="primary",
        use_container_width=True,
    ):
        _run_inferred_home_decision(inferred)


def render_home_domain_grid() -> None:
    """Secondary tier — compact icon cards in a 2-column grid (session-safe buttons)."""
    domains = ("food", "clothes", "movie", "workout", "weekend")
    entries: list[tuple[str, str, str]] = [
        (d, domain_label(d), _DOMAIN_CARD_ICONS.get(d, "")) for d in domains
    ]
    entries.append(
        ("fridge", t("home_fridge_card"), _DOMAIN_CARD_ICONS.get("fridge", ""))
    )
    with st.container(key="home_domains"):
        st.markdown(
            f'<div class="oc-section-label">{html.escape(t("home_or_choose"))}</div>',
            unsafe_allow_html=True,
        )
        for i in range(0, len(entries), 2):
            cols = st.columns(2, gap="small")
            for j in range(2):
                idx = i + j
                if idx >= len(entries):
                    break
                domain, label, _icon = entries[idx]
                with cols[j]:
                    if st.button(
                        label,
                        key=f"home_domain_{domain}",
                        use_container_width=True,
                    ):
                        if domain == "fridge":
                            _start_fridge_flow()
                        else:
                            _start_domain_decision(domain)


def render_logo() -> None:
    """Solid black wordmark — fixed top chrome (premium app pattern)."""
    render_top_chrome()


def render_tagline(text: str | None = None) -> None:
    """Secondary grey tagline; closing period in accent indigo."""
    raw = text if text is not None else t("tagline")
    if raw.endswith("."):
        body = html.escape(raw[:-1])
        line = f'{body}<span class="oc-tag-dot">.</span>'
    else:
        line = html.escape(raw)
    st.markdown(f'<p class="oc-tagline">{line}</p>', unsafe_allow_html=True)


def render_reroll_dots(reroll_index: int) -> None:
    """Three dots that fade as rerolls are used — not a game counter."""
    dots = []
    for i in range(pipeline.MAX_REROLLS):
        cls = "used" if i < reroll_index else ""
        dots.append(f'<i class="{cls}"></i>')
    st.markdown(
        f'<div class="oc-rerolls" aria-label="{html.escape(t("rerolls_left").format(n=max(0, pipeline.MAX_REROLLS - reroll_index)))}">'
        f'{"".join(dots)}</div>',
        unsafe_allow_html=True,
    )


def render_shopping_card(shop: dict[str, Any] | None, language: str) -> None:
    if not shop or not isinstance(shop, dict):
        return
    to_buy = shop.get("to_buy") or {}
    if not to_buy:
        return
    import shopping as shopping_mod

    sections = []
    title = "Inköpslista" if language == "sv" else "Shopping list"
    # Never brand a single chain — items are available at major Swedish chains
    sections.append(f'<div class="oc-shop-title">{html.escape(title)}</div>')
    for section, items in to_buy.items():
        if not items:
            continue
        sections.append(f'<div class="oc-sec">{html.escape(section)}</div><ul>')
        for item in items:
            sections.append(f"<li>{html.escape(str(item))}</li>")
        sections.append("</ul>")
    assumed = shop.get("assumed_at_home") or ["salt", "peppar", "olja"]
    assumed_line = shopping_mod.format_assumed_line(list(assumed), language=language)
    sections.append(f'<p class="oc-assumed">{html.escape(assumed_line)}</p>')
    st.markdown(
        f'<div class="oc-shop">{"".join(sections)}</div>',
        unsafe_allow_html=True,
    )


def _safe_decide(user_id: str, question: str, **kwargs: Any):
    """Call pipeline.decide with only kwargs the installed signature accepts.

    Protects against Streamlit Cloud rolling deploys where app.py and
    pipeline.py briefly disagree on keyword arguments.
    """
    import inspect

    params = inspect.signature(pipeline.decide).parameters
    filtered = {k: v for k, v in kwargs.items() if k in params}
    return pipeline.decide(user_id, question, **filtered)


def run_decision(*, question: str, domain_hint: str | None, reroll: bool, via_router: bool = False) -> None:
    """
    via_router=True: free-text path — MUST go through handle_free_text (no bypass).
    Domain chips / ambiguous picks use via_router=False with an explicit domain_hint.
    """
    import router as rt

    require_auth_context()
    # Guest mode must never hit Supabase RLS writes
    if st.session_state.get("guest_mode"):
        db.clear_auth()
        st.session_state.access_token = None
        st.session_state.refresh_token = None

    if not st.session_state.user_id:
        db.init_db()
        st.session_state.user_id = str(uuid.uuid4())
        st.session_state.guest_mode = True
        db.clear_auth()
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)

    if reroll:
        st.session_state.reroll_index = int(st.session_state.reroll_index or 0) + 1
    else:
        st.session_state.reroll_index = 0
        st.session_state.last_question = question or ""
        st.session_state.last_domain_hint = domain_hint

    q = (st.session_state.last_question or question or "").strip()
    if len(q) > rt.MAX_INPUT_CHARS:
        q = q[: rt.MAX_INPUT_CHARS]
        st.session_state.last_question = q

    hint = st.session_state.last_domain_hint or domain_hint
    if not q and hint and hint != "other":
        q = pipeline._default_question(str(hint), st.session_state.language)
        st.session_state.last_question = q

    # Clothes always need occasion first ("Vart ska du?")
    if (
        not reroll
        and (hint == "clothes" or st.session_state.get("force_route_domain") == "clothes")
        and not st.session_state.get("clothes_occasion")
    ):
        st.session_state.pending_clothes_question = q
        st.session_state.last_domain_hint = "clothes"
        st.session_state.page = "clothes_occasion"
        st.rerun()
        return

    prev_id = None
    cur = st.session_state.current
    if reroll and isinstance(cur, dict):
        prev_id = cur.get("decision_id")

    context_extra: dict[str, Any] = {}
    if st.session_state.get("clothes_occasion"):
        context_extra["occasion"] = st.session_state.clothes_occasion
        context_extra["intent"] = "wear"
    import food_domain as fd

    if st.session_state.get("food_meal_type") not in fd.MEAL_TYPES:
        st.session_state.food_meal_type = fd.default_meal_type()
    # Pass inferred/override meal type into food decisions (confirmable chips on result)
    context_extra["meal_type"] = st.session_state.food_meal_type
    if hint == "movie" or st.session_state.get("force_route_domain") == "movie" or (
        isinstance(st.session_state.get("last_domain_hint"), str)
        and st.session_state.last_domain_hint == "movie"
    ):
        _ensure_movie_chips_defaults()
        import movie_domain as md

        context_extra["format"] = md.normalize_format(st.session_state.get("movie_format"))
        context_extra["mood"] = md.normalize_mood(st.session_state.get("movie_mood"))
        if st.session_state.get("movie_in_progress_series"):
            context_extra["in_progress_series"] = st.session_state.movie_in_progress_series
    if reroll and isinstance(cur, dict) and cur.get("suggestion"):
        context_extra["previous_suggestion"] = str(cur.get("suggestion") or "")
    if st.session_state.get("fridge_mode"):
        import fridge_domain as fr

        context_extra["source"] = fr.SOURCE
        context_extra["available_ingredients"] = fr.names_only(
            st.session_state.get("fridge_inventory") or []
        )

    try:
        meal = str(st.session_state.get("food_meal_type") or "")
        spin = t("deciding") if meal in ("lunch", "middag") else t("loading")
        with st.spinner(spin):
            if via_router and not reroll:
                result = pipeline.handle_free_text(
                    str(st.session_state.user_id),
                    q,
                    language=st.session_state.language,
                    grok_api_key=get_secret("GROK_API_KEY"),
                    forced_domain=st.session_state.force_route_domain,
                    context_extra=context_extra or None,
                )
                st.session_state.force_route_domain = None
            elif via_router and reroll:
                result = pipeline.handle_free_text(
                    str(st.session_state.user_id),
                    q,
                    language=st.session_state.language,
                    grok_api_key=get_secret("GROK_API_KEY"),
                    reroll=True,
                    reroll_index=int(st.session_state.reroll_index or 0),
                    previous_decision_id=prev_id,
                    forced_domain=str(hint) if hint else None,
                    prior_route_log_id=st.session_state.route_log_id,
                    context_extra=context_extra or None,
                )
            else:
                result = _safe_decide(
                    str(st.session_state.user_id),
                    q,
                    domain_hint=str(hint) if hint else None,
                    language=st.session_state.language,
                    reroll=reroll,
                    reroll_index=int(st.session_state.reroll_index or 0),
                    previous_decision_id=prev_id,
                    grok_api_key=get_secret("GROK_API_KEY"),
                    skip_feasibility=(str(hint) == "other"),
                    context_extra=context_extra or None,
                )
        # Free-text may land on clothes without occasion — gate before showing
        if (
            getattr(result, "ok", False)
            and getattr(result, "domain", None) == "clothes"
            and not st.session_state.get("clothes_occasion")
            and not reroll
        ):
            st.session_state.pending_clothes_question = q
            st.session_state.last_domain_hint = "clothes"
            st.session_state.page = "clothes_occasion"
            st.rerun()
            return

        st.session_state.route_log_id = getattr(result, "route_log_id", None)
        st.session_state.current = result.to_dict()
        st.session_state.decision_id = getattr(result, "decision_id", None)
        st.session_state.accepted = False
        # Clear one-shot occasion after a successful clothes decision
        if getattr(result, "domain", None) == "clothes":
            pass  # keep occasion for justification / rerolls this session
        if result.ok and result.domain:
            st.session_state.last_domain_hint = result.domain
    except Exception as exc:
        log.exception("decide failed: %s", exc)
        st.session_state.ui_error = True
        st.rerun()
        return

    if getattr(result, "needs_domain_pick", False):
        st.session_state.pending_free_text = q
        st.session_state.page = "ambiguous"
        st.rerun()
        return

    if getattr(result, "ui_message", None) and not result.ok and not result.refused:
        st.session_state.page = "not_a_decision"
        st.rerun()
        return

    st.session_state.page = "result"
    st.rerun()


def _active_decision_id(cur: dict[str, Any] | None = None) -> int | None:
    """Resolve decision_id from session + current payload (never assume set)."""
    cur = cur if isinstance(cur, dict) else (st.session_state.get("current") or {})
    raw = st.session_state.get("decision_id")
    if raw is None:
        raw = cur.get("decision_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        # Non-int ids (should not happen with bigint) — keep raw usable via session only
        return None


def _is_food_cook(cur: dict[str, Any]) -> bool:
    """Home-cooking food decision (not eat-out map link)."""
    if (cur.get("domain") or "") != "food":
        return False
    if cur.get("execution_type") == "map" or cur.get("execution_url"):
        return False
    return True


def _is_streamlit_control_flow(exc: BaseException) -> bool:
    """st.rerun() / st.stop() must never be swallowed by the error boundary."""
    name = type(exc).__name__
    # Broad match — Cloud Streamlit versions rename/move these classes
    if "Rerun" in name or name in ("StopException", "StopException"):
        return True
    if name.startswith("Stop"):
        return True
    mod = getattr(type(exc), "__module__", "") or ""
    if "scriptrunner" in mod and ("Rerun" in name or "Stop" in name):
        return True
    try:
        from streamlit.runtime.scriptrunner import RerunException, StopException

        if isinstance(exc, (RerunException, StopException)):
            return True
    except Exception:
        pass
    try:
        from streamlit.runtime.scriptrunner_utils.exceptions import (
            RerunException as RE2,
            StopException as SE2,
        )

        if isinstance(exc, (RE2, SE2)):
            return True
    except Exception:
        pass
    return False


def safe_toast(message: str) -> None:
    """st.toast needs Streamlit >=1.33 — older Cloud pins must not crash accept."""
    toast = getattr(st, "toast", None)
    if callable(toast):
        try:
            toast(message)
            return
        except Exception as exc:
            log.warning("st.toast failed: %s", exc)
    # Fallback: quiet success, never raise
    st.caption(message)


def accept_current_decision(cur: dict[str, Any] | None = None) -> bool:
    """
    Shared accept for ALL domains (food / clothes / movie / workout / weekend).

    - Never raises into the Streamlit render loop (root cause of stacked error card)
    - Guest mode always clears Supabase auth so we hit local SQLite consistently
    - Mirrors accepted/locked into session_state even if DB write soft-fails
    Returns True when the decision is now accepted in session.
    """
    cur = cur if isinstance(cur, dict) else (st.session_state.get("current") or {})
    if not isinstance(cur, dict):
        cur = {}

    try:
        require_auth_context()
        if st.session_state.get("guest_mode"):
            db.clear_auth()
            st.session_state.access_token = None
            st.session_state.refresh_token = None

        if st.session_state.get("accepted") or cur.get("accepted"):
            return True

        did = _active_decision_id(cur)
        raw_id = did if did is not None else cur.get("decision_id") or st.session_state.get(
            "decision_id"
        )
        route_log_id = cur.get("route_log_id") or st.session_state.get("route_log_id")

        pipeline.try_accept_decision(did, route_log_id=route_log_id)

        st.session_state.accepted = True
        if raw_id is not None:
            st.session_state.decision_id = raw_id
        updated = dict(cur)
        updated["locked"] = True
        updated["accepted"] = True
        if raw_id is not None:
            updated["decision_id"] = raw_id
        st.session_state.current = updated
        return True
    except Exception as exc:
        # Last-resort soft-lock — Starta passet / Bygg outfit must never crash UI
        log.exception("accept_current_decision soft-failed: %s", exc)
        st.session_state.accepted = True
        updated = dict(cur)
        updated["locked"] = True
        updated["accepted"] = True
        st.session_state.current = updated
        return True


def _lock_current_locally(cur: dict[str, Any] | None = None) -> dict[str, Any]:
    """Immediate UI lock — never waits on network/DB."""
    cur = cur if isinstance(cur, dict) else (st.session_state.get("current") or {})
    if not isinstance(cur, dict):
        cur = {}
    updated = dict(cur)
    # Heal Cloud/Supabase JSON-string context before any .get() downstream
    updated["context"] = _as_dict(updated.get("context"))
    updated["locked"] = True
    updated["accepted"] = True
    st.session_state.accepted = True
    if updated.get("decision_id") is not None:
        st.session_state.decision_id = updated.get("decision_id")
    st.session_state.current = updated
    return updated


def _ensure_workout_in_session(cur: dict[str, Any]) -> dict[str, Any]:
    """Make sure context.workout exists before opening the player."""
    try:
        import workout_domain as wd

        language = st.session_state.get("language", "sv")
        w = wd.get_workout_from_decision(cur)
        if not w:
            w = wd.finalize_workout(
                wd._match_template(str(cur.get("suggestion") or ""), language),
                language=language,
            )
        updated = dict(cur)
        ctx = _as_dict(updated.get("context"))
        ctx["workout"] = w
        ctx["execution_detail"] = wd.detail_from_workout(w, language)
        updated["context"] = ctx
        updated["domain"] = updated.get("domain") or "workout"
        updated["execution_type"] = "workout"
        updated["execution_label"] = updated.get("execution_label") or (
            "Starta passet" if language == "sv" else "Start workout"
        )
        st.session_state.current = updated
        return updated
    except Exception as exc:
        log.exception("ensure workout structure failed: %s", exc)
        return cur if isinstance(cur, dict) else {}


def _reset_workout_player() -> None:
    st.session_state.workout_phase = "overview"
    st.session_state.workout_block_i = 0
    st.session_state.workout_set_i = 0
    st.session_state.workout_timer_end = None
    st.session_state.workout_timer_total = 0


def _prepare_execute_local(cur: dict[str, Any] | None = None) -> None:
    """
    Fast local prep for execute — NO network, NO st.rerun().

    Safe for Streamlit on_click (runs before script body on Cloud).
    DB accept is deferred via pending_db_accept.
    """
    cur = cur if isinstance(cur, dict) else (st.session_state.get("current") or {})
    if not isinstance(cur, dict):
        cur = {}
    domain = (cur.get("domain") or "").strip()
    is_workout = domain == "workout" or cur.get("execution_type") == "workout"

    updated = _lock_current_locally(cur)
    if is_workout:
        _reset_workout_player()
        _ensure_workout_in_session(updated)

    st.session_state.page = "execute"
    st.session_state.ui_error = None
    st.session_state["pending_db_accept"] = True
    _reset_execute_shopping_checks(
        (updated if isinstance(updated, dict) else {}).get("decision_id")
        or st.session_state.get("decision_id")
    )


def _cb_open_execute() -> None:
    """Button on_click — only set a flag (no rerun, no DB). Drained in main()."""
    st.session_state["pending_open_execute"] = True


def _drain_pending_open_execute() -> None:
    """Apply Starta / Handla navigation queued via on_click — before page render."""
    if not _session_pop("pending_open_execute", None):
        return
    try:
        _prepare_execute_local(st.session_state.get("current"))
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("drain pending open execute failed: %s", exc)
        st.session_state.accepted = True
        st.session_state.page = "execute"
        st.session_state.ui_error = None
        st.session_state["pending_db_accept"] = True


def open_execute_now(cur: dict[str, Any] | None = None) -> None:
    """Open execute immediately. st.rerun() must always propagate."""
    _prepare_execute_local(cur)
    st.rerun()


def _store_shopping_on_current(shop: dict[str, Any] | None) -> dict[str, Any]:
    """Write materialized shopping back onto session current.context (merge-safe)."""
    cur = st.session_state.get("current")
    cur = dict(cur) if isinstance(cur, dict) else {}
    if not shop or not isinstance(shop, dict):
        return cur
    ctx = dict(_as_dict(cur.get("context")))
    ctx["shopping"] = shop
    if isinstance(shop.get("recipe"), dict) and not isinstance(ctx.get("recipe"), dict):
        ctx["recipe"] = shop["recipe"]
    cur["context"] = ctx
    st.session_state.current = cur
    return cur


def _ensure_shopping_user() -> str | None:
    """Guarantee a user_id exists for shopping writes (guest or signed-in)."""
    uid = _shopping_list_user_id()
    if uid:
        try:
            if st.session_state.get("guest_mode") or not st.session_state.get("access_token"):
                db.clear_auth()
                db._ensure_sqlite_user(uid)
            else:
                db.ensure_user(uid, language=st.session_state.get("language", "sv"))
        except Exception as exc:
            log.warning("ensure shopping user failed: %s", exc)
            try:
                db._ensure_sqlite_user(uid)
            except Exception:
                pass
        return uid
    # Soft recover — never leave Skapa lista without a user
    try:
        db.init_db()
        db.clear_auth()
        uid = str(uuid.uuid4())
        st.session_state.user_id = uid
        st.session_state.guest_mode = True
        db._ensure_sqlite_user(uid)
        return uid
    except Exception as exc:
        log.warning("create shopping user failed: %s", exc)
        return None


def _merge_to_buy_into_list(
    to_buy: dict[str, Any] | None,
    decision_id: int | None = None,
) -> int:
    """Upsert selected to_buy rows into the persistent per-user list. Returns count."""
    if not isinstance(to_buy, dict) or not to_buy:
        return 0
    uid = _ensure_shopping_user()
    if not uid:
        _flag_shopping_list_error("no user")
        return 0
    try:
        rows = db.merge_shopping_from_decision(uid, decision_id, to_buy)
        st.session_state.shopping_list_cache = None
        st.session_state.shopping_list_error = None
        if decision_id is not None:
            st.session_state.shopping_merged_for = decision_id
        try:
            _load_shopping_items(force=True)
        except Exception:
            pass
        return len(rows or [])
    except Exception as exc:
        log.warning("merge shopping to_buy failed: %s", exc)
        # Last resort: force local SQLite and retry once
        try:
            db._mark_shopping_sqlite_fallback(exc)
            db._ensure_sqlite_user(uid)
            rows = db.merge_shopping_from_decision(uid, decision_id, to_buy)
            st.session_state.shopping_list_cache = None
            st.session_state.shopping_list_error = None
            if decision_id is not None:
                st.session_state.shopping_merged_for = decision_id
            try:
                _load_shopping_items(force=True)
            except Exception:
                pass
            return len(rows or [])
        except Exception as exc2:
            _flag_shopping_list_error(exc2)
            return 0


def _merge_accepted_shopping(cur: dict[str, Any]) -> None:
    """Upsert to_buy items into the persistent shopping list on accept."""
    ctx = _as_dict(cur.get("context"))
    shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
    if not shop:
        return
    to_buy = shop.get("to_buy")
    if not isinstance(to_buy, dict) or not to_buy:
        return
    did = cur.get("decision_id") or st.session_state.get("decision_id")
    try:
        did_i = int(did) if did is not None else None
    except (TypeError, ValueError):
        did_i = None
    _merge_to_buy_into_list(to_buy, did_i)


def _flush_db_accept() -> None:
    """Best-effort persist accept — shopping list is created when user presses Skapa lista."""
    if not _session_pop("pending_db_accept", None):
        return
    cur = st.session_state.get("current")
    cur = cur if isinstance(cur, dict) else {}
    did = cur.get("decision_id") or st.session_state.get("decision_id")
    rid = cur.get("route_log_id") or st.session_state.get("route_log_id")
    try:
        if st.session_state.get("guest_mode"):
            db.clear_auth()
        pipeline.try_accept_decision(did, route_log_id=rid)
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("deferred DB accept failed (UI already open): %s", exc)


def _selected_to_buy_from_checks(
    shop: dict[str, Any],
    decision_id: int | None,
) -> dict[str, list[str]]:
    """Build to_buy from shopping_checks toggles (default: unchecked)."""
    to_buy = shop.get("to_buy") if isinstance(shop.get("to_buy"), dict) else {}
    if not to_buy:
        return {}
    checks = st.session_state.get("shopping_checks")
    if not isinstance(checks, dict):
        checks = {}
    did = decision_id if decision_id is not None else "x"
    selected: dict[str, list[str]] = {}
    idx = 0
    for section, items in to_buy.items():
        if not items:
            continue
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            ckey = f"{did}:{idx}"
            idx += 1
            if checks.get(ckey, False):
                selected.setdefault(str(section), []).append(str(item))
    return selected


def _count_checked_shop_items(shop: dict[str, Any], decision_id: int | None) -> int:
    selected = _selected_to_buy_from_checks(shop, decision_id)
    return sum(len(v) for v in selected.values())


def _shop_item_count(shop: dict[str, Any] | None) -> int:
    if not shop or not isinstance(shop, dict):
        return 0
    to_buy = shop.get("to_buy") or {}
    if not isinstance(to_buy, dict):
        return 0
    n = 0
    for items in to_buy.values():
        if isinstance(items, str):
            n += 1
        elif isinstance(items, (list, tuple)):
            n += len(items)
    return n


def _toggle_shop_check(decision_id: int | None, idx: int) -> None:
    did = decision_id if decision_id is not None else "x"
    ckey = f"{did}:{idx}"
    checks = st.session_state.get("shopping_checks")
    if not isinstance(checks, dict):
        checks = {}
        st.session_state.shopping_checks = checks
    checks[ckey] = not bool(checks.get(ckey, False))


def _set_all_shop_checks(
    shop: dict[str, Any],
    decision_id: int | None,
    *,
    checked: bool,
) -> None:
    """Mark all execute-checklist items checked or unchecked."""
    to_buy = shop.get("to_buy") if isinstance(shop.get("to_buy"), dict) else {}
    checks = st.session_state.get("shopping_checks")
    if not isinstance(checks, dict):
        checks = {}
        st.session_state.shopping_checks = checks
    did = decision_id if decision_id is not None else "x"
    idx = 0
    for items in to_buy.values():
        if not items:
            continue
        if isinstance(items, str):
            items = [items]
        if not isinstance(items, (list, tuple)):
            continue
        for _item in items:
            ckey = f"{did}:{idx}"
            wkey = f"shop_chk_{did}_{idx}"
            checks[ckey] = bool(checked)
            st.session_state[wkey] = bool(checked)
            idx += 1


def _reset_execute_shopping_checks(decision_id: int | None = None) -> None:
    """All items start unchecked when execute opens."""
    st.session_state.shopping_checks = {}
    # Drop widget keys so checkboxes re-init unchecked
    drop = [
        k
        for k in list(st.session_state.keys())
        if isinstance(k, str) and k.startswith("shop_chk_")
    ]
    for k in drop:
        try:
            del st.session_state[k]
        except Exception:
            pass
    _ = decision_id


def _split_shop_item_label(raw: str) -> tuple[str, bool]:
    """Return (clean name, has skip-if-you-have hint)."""
    text = str(raw or "").strip()
    if not text:
        return "", False
    low = text.lower()
    has_hint = "hoppa över" in low or "skip if" in low
    parts = re.split(r"\s*[—–-]\s*", text, maxsplit=1)
    name = (parts[0] if parts else text).strip()
    return name, has_hint


def _recipe_amount_map(recipe: dict[str, Any] | None) -> dict[str, str]:
    """Map normalized ingredient name → amount string like '2 dl'."""
    out: dict[str, str] = {}
    if not isinstance(recipe, dict):
        return out
    import shopping as shopping_mod

    structured = recipe.get("ingredients_structured")
    if isinstance(structured, list):
        for ing in structured:
            if not isinstance(ing, dict):
                continue
            name = shopping_mod._norm_item(str(ing.get("name") or ""))
            if not name:
                continue
            amount = str(ing.get("amount") or "").strip()
            unit = str(ing.get("unit") or "").strip()
            if amount and unit:
                out[name] = f"{amount} {unit}".strip()
            elif amount:
                out[name] = amount
    units = r"dl|msk|tsk|krm|g|kg|ml|cl|st|skivor|näve"
    amt_trailing = re.compile(
        rf"^(?P<name>.+?)\s+(?P<amt>\d+[.,]?\d*)\s*(?P<unit>{units})?\s*$",
        re.IGNORECASE,
    )
    amt_leading = re.compile(
        rf"^(?P<amt>\d+[.,]?\d*)\s*(?P<unit>{units})\s+(?P<name>.+)$",
        re.IGNORECASE,
    )
    for line in list(recipe.get("ingredient_lines") or recipe.get("ingredients") or []):
        if isinstance(line, dict):
            continue
        raw = str(line).strip()
        if not raw:
            continue
        m = amt_leading.match(raw) or amt_trailing.match(raw)
        if not m:
            continue
        name = shopping_mod._norm_item(m.group("name"))
        if not name or name in out:
            continue
        amt = (m.group("amt") or "").replace(",", ".")
        unit = (m.group("unit") or "").strip()
        out[name] = f"{amt} {unit}".strip() if unit else amt
    return out


def _lookup_amount(amount_map: dict[str, str], name: str) -> str:
    import shopping as shopping_mod

    key = shopping_mod._norm_item(name)
    if key in amount_map:
        return amount_map[key]
    for k, v in amount_map.items():
        if key in k or k in key:
            return v
    return ""


def _history_status_label(status: str) -> str:
    key = f"history_status_{status}"
    pack = I18N.get(st.session_state.get("language", "sv"), I18N["sv"])
    return str(pack.get(key) or status)


def _restore_decision_from_row(row: dict[str, Any]) -> None:
    """Load a stored decision into session and open result/execute."""
    ctx = row.get("context")
    if not isinstance(ctx, dict):
        ctx = _as_dict(ctx)
    status = str(row.get("status") or "")
    accepted = status in ("accepted", "locked")
    cur: dict[str, Any] = {
        "ok": True,
        "domain": row.get("domain"),
        "suggestion": row.get("suggestion") or "",
        "justification": row.get("justification") or "",
        "execution_type": row.get("execution_type"),
        "execution_label": row.get("execution_label"),
        "execution_url": row.get("execution_url"),
        "decision_id": row.get("id"),
        "reroll_index": int(row.get("reroll_index") or 0),
        "locked": accepted,
        "refused": False,
        "refusal_message": None,
        "context": ctx if isinstance(ctx, dict) else {},
        "explore": False,
        "route": None,
        "route_log_id": None,
        "ui_message": None,
        "needs_domain_pick": False,
        "accepted": accepted,
        "favorite": bool(row.get("favorite")),
    }
    st.session_state.current = cur
    st.session_state.decision_id = row.get("id")
    st.session_state.accepted = accepted
    st.session_state.reroll_index = int(row.get("reroll_index") or 0)
    st.session_state.ui_error = None
    food_cook = _is_food_cook(cur)
    is_workout = (cur.get("domain") or "") == "workout" or cur.get("execution_type") == "workout"
    if accepted and (food_cook or is_workout):
        if is_workout:
            _reset_workout_player()
            _ensure_workout_in_session(cur)
        st.session_state.page = "execute"
    else:
        st.session_state.page = "result"


def _flush_db_accept_bg() -> None:
    """Deprecated alias — Cloud threading was unsafe; always sync after paint."""
    _flush_db_accept()


def on_accept_food_and_execute(cur: dict[str, Any]) -> None:
    """Food 'Välj' — accept, lock, and open execute in one tap."""
    try:
        st.session_state.accepted = False
        accept_current_decision(cur)
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("on_accept_food_and_execute failed: %s", exc)
        _lock_current_locally(cur)
        st.session_state.accepted = True
    try:
        safe_toast(t("accepted"))
    except Exception:
        pass
    st.session_state.ui_error = None
    open_execute_now(cur)


def on_accept_primary(cur: dict[str, Any]) -> None:
    """Primary accept for non-execute domains — lock locally first."""
    _lock_current_locally(cur)
    try:
        # Force DB write even though we already locked locally
        st.session_state.accepted = False
        accept_current_decision(cur)
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("on_accept_primary failed: %s", exc)
        st.session_state.accepted = True
    try:
        safe_toast(t("accepted"))
    except Exception:
        pass
    st.session_state.ui_error = None
    st.rerun()


def accept_and_open_execute(cur: dict[str, Any]) -> None:
    """Handla & laga / Starta passet → execute view (navigate first)."""
    open_execute_now(cur)


def _toggle_decision_favorite(decision_id: int) -> None:
    _ensure_db_api()
    cur = st.session_state.get("current")
    if not isinstance(cur, dict):
        cur = {}
    want = not bool(cur.get("favorite"))
    try:
        row = db.set_decision_favorite(int(decision_id), want)
        cur["favorite"] = bool(row.get("favorite"))
        st.session_state.current = cur
    except Exception as exc:
        log.warning("favorite toggle failed: %s", exc)


def _render_favorite_toggle(decision_id: int | None, *, is_favorite: bool) -> None:
    if not decision_id:
        return
    # Marker class for filled heart CSS (Streamlit keys can't be dynamic for CSS)
    marker = "oc-fav-on" if is_favorite else "oc-fav-off"
    st.markdown(
        f'<div class="{marker}" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="exec_fav_corner"):
        label = t("favorite_remove") if is_favorite else t("favorite_add")
        if st.button(
            label,
            key=f"fav_toggle_{int(decision_id)}",
            use_container_width=True,
            type="secondary",
        ):
            _toggle_decision_favorite(int(decision_id))
            st.rerun()


def _cook_favorite_tonight(row: dict[str, Any]) -> None:
    """Seed a new accepted decision from a favorited recipe and open execute."""
    uid = str(st.session_state.get("user_id") or "")
    if not uid:
        return
    ctx = row.get("context")
    if not isinstance(ctx, dict):
        ctx = _as_dict(ctx) or {}
    ctx = dict(ctx)
    ctx["from_favorite"] = True
    ctx["favorite_source_id"] = row.get("id")
    try:
        new_row = db.create_decision(
            user_id=uid,
            domain=str(row.get("domain") or "food"),
            question=str(row.get("question") or t("cook_tonight")),
            suggestion=str(row.get("suggestion") or ""),
            justification=str(row.get("justification") or ""),
            status="accepted",
            reroll_index=0,
            context=ctx,
            execution_type=row.get("execution_type"),
            execution_label=row.get("execution_label"),
            execution_url=row.get("execution_url"),
        )
    except Exception as exc:
        log.warning("cook tonight create failed: %s", exc)
        return
    _restore_decision_from_row(new_row)
    st.rerun()


def _favorite_card_html(row: dict[str, Any], language: str) -> str:
    import base64

    import food_categories as fcat

    suggestion = str(row.get("suggestion") or "")
    ctx = row.get("context") if isinstance(row.get("context"), dict) else {}
    cat = fcat.infer_dish_category(
        suggestion,
        meta={**(ctx or {}), "dish_category": (ctx or {}).get("dish_category")},
    )
    img = ""
    raw = fcat.dish_image_bytes(cat)
    if raw:
        b64 = base64.b64encode(raw).decode("ascii")
        img = f'<img src="data:image/jpeg;base64,{b64}" alt=""/>'
    mins = None
    recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
    if recipe and recipe.get("active_minutes") is not None:
        try:
            mins = int(recipe["active_minutes"])
        except (TypeError, ValueError):
            mins = None
    if mins is None and ctx.get("max_active_minutes") is not None:
        try:
            mins = int(ctx["max_active_minutes"])
        except (TypeError, ValueError):
            mins = None
    meta = t("recipe_mins").format(mins=mins) if mins else ""
    return (
        f'<div class="oc-fav-card">{img}'
        f'<div class="oc-fav-meta"><strong>{html.escape(suggestion)}</strong>'
        f'<span>{html.escape(meta)}</span></div></div>'
    )


def raise_ui_error(where: str, exc: BaseException | None = None) -> None:
    """Replace the whole content area with the friendly error (never stack mid-page)."""
    if exc is not None:
        log.error("ui error at %s:\n%s", where, traceback.format_exc())
    else:
        log.error("ui error at %s", where)
    st.session_state.ui_error = True
    st.rerun()


def _shopping_list_user_id() -> str | None:
    uid = st.session_state.get("user_id")
    return str(uid) if uid else None


def _ensure_db_api() -> None:
    """Streamlit Cloud can hot-reload app.py while keeping a stale `db` module.

    Reloads until shopping + favorites APIs are present (incl. list_decisions
    accepting favorite=).
    """
    global db
    import importlib
    import inspect

    required = (
        "delete_shopping_items",
        "clear_checked_shopping_items",
        "purge_stale_checked_shopping_items",
        "list_shopping_items",
        "toggle_shopping_item",
        "add_manual_shopping_item",
        "merge_shopping_from_decision",
        "list_decisions",
        "set_decision_favorite",
        "list_favorite_suggestions",
    )
    missing = [name for name in required if not hasattr(db, name)]
    needs_fav_kw = False
    if hasattr(db, "list_decisions"):
        try:
            params = inspect.signature(db.list_decisions).parameters
            needs_fav_kw = "favorite" not in params
        except (TypeError, ValueError):
            needs_fav_kw = True
    if not missing and not needs_fav_kw:
        return
    log.warning(
        "stale db module missing %s fav_kw=%s — reloading db (+ supabase_store)",
        missing,
        needs_fav_kw,
    )
    db = importlib.reload(db)
    try:
        import supabase_store as store

        importlib.reload(store)
    except Exception as exc:
        log.warning("supabase_store reload skipped: %s", exc)
    still = [name for name in required if not hasattr(db, name)]
    if still:
        raise AttributeError(f"db API still missing after reload: {still}")
    if "favorite" not in inspect.signature(db.list_decisions).parameters:
        raise AttributeError("db.list_decisions still missing favorite= after reload")


def _ensure_db_shopping_api() -> None:
    """Back-compat alias — shopping + favorites share one reload gate."""
    _ensure_db_api()


def _list_decisions(
    user_id: str,
    *,
    domain: str | None = None,
    status: str | None = None,
    favorite: bool | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Call db.list_decisions after ensuring favorite= is supported."""
    global db
    _ensure_db_api()
    kwargs: dict[str, Any] = {"limit": limit}
    if domain is not None:
        kwargs["domain"] = domain
    if status is not None:
        kwargs["status"] = status
    if favorite is not None:
        kwargs["favorite"] = favorite
    try:
        return db.list_decisions(user_id, **kwargs)
    except TypeError as exc:
        # Stale module slipped through — reload once and retry
        if "favorite" not in str(exc):
            raise
        log.warning("list_decisions favorite TypeError — force reload: %s", exc)
        import importlib

        db = importlib.reload(db)
        try:
            import supabase_store as store

            importlib.reload(store)
        except Exception:
            pass
        return db.list_decisions(user_id, **kwargs)


def _flag_shopping_list_error(exc: BaseException | str | None = None) -> None:
    """Mark shopping error for UI — raw details stay in server logs only."""
    if isinstance(exc, BaseException):
        log.warning("shopping list error: %s", exc)
    elif exc:
        log.warning("shopping list error: %s", exc)
    st.session_state.shopping_list_error = True


def _show_shopping_list_error() -> None:
    """Yellow friendly warning only — never render exception text to users."""
    if st.session_state.get("shopping_list_error") or st.session_state.get(
        "_lista_clear_error"
    ):
        st.warning(t("list_error"))


def _load_shopping_items(*, force: bool = False) -> list[dict[str, Any]]:
    _ensure_db_shopping_api()
    cached = st.session_state.get("shopping_list_cache")
    if not force and isinstance(cached, list):
        return _apply_lista_tombstones(cached)
    uid = _ensure_shopping_user()
    if not uid:
        return []
    try:
        db.purge_stale_checked_shopping_items(uid)
        items = db.list_shopping_items(uid)
    except Exception as exc:
        log.warning("load shopping items failed: %s", exc)
        try:
            db._mark_shopping_sqlite_fallback(exc)
            db._ensure_sqlite_user(uid)
            items = db.list_shopping_items(uid)
        except Exception:
            items = list(cached) if isinstance(cached, list) else []
    items = _apply_lista_tombstones(items)
    st.session_state.shopping_list_cache = items
    return items


def _flush_shopping_pending_writes() -> None:
    pending = list(st.session_state.get("shopping_pending_writes") or [])
    if not pending:
        return
    uid = _shopping_list_user_id()
    if not uid:
        st.session_state.shopping_pending_writes = []
        return
    remaining: list[dict[str, Any]] = []
    for op in pending:
        try:
            db.toggle_shopping_item(uid, int(op["id"]), bool(op["checked"]))
        except Exception as exc:
            log.warning("shopping write-behind failed id=%s: %s", op.get("id"), exc)
            remaining.append(op)
    st.session_state.shopping_pending_writes = remaining


def _clear_done_shopping_items(done: list[dict[str, Any]]) -> int:
    """Rensa klara — delete Klart rows by id (and checked=1 as backup).

    Order matters: flush optimistic check-writes first so cloud rows are
    actually checked, then DELETE by id. Never drop pending toggles before
    flush — that made clear_checked find zero rows when DELETE was blocked.

    Always applies local tombstones so the UI clears even if remote lags.
    Returns number of ids requested.
    """
    _ensure_db_shopping_api()
    ids = [int(r.get("id") or 0) for r in done if int(r.get("id") or 0) > 0]
    if not ids:
        return 0
    id_set = set(ids)
    # 1) Persist optimistic checks so cloud DELETE / clear_checked can see them
    _flush_shopping_pending_writes()
    # 2) Drop any remaining write-behind for these ids (do not resurrect)
    pending = list(st.session_state.get("shopping_pending_writes") or [])
    st.session_state.shopping_pending_writes = [
        p for p in pending if int(p.get("id") or 0) not in id_set
    ]
    # 3) Tombstones + local cache — UI must clear this paint
    tombs = set(int(i) for i in (st.session_state.get("_lista_tombstones") or []))
    tombs |= id_set
    st.session_state["_lista_tombstones"] = sorted(tombs)
    cached = st.session_state.get("shopping_list_cache")
    if isinstance(cached, list):
        st.session_state.shopping_list_cache = [
            r for r in cached if int(r.get("id") or 0) not in id_set
        ]
    else:
        st.session_state.shopping_list_cache = []
    for iid in ids:
        st.session_state.pop(f"lista_chk_{iid}", None)
    uid = _ensure_shopping_user()
    if not uid:
        return len(ids)
    # 4) Cloud/sqlite delete by id, then belt-and-suspenders clear_checked
    failed = False
    try:
        db.delete_shopping_items(uid, ids)
    except Exception as exc:
        log.warning("delete shopping items by id failed: %s", exc)
        failed = True
    try:
        db.clear_checked_shopping_items(uid)
    except Exception as exc2:
        log.warning("clear checked shopping fallback failed: %s", exc2)
        failed = True
    # Verify remote no longer returns these ids
    try:
        left = {
            int(r.get("id") or 0)
            for r in db.list_shopping_items(uid)
            if int(r.get("id") or 0) in id_set
        }
        if not left:
            failed = False
            st.session_state.shopping_list_cache = None
    except Exception as exc3:
        log.warning("post-clear shopping verify failed: %s", exc3)
        failed = True
    if failed:
        st.session_state["_lista_clear_error"] = True
    else:
        st.session_state.pop("_lista_clear_error", None)
    return len(ids)


def _request_clear_done_shopping_items() -> None:
    """on_click: stash Klart ids and ask page_lista to clear before widgets."""
    ids = [
        int(i)
        for i in (st.session_state.get("_lista_clear_ids_ready") or [])
        if int(i) > 0
    ]
    st.session_state["_lista_clear_ids"] = ids
    st.session_state["_lista_clear_request"] = True


def _apply_lista_tombstones(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hide rows Rensa klara already removed (covers slow/failed remote DELETE)."""
    tombs = {int(i) for i in (st.session_state.get("_lista_tombstones") or []) if int(i) > 0}
    if not tombs:
        return items
    # Retry delete for ids the backend still returns
    still = [int(r.get("id") or 0) for r in items if int(r.get("id") or 0) in tombs]
    if still:
        uid = _shopping_list_user_id()
        if uid:
            try:
                db.delete_shopping_items(uid, still)
            except Exception as exc:
                log.warning("tombstone retry delete failed: %s", exc)
    kept = [r for r in items if int(r.get("id") or 0) not in tombs]
    present = {int(r.get("id") or 0) for r in items}
    # Forget tombstones once the backend no longer returns them
    st.session_state._lista_tombstones = sorted(tombs & present)
    return kept


def _optimistic_toggle_shopping_item(
    item_id: int,
    *,
    checked: bool | None = None,
) -> None:
    items = _load_shopping_items()
    target: dict[str, Any] | None = None
    for row in items:
        if int(row.get("id") or 0) == int(item_id):
            target = dict(row)
            break
    if not target:
        return
    if checked is None:
        new_checked = not bool(target.get("checked"))
    else:
        new_checked = bool(checked)
        if bool(target.get("checked")) == new_checked:
            return
    target["checked"] = new_checked
    if new_checked:
        from datetime import datetime, timezone

        target["checked_at"] = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        )
    else:
        target["checked_at"] = None
    updated: list[dict[str, Any]] = []
    for row in items:
        if int(row.get("id") or 0) == int(item_id):
            updated.append(target)
        else:
            updated.append(row)
    st.session_state.shopping_list_cache = updated
    queue = list(st.session_state.get("shopping_pending_writes") or [])
    queue = [q for q in queue if int(q.get("id") or 0) != int(item_id)]
    queue.append({"id": int(item_id), "checked": new_checked})
    st.session_state.shopping_pending_writes = queue
    _flush_shopping_pending_writes()


def _render_shop_toggle_button(
    *,
    label: str,
    key: str,
    checked: bool,
) -> bool:
    """Premium row-styled toggle — primary=checked, secondary=open."""
    st.markdown(
        f'<div class="oc-shop-tog-marker" data-checked="{"1" if checked else "0"}"></div>',
        unsafe_allow_html=True,
    )
    return bool(
        st.button(
            label,
            key=key,
            use_container_width=True,
            type="primary" if checked else "secondary",
        )
    )


def render_persistent_shopping_list() -> None:
    """Lista tab — active aisles + Klart section (checked leave their category)."""
    _flush_shopping_pending_writes()
    items = _load_shopping_items(force=True)
    if not items:
        st.markdown(
            f'<p class="oc-meta">{html.escape(t("list_empty"))}</p>',
            unsafe_allow_html=True,
        )
        return
    import importlib

    import shopping_items as si

    # Streamlit Cloud can hot-reload app.py before shopping_items — refresh if stale.
    if not hasattr(si, "checked_items"):
        si = importlib.reload(si)

    grouped = si.group_items(items)
    done = si.checked_items(items)

    def _row_checkbox(row: dict[str, Any]) -> None:
        iid = int(row.get("id") or 0)
        name = str(row.get("name") or "")
        checked = bool(row.get("checked"))
        wkey = f"lista_chk_{iid}"
        if wkey not in st.session_state:
            st.session_state[wkey] = checked
        elif bool(st.session_state.get(wkey)) != checked:
            # Cache moved item between aisle ↔ Klart — sync widget state
            st.session_state[wkey] = checked

        def _on_toggle(item_id: int = iid, wk: str = wkey) -> None:
            new_val = bool(st.session_state.get(wk, False))
            _optimistic_toggle_shopping_item(item_id, checked=new_val)

        st.checkbox(
            name,
            key=wkey,
            on_change=_on_toggle,
        )

    err = st.session_state.get("_lista_clear_error")
    if err:
        st.warning(t("list_error"))

    with st.container(border=True, key="lista_shop_card"):
        st.markdown(
            '<div class="oc-shop-pick-marker" data-mode="lista" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        for section, rows in grouped.items():
            if not rows:
                continue
            st.markdown(
                f'<div class="oc-sec-label">{html.escape(section)}</div>',
                unsafe_allow_html=True,
            )
            for row in rows:
                _row_checkbox(row)

        if done:
            n_done = len(done)
            st.markdown(
                f'<div class="oc-sec-label oc-klart-label">'
                f'{html.escape(t("list_done"))} ({n_done})</div>',
                unsafe_allow_html=True,
            )
            for row in done:
                _row_checkbox(row)

    # Outside the card — full-width button + on_click (forms inside the card
    # were unreliable on mobile; deferred clear runs at page_lista start).
    if done:
        st.session_state["_lista_clear_ids_ready"] = [
            int(r.get("id") or 0) for r in done if int(r.get("id") or 0) > 0
        ]
        with st.container(key="lista_clear_done"):
            st.button(
                t("list_clear_done"),
                key="lista_clear_done_btn",
                type="primary",
                use_container_width=True,
                on_click=_request_clear_done_shopping_items,
            )


def render_decision_shopping_added(
    shop: dict[str, Any] | None,
    language: str,
    *,
    recipe: dict[str, Any] | None = None,
) -> None:
    """Execute: quiet checklist card (CTA rendered separately as sticky)."""
    if not shop or not isinstance(shop, dict):
        return
    to_buy = shop.get("to_buy") or {}
    if not isinstance(to_buy, dict) or not to_buy:
        return

    err = st.session_state.get("shopping_list_error")
    if err:
        st.warning(t("list_error"))

    if getattr(db, "_SHOPPING_FORCE_SQLITE", False):
        st.caption(t("list_local_note"))

    did = _active_decision_id()
    render_checkable_shopping(shop, did, recipe=recipe)


def render_execute_sticky_cta(shop: dict[str, Any] | None) -> None:
    """Single indigo CTA above nav — indigo reserved for this one action."""
    if not shop or not isinstance(shop, dict):
        return
    to_buy = shop.get("to_buy") or {}
    if not isinstance(to_buy, dict) or not to_buy:
        return
    did = _active_decision_id()
    merged_for = st.session_state.get("shopping_merged_for")
    already = did is not None and merged_for is not None and int(merged_for) == int(did)
    checked_n = _count_checked_shop_items(shop, did)
    with st.container(key="exec_sticky_cta"):
        if already:
            # Session-safe — never use ?nav= anchors here
            if st.button(
                t("list_added_open") + " →",
                type="primary",
                use_container_width=True,
                key="exec_open_lista",
            ):
                st.session_state.page = "lista"
                st.rerun()
        else:
            label = t("list_add_n").format(n=checked_n)
            if st.button(
                label,
                type="primary",
                use_container_width=True,
                key="exec_create_list",
                disabled=checked_n <= 0,
            ):
                selected = _selected_to_buy_from_checks(shop, did)
                if not selected:
                    st.rerun()
                    return
                n = _merge_to_buy_into_list(selected, did)
                if n:
                    try:
                        safe_toast(t("list_created"))
                    except Exception:
                        pass
                    st.session_state.shopping_list_error = None
                elif not st.session_state.get("shopping_list_error"):
                    st.session_state.shopping_list_error = True
                st.rerun()


def render_checkable_shopping(
    shop: dict[str, Any] | None,
    decision_id: int | None,
    *,
    recipe: dict[str, Any] | None = None,
) -> None:
    """Selection checklist via st.checkbox — stays on execute, no anchors."""
    if not shop or not isinstance(shop, dict):
        return
    to_buy = shop.get("to_buy") or {}
    if not isinstance(to_buy, dict) or not to_buy:
        return
    import shopping as shopping_mod

    language = st.session_state.get("language", "sv")
    checks = st.session_state.get("shopping_checks")
    if not isinstance(checks, dict):
        checks = {}
        st.session_state.shopping_checks = checks
    did = decision_id if decision_id is not None else "x"
    recipe_src = recipe if isinstance(recipe, dict) else None
    if recipe_src is None and isinstance(shop.get("recipe"), dict):
        recipe_src = shop.get("recipe")
    amount_map = _recipe_amount_map(recipe_src)

    with st.container(border=True, key="exec_shop_card"):
        st.markdown(
            '<div class="oc-shop-pick-marker" aria-hidden="true"></div>',
            unsafe_allow_html=True,
        )
        head_l, head_r = st.columns([3, 1])
        with head_l:
            st.markdown(
                f'<div class="oc-shop-title">{html.escape(t("list_create_hint"))}</div>',
                unsafe_allow_html=True,
            )
        with head_r:
            if st.button(
                t("list_mark_all"),
                key=f"shop_mark_all_{did}",
                use_container_width=True,
            ):
                _set_all_shop_checks(shop, decision_id, checked=True)
                st.rerun()

        idx = 0
        for section, items in to_buy.items():
            if not items:
                continue
            if isinstance(items, str):
                items = [items]
            if not isinstance(items, (list, tuple)):
                continue
            st.markdown(
                f'<div class="oc-sec-label">{html.escape(str(section))}</div>',
                unsafe_allow_html=True,
            )
            for item in items:
                ckey = f"{did}:{idx}"
                wkey = f"shop_chk_{did}_{idx}"
                name, has_hint = _split_shop_item_label(str(item))
                amt = _lookup_amount(amount_map, name)
                if wkey not in st.session_state:
                    st.session_state[wkey] = bool(checks.get(ckey, False))

                label_bits = [name]
                if has_hint:
                    label_bits.append(f"({t('list_skip_hint')})")
                if amt:
                    label_bits.append(f"— {amt}")
                label = " ".join(label_bits)

                def _sync_check(ck: str = ckey, wk: str = wkey) -> None:
                    cur_checks = st.session_state.get("shopping_checks")
                    if not isinstance(cur_checks, dict):
                        cur_checks = {}
                        st.session_state.shopping_checks = cur_checks
                    cur_checks[ck] = bool(st.session_state.get(wk, False))

                checked = st.checkbox(
                    label,
                    key=wkey,
                    on_change=_sync_check,
                )
                checks[ckey] = bool(checked)
                idx += 1

        assumed = shop.get("assumed_at_home") or ["salt", "peppar", "olja"]
        if not isinstance(assumed, (list, tuple)):
            assumed = ["salt", "peppar", "olja"]
        assumed_line = shopping_mod.format_assumed_line(list(assumed), language=language)
        st.markdown(
            f'<p class="oc-assumed">{html.escape(assumed_line)}</p>',
            unsafe_allow_html=True,
        )


def _profile_show_nutrition() -> bool:
    """Recipe-only nutrition — ON by default. Never drives decision-card UI."""
    import json

    try:
        uid = st.session_state.get("user_id")
        if not uid:
            return True
        user = db.ensure_user(uid)
        raw = user.get("profile_json") or {}
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        food = (raw if isinstance(raw, dict) else {}).get("food") or {}
        if "show_nutrition" not in food:
            return True
        return bool(food.get("show_nutrition"))
    except Exception:
        return True


def _set_profile_show_nutrition(enabled: bool) -> None:
    """Persist preference to profile_json.food.show_nutrition."""
    import json

    uid = st.session_state.get("user_id")
    if not uid:
        return
    user = db.ensure_user(uid)
    raw = user.get("profile_json") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    food = dict(raw.get("food") or {})
    food["show_nutrition"] = bool(enabled)
    raw["food"] = food
    db.update_user(uid, profile_json=raw)


def _mark_execution_opened_for_current(cur: dict[str, Any]) -> None:
    """Persist execute-view open — grounds leftover evidence."""
    did = _active_decision_id(cur)
    if did is None:
        return
    try:
        db.mark_execution_opened(int(did))
    except Exception as exc:
        log.warning("mark_execution_opened failed: %s", exc)


def _nutrition_display_line(recipe: dict[str, Any] | None) -> tuple[str, bool]:
    """Return (label, has_values) for the nutrition control — never None/null text."""
    import shopping as shopping_mod

    lang = st.session_state.get("language", "sv")
    missing = t("nutrition_missing")
    if not isinstance(recipe, dict):
        return missing, False
    try:
        import shopping as shopping_mod

        visible = getattr(shopping_mod, "nutrition_segment_visible", None)
        if callable(visible) and not visible(recipe):
            return missing, False
    except Exception:
        pass
    try:
        ensure = getattr(shopping_mod, "ensure_recipe_nutrition", None)
        if callable(ensure):
            healed = ensure(
                recipe,
                suggestion=str(recipe.get("title") or ""),
                allow_estimate=True,
            )
        else:
            healed = recipe
    except Exception:
        healed = recipe
    try:
        fmt = getattr(shopping_mod, "format_nutrition_line", None)
        if callable(fmt):
            line = fmt(
                healed.get("nutrition") if isinstance(healed.get("nutrition"), dict) else None,
                language=lang,
                recipe=healed if isinstance(healed, dict) else None,
            )
        else:
            line = _format_nutrition_fallback(healed, language=lang)
    except Exception:
        line = _format_nutrition_fallback(healed, language=lang)
    if not line or line.strip().lower() in ("none", "null"):
        return missing, False
    has_vals = "kcal" in line.lower() and (
        "ca " in line.lower() or "approx" in line.lower() or "≈" in line
    )
    return line, has_vals


def _format_nutrition_fallback(
    recipe: dict[str, Any] | None,
    *,
    language: str = "sv",
) -> str:
    """Last-resort formatter if shopping.py is stale on Cloud hot-reload."""
    if not isinstance(recipe, dict):
        return "Nutrition unavailable" if language == "en" else "Näringsvärden saknas"
    nut = recipe.get("nutrition") if isinstance(recipe.get("nutrition"), dict) else {}
    kcal = recipe.get("kcal_per_portion", nut.get("kcal"))
    protein = recipe.get("protein_g_per_portion", nut.get("protein_g"))
    try:
        k_i = int(kcal)
        p_i = int(protein)
    except (TypeError, ValueError):
        return "Nutrition unavailable" if language == "en" else "Näringsvärden saknas"
    if language == "en":
        return f"Approx. {k_i} kcal per serving · {p_i} g protein"
    return f"Ca {k_i} kcal per portion · {p_i} g protein"


def render_top_chrome(*, extra_class: str = "", show_lang: bool = True) -> None:
    """Fixed frosted header: OneChoice wordmark + SV/EN (lang pills overlay right)."""
    extra = f" {extra_class}" if extra_class else ""
    st.markdown(
        f'<header class="oc-header{extra}" aria-label="OneChoice">'
        f'<span class="oc-header-wordmark oc-logo">OneChoice</span>'
        f"</header>",
        unsafe_allow_html=True,
    )
    if show_lang:
        lang_bar()


def render_share_landing_chrome() -> None:
    """Public share page — wordmark only (no lang bar / bottom nav)."""
    render_top_chrome(extra_class="oc-share-landing", show_lang=False)
    st.markdown(
        '<div class="oc-share-landing-marker" data-oc-share="landing" aria-hidden="true"></div>',
        unsafe_allow_html=True,
    )


def render_food_recipe(
    recipe: dict[str, Any] | None,
    fallback_ings: list[str] | None = None,
    *,
    show_nutrition: bool | None = None,
    include_ingredients: bool = True,
) -> None:
    """Single entry for food recipe cards — always show the same kcal line."""
    import shopping as shopping_mod

    # Always show on food pages (profile opt-out is ignored here — user asked for
    # kcal on every matsida; existing profiles often still have show_nutrition=False).
    if show_nutrition is None:
        show_nutrition = True
    healed = recipe
    if isinstance(recipe, dict):
        try:
            ensure = getattr(shopping_mod, "ensure_recipe_nutrition", None)
            if callable(ensure):
                healed = ensure(
                    recipe,
                    suggestion=str(recipe.get("title") or ""),
                    allow_estimate=True,
                )
        except Exception:
            healed = recipe
    render_recipe_block(
        healed,
        fallback_ings,
        show_nutrition=show_nutrition,
        include_ingredients=include_ingredients,
    )


def render_recipe_block(
    recipe: dict[str, Any] | None,
    fallback_ings: list[str] | None = None,
    *,
    show_nutrition: bool | None = None,
    include_ingredients: bool = True,
) -> None:
    if not recipe or not isinstance(recipe, dict):
        if fallback_ings:
            recipe = {"ingredients": fallback_ings, "steps": []}
        else:
            return
    ings = recipe.get("ingredient_lines") or recipe.get("ingredients") or fallback_ings or []
    steps = recipe.get("steps") or []
    nutrition_html = ""
    if show_nutrition is None:
        show_nutrition = True
    if show_nutrition and include_ingredients:
        line, has_vals = _nutrition_display_line(recipe)
        if has_vals:
            nutrition_html = f'<p class="oc-nutrition">{html.escape(line)}</p>'
    ings_html = ""
    if include_ingredients:
        ings_html = (
            f'<div class="oc-sec">{html.escape(t("ingredients_title"))}</div>'
            f'<ul>{"".join(f"<li>{html.escape(str(i))}</li>" for i in ings)}</ul>'
        )
        title = f'<div class="oc-shop-title">{html.escape(t("recipe_title"))}</div>'
        steps_sec = f'<div class="oc-sec">{html.escape(t("steps_title"))}</div>'
        card_cls = "oc-recipe"
    else:
        title = f'<div class="oc-shop-title">{html.escape(t("steps_title"))}</div>'
        steps_sec = ""
        card_cls = "oc-recipe oc-recipe-steps-only"
    st.markdown(
        f'<div class="{card_cls}">'
        f"{title}"
        f"{nutrition_html}"
        f"{ings_html}"
        f"{steps_sec}"
        f'<ol>{"".join(f"<li>{html.escape(str(s))}</li>" for s in steps)}</ol>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_error_boundary() -> None:
    """Friendly Swedish error — never show a traceback to the user."""
    render_top_chrome()
    st.markdown(
        f'<div class="oc-error"><p>{html.escape(t("error_friendly"))}</p></div>',
        unsafe_allow_html=True,
    )
    # Raw exception stays in logs / _last_ui_error — never render to users
    if st.button(t("retry"), type="primary", use_container_width=True, key="ui_error_retry"):
        st.session_state.ui_error = None
        st.session_state._last_ui_error = None
        # Prefer returning to execute if we have a decision (Handla recovery)
        cur = st.session_state.get("current") or {}
        if isinstance(cur, dict) and cur.get("suggestion") and (
            st.session_state.get("accepted") or cur.get("accepted") or cur.get("locked")
        ):
            st.session_state.page = "execute"
        elif st.session_state.get("page") not in (
            "home",
            "result",
            "execute",
            "history",
            "profile",
            "auth",
        ):
            st.session_state.page = "home"
        st.rerun()
    nav()


def _qp_one(value: Any) -> str | None:
    """Normalize Streamlit query param (str or list) to a single string."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if not value:
            return None
        value = value[0]
    text = str(value).strip()
    return text or None


def _guest_query_active() -> bool:
    return _qp_one(st.query_params.get("guest")) == "1"


def _bootstrap_guest_session() -> None:
    """Ensure guest mode survives ?domain= / ?nav= full-page navigations on mobile."""
    if not (st.session_state.get("guest_mode") or _guest_query_active()):
        return
    st.session_state.guest_mode = True
    st.session_state.access_token = None
    st.session_state.refresh_token = None
    db.clear_auth()
    if not st.session_state.user_id:
        db.init_db()
        st.session_state.user_id = str(uuid.uuid4())
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)


def _qp_href(**params: str) -> str:
    """Build query-string href; carry guest=1 so session survives chip/nav taps."""
    parts = [f"{k}={html.escape(str(v), quote=True)}" for k, v in params.items()]
    if st.session_state.get("guest_mode") or _guest_query_active():
        parts.append("guest=1")
    return "?" + "&".join(parts)


def _set_guest_query_param() -> None:
    try:
        st.query_params["guest"] = "1"
    except Exception:
        pass


def _clear_guest_query_param() -> None:
    try:
        del st.query_params["guest"]
    except Exception:
        pass


def page_home() -> None:
    import router as rt

    # Locked decision in play → resume it. Chooser only for an explicit start-over.
    force_chooser = bool(_session_pop("_force_home_chooser", False))
    if not force_chooser:
        resume = _resume_decision_page()
        if resume:
            st.session_state.page = resume
            st.rerun()
            return

    render_logo()
    inferred = infer_home_hero(language=st.session_state.get("language", "sv"))

    with st.container(key="home_hero"):
        render_home_hero(inferred)

    if inferred.get("weekend_alternate"):
        with st.container(key="home_weekend_alt"):
            alt = str(inferred.get("weekend_headline") or "")
            if st.button(alt, key="home_weekend_alt_btn"):
                run_decision(
                    question="",
                    domain_hint="weekend",
                    reroll=False,
                    via_router=False,
                )

    render_home_domain_grid()

    with st.container(key="home_free_form"):
        with st.form("home_free_form", clear_on_submit=False, border=False):
            col_in, col_go = st.columns([5, 1.6], gap="small", vertical_alignment="bottom")
            with col_in:
                q = st.text_input(
                    " ",
                    label_visibility="collapsed",
                    key="home_free_input",
                    placeholder=t("home_free_placeholder"),
                    max_chars=rt.MAX_INPUT_CHARS,
                )
            with col_go:
                submitted = st.form_submit_button(
                    t("home_free_submit"),
                    use_container_width=True,
                )
    if submitted:
        question = (q or "").strip()
        if not question:
            st.warning(t("empty"))
        elif len(question) > rt.MAX_INPUT_CHARS:
            st.warning(t("too_long"))
        else:
            run_decision(question=question, domain_hint=None, reroll=False, via_router=True)
    nav()


def _clear_fridge_session() -> None:
    st.session_state.fridge_step = "capture"
    st.session_state.fridge_inventory = []
    st.session_state.fridge_mode = False
    st.session_state.fridge_photos = []
    st.session_state.pop("fridge_cam_bytes", None)
    st.session_state.pop("fridge_cam_mime", None)
    st.session_state.pop("fridge_upload_bytes", None)
    st.session_state.pop("fridge_upload_mimes", None)


def _fridge_debug_ui() -> bool:
    """Show build/API diagnostics only when ?debug=1 (not for end users)."""
    try:
        return str(st.query_params.get("debug", "")).lower() in ("1", "true", "yes")
    except Exception:
        return False


def _fridge_photos() -> list[dict[str, Any]]:
    raw = st.session_state.get("fridge_photos")
    return list(raw) if isinstance(raw, list) else []


def _fridge_add_photo(blob: bytes, mime: str = "image/jpeg") -> bool:
    """Append a unique photo; returns True if added. Caps at MAX_PHOTOS."""
    import hashlib

    import fridge_domain as fr

    if not isinstance(blob, (bytes, bytearray)) or len(blob) < 20:
        return False
    data = bytes(blob)
    fp = hashlib.sha1(data).hexdigest()
    photos = _fridge_photos()
    if any(p.get("fp") == fp for p in photos):
        return False
    if len(photos) >= fr.MAX_PHOTOS:
        return False
    photos.append({"bytes": data, "mime": mime or "image/jpeg", "fp": fp})
    st.session_state.fridge_photos = photos
    return True


def page_fridge() -> None:
    """Capture photos → invent inventory → confirm chips → decide (two LLM steps)."""
    import time

    import fridge_domain as fr

    debug = _fridge_debug_ui()
    render_top_chrome()
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("fridge_title"))}</p>',
        unsafe_allow_html=True,
    )
    st.caption(t("fridge_hint"))

    api_key = resolve_grok_api_key()
    diag = diagnose_grok_secret()
    key_ok = bool(diag.get("usable")) or _usable_grok_secret(api_key)
    if not key_ok:
        st.warning(t("fridge_api_missing"))
        if debug:
            names = diag.get("secret_names") or []
            detail = (
                f"nycklar={names or '[]'} · "
                f"GROK_API_KEY={'ja' if diag.get('has_grok_name') else 'nej'} · "
                f"träff={diag.get('found_name') or 'ingen'} · "
                f"len={diag.get('len')} · "
                f"xai-prefix={'ja' if diag.get('startswith_xai') else 'nej'}"
            )
            st.caption(t("fridge_api_diag").format(detail=detail))
            st.caption(
                "Exakt format i Streamlit Secrets (inga [sektioner] runt nyckeln):\n"
                'GROK_API_KEY = "xai-din-nyckel-här"'
            )
    elif debug:
        st.caption(f"{t('fridge_api_ok')} · {len(api_key)} tecken · {api_key[:4]}…")

    step = st.session_state.get("fridge_step") or "capture"

    if step == "capture":
        photos = _fridge_photos()
        st.caption(
            t("fridge_photos_count").format(n=len(photos), max=fr.MAX_PHOTOS)
            + " · "
            + t("fridge_camera_tip")
        )

        if len(photos) < fr.MAX_PHOTOS:
            cam_kwargs: dict[str, Any] = {"key": "fridge_cam"}
            try:
                import inspect as _inspect

                if "resolution" in _inspect.signature(st.camera_input).parameters:
                    cam_kwargs["resolution"] = "1080p"
            except Exception:
                pass
            cam = st.camera_input(t("fridge_camera"), **cam_kwargs)
            if cam is not None:
                try:
                    added = _fridge_add_photo(
                        cam.getvalue(),
                        getattr(cam, "type", None) or "image/jpeg",
                    )
                    # Keep legacy keys for safety
                    st.session_state["fridge_cam_bytes"] = cam.getvalue()
                    st.session_state["fridge_cam_mime"] = (
                        getattr(cam, "type", None) or "image/jpeg"
                    )
                    if added:
                        st.rerun()
                except Exception as exc:
                    log.warning("fridge camera read failed: %s", exc)
            if photos:
                st.caption(t("fridge_add_another"))
        else:
            st.info(t("fridge_photos_full"))

        if photos:
            cols = st.columns(min(3, len(photos)))
            for i, photo in enumerate(photos):
                with cols[i % len(cols)]:
                    try:
                        st.image(photo["bytes"], use_container_width=True)
                    except Exception:
                        st.caption(f"foto {i + 1}")
                    if st.button(
                        f"× {i + 1}",
                        key=f"fridge_photo_rm_{i}_{photo.get('fp', i)}",
                        use_container_width=True,
                    ):
                        keep = [p for j, p in enumerate(_fridge_photos()) if j != i]
                        st.session_state.fridge_photos = keep
                        st.rerun()
                        return
            if st.button(t("fridge_clear_photos"), use_container_width=True, key="fridge_clear_photos"):
                st.session_state.fridge_photos = []
                st.rerun()
                return

        with st.expander(t("fridge_upload"), expanded=False):
            uploads = st.file_uploader(
                t("fridge_upload"),
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="fridge_uploads",
                label_visibility="collapsed",
            )
            if uploads:
                for f in list(uploads)[: fr.MAX_PHOTOS]:
                    try:
                        _fridge_add_photo(
                            f.getvalue(),
                            getattr(f, "type", None) or "image/jpeg",
                        )
                    except Exception:
                        continue

        if st.button(t("fridge_scan"), type="primary", use_container_width=True, key="fridge_scan_btn"):
            photos = _fridge_photos()
            # Fallback: single live camera frame if list empty
            if not photos:
                cam_b = st.session_state.get("fridge_cam_bytes")
                if isinstance(cam_b, (bytes, bytearray)) and len(cam_b) > 20:
                    _fridge_add_photo(
                        bytes(cam_b),
                        str(st.session_state.get("fridge_cam_mime") or "image/jpeg"),
                    )
                    photos = _fridge_photos()
            blobs = [p["bytes"] for p in photos if p.get("bytes")][: fr.MAX_PHOTOS]
            mimes = [str(p.get("mime") or "image/jpeg") for p in photos[: len(blobs)]]
            if not blobs:
                st.warning(t("fridge_need_photo"))
            elif not key_ok:
                st.error(t("fridge_api_missing"))
            else:
                t0 = time.time()
                with st.spinner(t("fridge_scanning")):
                    try:
                        invent = fr.invent_from_images(
                            blobs,
                            api_key=api_key,
                            language=st.session_state.get("language", "sv"),
                            mime_types=mimes,
                        )
                    except fr.FridgeVisionError as exc:
                        elapsed = time.time() - t0
                        log.error("fridge invent UI error (%.2fs): %s", elapsed, exc)
                        st.session_state._last_ui_error = f"{exc.code}: {exc}"
                        st.error(f"{t('fridge_vision_error')}: {exc}")
                        if debug:
                            dbg = fr.LAST_VISION_DEBUG or {}
                            st.caption(
                                f"{elapsed:.1f}s · status={dbg.get('http_status')} · "
                                f"model={dbg.get('model')} · endpoint={dbg.get('endpoint')} · "
                                f"images={dbg.get('image_bytes')}"
                            )
                            if exc.raw:
                                st.caption(html.escape(str(exc.raw)[:280]))
                        if st.button(t("fridge_manual"), use_container_width=True, key="fridge_manual_btn"):
                            st.session_state.fridge_inventory = []
                            st.session_state.fridge_step = "confirm"
                            st.rerun()
                        nav()
                        return
                elapsed = time.time() - t0
                dbg = fr.LAST_VISION_DEBUG or {}
                if not invent or not dbg.get("http_status"):
                    st.error(t("fridge_vision_error"))
                    if debug:
                        st.caption(
                            f"anropet verkar inte ha gått iväg "
                            f"({elapsed:.2f}s, status={dbg.get('http_status')})."
                        )
                    nav()
                    return
                st.session_state.fridge_inventory = invent
                st.session_state.fridge_step = "confirm"
                st.session_state["fridge_last_scan_secs"] = elapsed
                st.rerun()
                return
        if st.button(t("home"), use_container_width=True, key="fridge_home_cap"):
            _clear_fridge_session()
            st.session_state.page = "home"
            st.rerun()
        nav()
        return

    # ----- confirm inventory -----
    inventory = list(st.session_state.get("fridge_inventory") or [])
    names = fr.names_only(inventory)
    secs = st.session_state.get("fridge_last_scan_secs")
    if secs is not None and names:
        st.caption(t("fridge_scan_took").format(secs=f"{float(secs):.1f}", n=len(names)))
    if not names:
        st.info(t("fridge_empty_scan"))
    else:
        st.markdown(
            f'<p class="oc-tagline" style="font-size:1.05rem">'
            f'{html.escape(t("fridge_confirm_title"))}: '
            f'{html.escape(", ".join(names))}.</p>',
            unsafe_allow_html=True,
        )
        st.caption(t("fridge_confirm_q"))

    # Editable chips — remove per item
    if names:
        cols = st.columns(min(3, max(1, len(names))))
        for i, name in enumerate(names):
            with cols[i % len(cols)]:
                if st.button(
                    f"× {name}",
                    key=f"fridge_rm_{i}_{name}",
                    use_container_width=True,
                ):
                    st.session_state.fridge_inventory = [
                        x
                        for x in inventory
                        if fr.normalize_name(
                            x.get("name") if isinstance(x, dict) else str(x)
                        )
                        != name
                    ]
                    st.rerun()
                    return

    add_cols = st.columns([3, 1])
    with add_cols[0]:
        new_item = st.text_input(
            t("fridge_add"),
            key="fridge_add_input",
            placeholder=t("fridge_add_placeholder"),
            label_visibility="collapsed",
        )
    with add_cols[1]:
        if st.button(t("fridge_add"), use_container_width=True, key="fridge_add_btn"):
            n = fr.normalize_name(new_item or "")
            if n and n not in names:
                inventory = list(inventory)
                inventory.append({"name": n, "confidence": 1.0})
                st.session_state.fridge_inventory = inventory
                st.rerun()
                return

    # HARD: never decide on empty inventory (blocked "Värm en rest" leak via meal templates)
    confirm_ready = bool(names)
    if st.button(
        t("fridge_confirm"),
        type="primary",
        use_container_width=True,
        key="fridge_confirm_btn",
        disabled=not confirm_ready,
    ):
        confirmed = fr.names_only(st.session_state.get("fridge_inventory") or [])
        if not confirmed:
            st.warning(t("fridge_need_items"))
        else:
            st.session_state.fridge_inventory = [
                {"name": n, "confidence": 1.0} for n in confirmed
            ]
            st.session_state.fridge_mode = True
            st.session_state.last_domain_hint = "food"
            import food_domain as fd

            if st.session_state.get("food_meal_type") not in fd.MEAL_TYPES:
                st.session_state.food_meal_type = fd.default_meal_type()
            q = (
                "Vad ska jag laga av det som finns i kylen?"
                if st.session_state.get("language", "sv") == "sv"
                else "What should I cook from what’s in the fridge?"
            )
            run_decision(question=q, domain_hint="food", reroll=False, via_router=False)
            return
    if not confirm_ready:
        st.caption(t("fridge_need_items"))

    if st.button(t("fridge_scan"), use_container_width=True, key="fridge_rescan"):
        st.session_state.fridge_step = "capture"
        st.rerun()
        return
    if st.button(t("home"), use_container_width=True, key="fridge_home_conf"):
        _clear_fridge_session()
        st.session_state.page = "home"
        st.rerun()
    nav()


def page_clothes_occasion() -> None:
    """One-tap 'Vart ska du?' — primary input before any clothes decision."""
    import clothes_domain as cd
    from datetime import datetime

    render_top_chrome()
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("occasion_title"))}</p>',
        unsafe_allow_html=True,
    )
    st.caption(t("occasion_hint"))

    language = st.session_state.get("language", "sv")
    now = datetime.now().astimezone()
    hour = now.hour
    remembered = (st.session_state.get("occasion_by_hour") or {}).get(str(hour))
    preselect = remembered or cd.default_occasion(hour, weekday=now.weekday() < 5)

    # Visible chip buttons (CSS targets horizontal blocks — not ghost secondary links)
    cols = st.columns(2)
    for i, key in enumerate(cd.OCCASION_ORDER):
        label = cd.occasion_label(key, language)
        is_sel = key == preselect
        with cols[i % 2]:
            if st.button(
                f"● {label}" if is_sel else label,
                key=f"occasion_btn_{key}",
                use_container_width=True,
                type="primary" if is_sel else "secondary",
            ):
                hist = dict(st.session_state.get("occasion_by_hour") or {})
                hist[str(hour)] = key
                st.session_state.occasion_by_hour = hist
                st.session_state.clothes_occasion = key
                pending = (
                    st.session_state.get("pending_clothes_question")
                    or st.session_state.get("last_question")
                    or pipeline._default_question(
                        "clothes", st.session_state.get("language", "sv")
                    )
                )
                st.session_state.last_domain_hint = "clothes"
                run_decision(
                    question=pending,
                    domain_hint="clothes",
                    reroll=False,
                    via_router=False,
                )

    if st.button(t("home"), use_container_width=True, key="occasion_home"):
        st.session_state.page = "home"
        st.session_state.clothes_occasion = None
        st.rerun()
    nav()


def page_ambiguous() -> None:
    render_top_chrome()
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("ambiguous"))}</p>',
        unsafe_allow_html=True,
    )
    domains = ("food", "clothes", "movie", "workout", "weekend", "other")
    st.markdown('<div class="oc-chip-row" aria-hidden="true"></div>', unsafe_allow_html=True)
    choice = st.pills(
        "ambiguous_pick",
        options=list(domains),
        format_func=lambda d: t("other") if d == "other" else domain_label(d),
        selection_mode="single",
        key="ambig_domain_pills",
        label_visibility="collapsed",
    )
    prev = st.session_state.get("_ambig_domain_pills_prev")
    if choice and choice != prev:
        st.session_state._ambig_domain_pills_prev = choice
        _pick_ambiguous_domain(str(choice))
    if st.button(t("home"), use_container_width=True):
        st.session_state.page = "home"
        st.session_state.pending_free_text = None
        st.rerun()
    nav()


def _ensure_movie_chips_defaults() -> None:
    """Infer format + mood once — confirmable on the result card."""
    import movie_domain as md

    history: list[dict[str, Any]] = []
    uid = st.session_state.get("user_id")
    if uid:
        try:
            history = db.list_decisions(str(uid), domain="movie", limit=40)
        except Exception:
            history = []
    in_prog = md.find_in_progress_series(history)
    st.session_state.movie_in_progress_series = in_prog
    if st.session_state.get("movie_format") not in md.FORMATS:
        st.session_state.movie_format = md.default_format(in_progress_series=in_prog)
    if st.session_state.get("movie_mood") not in md.MOODS:
        st.session_state.movie_mood = md.default_mood(history=history)


def render_meal_type_chips(cur: dict[str, Any]) -> None:
    """Meal type chooser above the food decision — st.pills (visible on Cloud)."""
    import food_domain as fd

    language = st.session_state.get("language", "sv")
    current = (
        _as_dict(cur.get("context")).get("meal_type")
        or st.session_state.get("food_meal_type")
        or fd.default_meal_type()
    )
    if current not in fd.MEAL_TYPES:
        current = fd.default_meal_type()
    st.session_state.food_meal_type = current

    # Session-state only (no default=) — avoids Streamlit warning and overwrite races
    if st.session_state.get("meal_pills") not in fd.MEAL_TYPES:
        st.session_state.meal_pills = current

    st.markdown(
        f'<p class="oc-sec-label">{html.escape("Måltid" if language == "sv" else "Meal")}</p>',
        unsafe_allow_html=True,
    )
    choice = st.pills(
        "meal_pills",
        options=list(fd.MEAL_ORDER),
        format_func=lambda k: fd.meal_label(k, language),
        selection_mode="single",
        key="meal_pills",
        label_visibility="collapsed",
    )
    if choice is None:
        choice = current
    if choice != current:
        st.session_state.food_meal_type = choice
        st.session_state.accepted = False
        pending = (
            st.session_state.get("last_question")
            or pipeline._default_question(
                "food", st.session_state.get("language", "sv")
            )
        )
        st.session_state.last_domain_hint = "food"
        run_decision(
            question=pending,
            domain_hint="food",
            reroll=False,
            via_router=False,
        )


def render_movie_format_mood_chips(cur: dict[str, Any]) -> None:
    """Two pill rows above the movie decision: Format + Läge (mood)."""
    import movie_domain as md

    language = st.session_state.get("language", "sv")
    ctx = _as_dict(cur.get("context"))
    in_prog = (
        ctx.get("in_progress_series")
        or st.session_state.get("movie_in_progress_series")
        or None
    )
    if in_prog:
        st.session_state.movie_in_progress_series = in_prog

    current_fmt = md.normalize_format(
        ctx.get("format") or st.session_state.get("movie_format")
    )
    current_mood = md.normalize_mood(
        ctx.get("mood") or st.session_state.get("movie_mood")
    )
    st.session_state.movie_format = current_fmt
    st.session_state.movie_mood = current_mood

    if st.session_state.get("movie_format_pills") not in md.FORMATS:
        st.session_state.movie_format_pills = current_fmt
    if st.session_state.get("movie_mood_pills") not in md.MOODS:
        st.session_state.movie_mood_pills = current_mood

    st.markdown(
        f'<p class="oc-sec-label">{html.escape("Format" if language == "sv" else "Format")}</p>',
        unsafe_allow_html=True,
    )
    fmt_choice = st.pills(
        "movie_format_pills",
        options=list(md.FORMAT_ORDER),
        format_func=lambda k: md.format_label(
            k, language, in_progress_series=in_prog if k == "avsnitt" else None
        ),
        selection_mode="single",
        key="movie_format_pills",
        label_visibility="collapsed",
    )
    st.markdown(
        f'<p class="oc-sec-label">{html.escape("Läge" if language == "sv" else "Mood")}</p>',
        unsafe_allow_html=True,
    )
    mood_choice = st.pills(
        "movie_mood_pills",
        options=list(md.MOOD_ORDER),
        format_func=lambda k: md.mood_label(k, language),
        selection_mode="single",
        key="movie_mood_pills",
        label_visibility="collapsed",
    )

    fmt_choice = current_fmt if fmt_choice is None else fmt_choice
    mood_choice = current_mood if mood_choice is None else mood_choice
    if fmt_choice != current_fmt or mood_choice != current_mood:
        st.session_state.movie_format = md.normalize_format(fmt_choice)
        st.session_state.movie_mood = md.normalize_mood(mood_choice)
        st.session_state.accepted = False
        pending = (
            st.session_state.get("last_question")
            or pipeline._default_question(
                "movie", st.session_state.get("language", "sv")
            )
        )
        st.session_state.last_domain_hint = "movie"
        run_decision(
            question=pending,
            domain_hint="movie",
            reroll=False,
            via_router=False,
        )


def page_not_a_decision() -> None:
    render_top_chrome()
    cur = st.session_state.current or {}
    msg = cur.get("ui_message") or t("not_a_decision")
    st.markdown(f'<div class="oc-refuse">{html.escape(msg)}</div>', unsafe_allow_html=True)
    if st.button(t("home"), use_container_width=True):
        st.session_state.page = "home"
        st.rerun()
    nav()


def page_result() -> None:
    render_top_chrome()
    cur = st.session_state.get("current") or {}
    if not isinstance(cur, dict):
        cur = {}
    # Normalize context once — Cloud/Supabase may leave a JSON string
    ctx_norm = _as_dict(cur.get("context"))
    if cur.get("context") is not ctx_norm:
        cur = dict(cur)
        cur["context"] = ctx_norm
        st.session_state.current = cur
    language = st.session_state.get("language", "sv")
    accepted = bool(st.session_state.get("accepted") or cur.get("accepted"))
    reroll_locked = bool(cur.get("locked"))
    # Show lock card when user accepted OR max-reroll locked (no more "Nytt förslag")
    show_lock_card = accepted or reroll_locked
    # Keep session mirrors aligned
    if cur.get("decision_id") is not None and st.session_state.get("decision_id") is None:
        st.session_state.decision_id = cur.get("decision_id")

    if cur.get("refused"):
        msg = cur.get("refusal_message") or t("refuse")
        st.markdown(f'<div class="oc-refuse">{html.escape(msg)}</div>', unsafe_allow_html=True)
        if st.button(t("home"), use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        nav()
        return

    suggestion = str(cur.get("suggestion") or "")
    justification = str(cur.get("justification") or "")
    domain = cur.get("domain") or ""
    reroll_index = int(cur.get("reroll_index") or 0)
    food_cook = _is_food_cook(cur)

    if show_lock_card:
        share_corner = _safe_decision_share_button_html(cur, key="share_lock_icon")
        title = (
            t("locked_title").format(suggestion=suggestion)
            if accepted
            else suggestion
        )
        if accepted:
            body = ""
        else:
            body = f"<p>{html.escape(t('lock_msg').format(suggestion=suggestion))}</p>"
        if domain == "movie":
            ctx_l = _as_dict(cur.get("context"))
            lock_label_html = f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
            lock_body_html = None
            if body:
                lock_body_html = body
            elif accepted and justification:
                lock_body_html = f"<p>{html.escape(justification)}</p>"
            _paint_html(
                _render_movie_card_html(
                    language=language,
                    suggestion=title,
                    justification=justification,
                    ctx=ctx_l,
                    lock_label_html=lock_label_html,
                    lock_body_html=lock_body_html,
                    share_corner_html=share_corner,
                )
            )
        elif domain == "food":
            ctx_l = _as_dict(cur.get("context"))
            lock_label_html = f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
            lock_body_html = None
            if body:
                lock_body_html = body
            elif accepted and justification:
                lock_body_html = f"<p>{html.escape(justification)}</p>"
            _paint_html(
                _render_food_card_html(
                    language=language,
                    suggestion=suggestion,
                    justification=justification,
                    ctx=ctx_l,
                    lock_label_html=lock_label_html,
                    lock_body_html=lock_body_html,
                    share_corner_html=share_corner,
                )
            )
        else:
            _paint_html(
                f'<div class="oc-decision">'
                f"{share_corner}"
                f'<div class="label">{html.escape(domain_label(domain))}</div>'
                f"<h1>{html.escape(title)}</h1>"
                f"{body}"
                f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
                f"</div>"
            )
        if food_cook:
            ctx_l = _as_dict(cur.get("context"))
            fridge_locked = str(ctx_l.get("source") or "") == "fridge_photo"
            mt = ctx_l.get("meal_type") or st.session_state.get("food_meal_type")
            show_shop = False
            if not fridge_locked:
                try:
                    import food_domain as fd

                    show_shop = fd.show_shopping(str(mt or "middag"))
                except Exception:
                    show_shop = True
            if fridge_locked:
                has_recipe = bool(ctx_l.get("recipe"))
                if has_recipe:
                    if st.button(
                        cur.get("execution_label") or t("fridge_cook"),
                        type="primary",
                        use_container_width=True,
                        key="fridge_reopen",
                    ):
                        open_execute_now(cur)
                elif st.button(
                    t("fridge_shop_alt"),
                    type="primary",
                    use_container_width=True,
                    key="fridge_shop_reopen",
                ):
                    st.session_state.fridge_mode = False
                    st.session_state.page = "home"
                    st.rerun()
            elif show_shop:
                if st.button(
                    t("handla_laga"),
                    type="primary",
                    use_container_width=True,
                    key="handla_reopen",
                ):
                    open_execute_now(cur)
            else:
                # Frukost / kvällsmål — reopen recipe view (no shopping list)
                label = cur.get("execution_label") or (
                    "Ät nu" if language == "sv" else "Eat now"
                )
                if st.button(label, type="primary", use_container_width=True, key="eat_reopen"):
                    open_execute_now(cur)
        else:
            exec_url = cur.get("execution_url")
            exec_label = cur.get("execution_label") or t("do_it")
            if exec_url:
                st.link_button(exec_label, exec_url, use_container_width=True, type="primary")
            elif (cur.get("domain") or "") == "workout" or cur.get("execution_type") == "workout":
                if st.button(
                    exec_label,
                    type="primary",
                    use_container_width=True,
                    key="do_it_locked",
                    on_click=_cb_open_execute,
                ):
                    open_execute_now(cur)
            elif st.button(exec_label, type="primary", use_container_width=True, key="do_it_locked"):
                on_accept_primary(cur)
        if st.button(t("home"), key="back_home_locked", type="secondary", use_container_width=True):
            _go_home_chooser()
        nav()
        return

    # Unlocked decision card — share icon top-right on every domain
    ctx = _as_dict(cur.get("context"))
    fridge_mode = str(ctx.get("source") or "") == "fridge_photo"
    share_corner = _safe_decision_share_button_html(cur, key="share_card_icon")
    # Food: meal-type chips ABOVE the decision (not for fridge — inventory is the constraint)
    if domain == "food" and not accepted and not fridge_mode:
        render_meal_type_chips(cur)
    # Movie: format + mood chips ABOVE the decision (two rows max — never a third)
    if domain == "movie" and not accepted:
        render_movie_format_mood_chips(cur)

    if domain == "movie":
        _paint_html(
            _render_movie_card_html(
                language=language,
                suggestion=suggestion,
                justification=justification,
                ctx=ctx,
                share_corner_html=share_corner,
            )
        )
    elif domain == "food":
        # Pre-lock: sell the decision — image + title + justification + meta only
        _paint_html(
            _render_food_card_html(
                language=language,
                suggestion=suggestion,
                justification=justification,
                ctx=ctx,
                share_corner_html=share_corner,
            )
        )
    else:
        _paint_html(
            f'<div class="oc-decision">'
            f"{share_corner}"
            f'<div class="label">{html.escape(domain_label(domain))}</div>'
            f"<h1>{html.escape(suggestion)}</h1>"
            f"<p>{html.escape(justification)}</p>"
            f"</div>"
        )
    render_reroll_dots(reroll_index)

    # Shopping list + recipe live on execute only — never on pre-lock food card
    if domain != "food":
        exec_detail = ctx.get("execution_detail")
        if exec_detail:
            st.markdown(
                f'<p class="oc-meta">{html.escape(str(exec_detail))}</p>',
                unsafe_allow_html=True,
            )

    if food_cook and fridge_mode:
        # Cook from inventory — recipe execute, no shopping list
        empty_fallback = bool(ctx.get("offers_shopping")) and not ctx.get("recipe")
        if not empty_fallback:
            label = cur.get("execution_label") or t("fridge_cook")
            if st.button(
                label,
                type="primary",
                use_container_width=True,
                key="fridge_cook_accept",
            ):
                open_execute_now(cur)
        if ctx.get("offers_shopping"):
            if st.button(
                t("fridge_shop_alt"),
                type="secondary" if not empty_fallback else "primary",
                use_container_width=True,
                key="fridge_shop_escape",
            ):
                st.session_state.fridge_mode = False
                st.session_state.fridge_inventory = []
                st.session_state.accepted = False
                run_decision(
                    question="",
                    domain_hint="food",
                    reroll=False,
                    via_router=False,
                )
    elif food_cook and not fridge_mode:
        # Pre-lock primary: lock the decision (details live on execute)
        if st.button(
            t("food_choose"),
            type="primary",
            use_container_width=True,
            key="food_go_for_it",
        ):
            on_accept_food_and_execute(cur)
    else:
        # Shared accept for clothes / movie / weekend; workout opens execute player
        exec_label = cur.get("execution_label") or t("do_it")
        if domain == "workout" or cur.get("execution_type") == "workout":
            if st.button(
                exec_label,
                type="primary",
                use_container_width=True,
                key="do_it_primary",
                on_click=_cb_open_execute,
            ):
                open_execute_now(cur)
        elif st.button(exec_label, type="primary", use_container_width=True, key="do_it_primary"):
            on_accept_primary(cur)

    # Secondary: reroll — hidden once accepted (lock card branch above)
    st.markdown('<div class="oc-link-wrap"></div>', unsafe_allow_html=True)
    if st.button(t("new"), type="secondary", use_container_width=True, key="reroll_link"):
        via = bool(cur.get("route") or st.session_state.get("route_log_id"))
        run_decision(
            question=st.session_state.get("last_question") or "",
            domain_hint=st.session_state.get("last_domain_hint") or cur.get("domain"),
            reroll=True,
            via_router=via,
        )

    if st.button(t("home"), key="back_home", type="secondary", use_container_width=True):
        _go_home_chooser()
    nav()


def _inject_wake_lock() -> None:
    """Best-effort Screen Wake Lock — fully reliable only in PWA/native."""
    import streamlit.components.v1 as components

    components.html(
        """
        <script>
        (async () => {
          try {
            if (navigator.wakeLock) {
              await navigator.wakeLock.request('screen');
            }
          } catch (e) {}
        })();
        </script>
        """,
        height=0,
    )


def _start_timer(seconds: int) -> None:
    import time as _time

    sec = max(1, int(seconds))
    st.session_state.workout_timer_total = sec
    st.session_state.workout_timer_end = _time.time() + sec


def _timer_remaining() -> int:
    import time as _time

    end = st.session_state.get("workout_timer_end")
    if not end:
        return 0
    return max(0, int(round(float(end) - _time.time())))


def _advance_workout_after_block(workout: dict[str, Any]) -> None:
    """Move to next set, rest, next block, or done."""
    import workout_domain as wd

    blocks = workout.get("blocks") or []
    bi = int(st.session_state.get("workout_block_i") or 0)
    si = int(st.session_state.get("workout_set_i") or 0)
    if bi >= len(blocks):
        st.session_state.workout_phase = "done"
        st.session_state.workout_timer_end = None
        return
    block = blocks[bi]
    sets = max(1, int(block.get("sets") or 1))
    rest = max(0, int(block.get("rest_seconds") or 0))
    # Finished a set
    if si + 1 < sets:
        st.session_state.workout_set_i = si + 1
        if rest > 0:
            st.session_state.workout_phase = "rest"
            _start_timer(rest)
        else:
            st.session_state.workout_phase = "play"
            _begin_block_work(block)
        return
    # Next block
    st.session_state.workout_block_i = bi + 1
    st.session_state.workout_set_i = 0
    if st.session_state.workout_block_i >= len(blocks):
        st.session_state.workout_phase = "done"
        st.session_state.workout_timer_end = None
        return
    st.session_state.workout_phase = "play"
    _begin_block_work(blocks[st.session_state.workout_block_i])


def _begin_block_work(block: dict[str, Any]) -> None:
    if (block.get("type") or "reps") == "time":
        _start_timer(int(block.get("seconds") or 30))
    else:
        st.session_state.workout_timer_end = None


def render_workout_progress(blocks: list, bi: int) -> None:
    dots = []
    for i, _ in enumerate(blocks):
        cls = "used" if i < bi else ("" if i > bi else "current")
        dots.append(f'<i class="{cls}"></i>')
    st.markdown(
        f'<div class="oc-rerolls" aria-label="progress">{"".join(dots)}</div>',
        unsafe_allow_html=True,
    )


def render_workout_overview(workout: dict[str, Any], language: str) -> None:
    import workout_domain as wd

    w = wd.finalize_workout(workout, language=language)
    title = w["title"]
    if title:
        title = title[:1].upper() + title[1:]
    st.markdown(
        f'<div class="oc-decision" style="padding:1.4rem 1.2rem 1.2rem;margin-bottom:0.9rem">'
        f'<div class="label">{html.escape(domain_label("workout"))}</div>'
        f'<h1 style="font-size:1.55rem">{html.escape(title)}</h1>'
        f'<p>{html.escape(str(w["total_minutes"]))} min</p>'
        f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
    rows = []
    for b in w["blocks"]:
        rows.append(
            f'<li><strong>{html.escape(str(b["name"]))}</strong> '
            f'<span style="color:#6B6B76">{html.escape(wd.block_duration_label(b, language))}</span></li>'
        )
    st.markdown(
        f'<div class="oc-shop"><div class="oc-shop-title">{html.escape(t("workout_overview"))}</div>'
        f'<ul>{"".join(rows)}</ul></div>',
        unsafe_allow_html=True,
    )
    st.caption(t("workout_awake_note"))
    if st.button(t("workout_go"), type="primary", use_container_width=True, key="wo_go"):
        # Persist accept here (after overview is already visible) so Starta never blocks
        _flush_db_accept()
        st.session_state.workout_phase = "play"
        st.session_state.workout_block_i = 0
        st.session_state.workout_set_i = 0
        _begin_block_work(w["blocks"][0])
        st.rerun()


def render_workout_player(workout: dict[str, Any], language: str) -> None:
    import workout_domain as wd
    from datetime import timedelta

    w = wd.finalize_workout(workout, language=language)
    blocks = w["blocks"]
    bi = int(st.session_state.get("workout_block_i") or 0)
    si = int(st.session_state.get("workout_set_i") or 0)
    phase = st.session_state.get("workout_phase") or "play"

    if bi >= len(blocks):
        st.session_state.workout_phase = "done"
        st.rerun()
        return

    _inject_wake_lock()
    render_workout_progress(blocks, bi)
    block = blocks[bi]
    sets = max(1, int(block.get("sets") or 1))

    if phase == "rest":
        remaining = _timer_remaining()
        st.markdown(
            f'<div class="oc-decision">'
            f'<div class="label">{html.escape(t("workout_rest"))}</div>'
            f'<h1 style="font-size:3rem">{remaining}s</h1>'
            f"<p>{html.escape(str(block.get('name')))} · set {si + 1}/{sets}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

        @st.fragment(run_every=timedelta(seconds=1))
        def _rest_tick() -> None:
            left = _timer_remaining()
            st.progress(1.0 - (left / max(1, int(st.session_state.get("workout_timer_total") or 1))))
            if left <= 0:
                st.session_state.workout_phase = "play"
                _begin_block_work(block)
                st.rerun()

        _rest_tick()
        if st.button(t("workout_skip"), use_container_width=True, key="wo_skip_rest"):
            st.session_state.workout_phase = "play"
            _begin_block_work(block)
            st.rerun()
        return

    # Active work
    cue = str(block.get("cue") or "")
    if (block.get("type") or "reps") == "time":
        remaining = _timer_remaining()
        if st.session_state.get("workout_timer_end") is None:
            _begin_block_work(block)
            remaining = _timer_remaining()
        st.markdown(
            f'<div class="oc-decision">'
            f'<div class="label">Set {si + 1}/{sets}</div>'
            f'<h1 style="font-size:2.2rem">{html.escape(str(block["name"]))}</h1>'
            f'<h1 style="font-size:3rem;margin:0.4rem 0">{remaining}s</h1>'
            f"<p>{html.escape(cue)}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )

        @st.fragment(run_every=timedelta(seconds=1))
        def _work_tick() -> None:
            left = _timer_remaining()
            total = max(1, int(st.session_state.get("workout_timer_total") or 1))
            st.progress(1.0 - (left / total))
            if left <= 0:
                _advance_workout_after_block(w)
                st.rerun()

        _work_tick()
        if st.button(t("workout_skip"), use_container_width=True, key="wo_skip_time"):
            _advance_workout_after_block(w)
            st.rerun()
    else:
        reps = int(block.get("reps") or 10)
        st.markdown(
            f'<div class="oc-decision">'
            f'<div class="label">Set {si + 1}/{sets}</div>'
            f'<h1 style="font-size:2.2rem">{html.escape(str(block["name"]))}</h1>'
            f'<h1 style="font-size:2.6rem;margin:0.4rem 0">{reps}</h1>'
            f"<p>{html.escape(cue)}</p>"
            f"</div>",
            unsafe_allow_html=True,
        )
        label = t("workout_next_set") if si + 1 < sets else t("workout_next")
        if st.button(label, type="primary", use_container_width=True, key="wo_next_reps"):
            _advance_workout_after_block(w)
            st.rerun()


def render_workout_done(workout: dict[str, Any], cur: dict[str, Any], language: str) -> None:
    import workout_domain as wd

    w = wd.finalize_workout(workout, language=language)
    mins = w["total_minutes"]
    title = t("workout_done_title")
    line = f"{title} {mins} minuter." if language == "sv" else f"{title} {mins} minutes."
    st.markdown(
        f'<div class="oc-decision"><h1 style="font-size:1.8rem">{html.escape(line)}</h1>'
        f'<p>{html.escape(t("workout_feedback_q"))}</p></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    did = _active_decision_id(cur)
    with c1:
        if st.button("👍", use_container_width=True, key="wo_up"):
            _record_workout_feel(did, positive=True, cur=cur)
            safe_toast(t("accepted"))
            st.session_state.page = "home"
            st.rerun()
    with c2:
        if st.button("👎", use_container_width=True, key="wo_down"):
            _record_workout_feel(did, positive=False, cur=cur)
            st.session_state.page = "home"
            st.rerun()


def _record_workout_feel(
    decision_id: int | None, *, positive: bool, cur: dict[str, Any]
) -> None:
    """Post-decision feedback into preference log (structure stays accepted)."""
    try:
        suggestion = str(cur.get("suggestion") or "").strip().lower()
        uid = st.session_state.get("user_id")
        if uid and suggestion:
            db.upsert_preference(
                str(uid),
                "workout",
                "suggestion",
                suggestion,
                1.0 if positive else -1.0,
            )
        # Mirror into session context for history visibility
        updated = dict(cur)
        ctx = _as_dict(updated.get("context"))
        ctx["post_feedback"] = "up" if positive else "down"
        updated["context"] = ctx
        st.session_state.current = updated
    except Exception as exc:
        log.warning("workout feedback failed: %s", exc)


def page_execute() -> None:
    """Execution view: food shopping/recipe OR workout player."""
    # Clear sticky error so Handla always gets a clean paint
    st.session_state.ui_error = None

    render_top_chrome()
    cur = st.session_state.get("current") or {}
    if not isinstance(cur, dict) or not cur.get("suggestion"):
        st.session_state.page = "home"
        st.rerun()
        return

    # Soft-lock if we landed here without accept flag (Cloud race)
    if not (st.session_state.get("accepted") or cur.get("accepted") or cur.get("locked")):
        try:
            _lock_current_locally(cur)
        except Exception:
            st.session_state.accepted = True

    _mark_execution_opened_for_current(cur if isinstance(cur, dict) else {})

    language = st.session_state.get("language", "sv")
    domain = (cur.get("domain") or "").strip()
    ctx = _as_dict(cur.get("context"))
    # Persist healed context so later renders never see a JSON string
    if cur.get("context") is not ctx:
        cur = dict(cur)
        cur["context"] = ctx
        st.session_state.current = cur

    # ----- Workout player -----
    if domain == "workout" or cur.get("execution_type") == "workout":
        try:
            import workout_domain as wd

            workout = wd.get_workout_from_decision(cur)
            if not workout:
                workout = wd.finalize_workout(
                    wd._match_template(str(cur.get("suggestion") or ""), language),
                    language=language,
                )
                ctx = dict(ctx)
                ctx["workout"] = workout
                cur = dict(cur)
                cur["context"] = ctx
                st.session_state.current = cur

            phase = st.session_state.get("workout_phase") or "overview"
            share_corner = _safe_decision_share_button_html(
                cur, key=f"share_wo_{phase}"
            )
            _paint_html(
                f'<div class="oc-decision oc-exec-lock">'
                f"{share_corner}"
                f'<h1>{html.escape(str(cur.get("suggestion") or ""))}</h1>'
                f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
                f"</div>"
            )
            if phase == "overview":
                render_workout_overview(workout, language)
            elif phase == "done":
                render_workout_done(workout, cur, language)
            else:
                render_workout_player(workout, language)

            if phase != "done" and st.button(
                t("back_to_decision"),
                type="secondary",
                use_container_width=True,
                key="exec_back_wo",
            ):
                st.session_state.page = "result"
                st.rerun()
            nav()
            try:
                _flush_db_accept()
            except Exception:
                pass
            return
        except BaseException as exc:
            if _is_streamlit_control_flow(exc):
                raise
            log.exception("workout execute failed: %s", exc)
            st.markdown(
                f'<div class="oc-error"><p>{html.escape(t("error_friendly"))}</p></div>',
                unsafe_allow_html=True,
            )
            st.caption(html.escape(f"{type(exc).__name__}: {exc}")[:180])
            if st.button(t("retry"), type="primary", use_container_width=True, key="wo_exec_retry"):
                _reset_workout_player()
                st.rerun()
            if st.button(t("home"), use_container_width=True, key="wo_exec_home"):
                _go_home_chooser()
            nav()
            return

    # ----- Food shopping + recipe (minimal — never escalates to ui_error) -----
    suggestion = str(cur.get("suggestion") or "")
    justification = str(cur.get("justification") or "")
    share_corner = _safe_decision_share_button_html(cur, key="share_execute")
    did = cur.get("decision_id") or st.session_state.get("decision_id")
    is_fav = bool(cur.get("favorite"))
    if did and not is_fav:
        # Heal favorite flag from DB if session was restored without it
        try:
            rows = _list_decisions(
                str(st.session_state.user_id), favorite=True, limit=80
            )
            is_fav = any(int(r.get("id") or 0) == int(did) for r in rows)
            cur["favorite"] = is_fav
            st.session_state.current = cur
        except Exception:
            pass
    with st.container(key="exec_food_host"):
        _render_favorite_toggle(int(did) if did else None, is_favorite=is_fav)
        # Same dish image as pre-lock card — not a title-only stub
        _paint_html(
            _render_food_card_html(
                language=language,
                suggestion=suggestion,
                justification=justification,
                ctx=ctx,
                lock_label_html=(
                    f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
                ),
                share_corner_html=share_corner,
            )
        )

    shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
    # Cloud/Supabase may leave recipe as a JSON string — heal before use
    recipe = ctx.get("recipe")
    if isinstance(recipe, str):
        recipe = _as_dict(recipe) or None
    if not isinstance(recipe, dict):
        recipe = None
    if not recipe and shop and isinstance(shop.get("recipe"), dict):
        recipe = shop.get("recipe")
    elif not recipe and shop and isinstance(shop.get("recipe"), str):
        recipe = _as_dict(shop.get("recipe")) or None

    active_mins: int | None = None
    if isinstance(recipe, dict) and recipe.get("active_minutes") is not None:
        try:
            active_mins = int(recipe["active_minutes"])
        except (TypeError, ValueError):
            active_mins = None
    if active_mins is None:
        try:
            active_mins = int(ctx.get("max_active_minutes") or 0) or None
        except (TypeError, ValueError):
            active_mins = None

    # ALWAYS materialize a valid structured recipe — never title-only stubs
    meal_type = str(
        ctx.get("meal_type")
        or st.session_state.get("food_meal_type")
        or "middag"
    )
    try:
        import food_domain as fd

        if fd.is_no_recipe_meal(
            suggestion,
            meta=_as_dict(ctx),
            execution={"type": cur.get("execution_type")},
        ):
            recipe = fd.reheat_execution_recipe(
                suggestion, language=st.session_state.get("language", "sv")
            )
            render_food_recipe(recipe)
            if st.button(
                t("back_to_decision"),
                type="secondary",
                use_container_width=True,
                key="exec_back_leftover",
            ):
                st.session_state.page = "result"
                st.rerun()
            nav()
            try:
                _flush_db_accept()
            except Exception:
                pass
            return
    except Exception as exc:
        log.warning("leftover execute shortcut failed: %s", exc)

    seed_ings: list[str] | None = None
    if isinstance(recipe, dict) and recipe.get("ingredient_lines"):
        seed_ings = [str(x) for x in recipe.get("ingredient_lines") or []]
    elif isinstance(recipe, dict) and recipe.get("ingredients"):
        seed_ings = [str(x) for x in recipe.get("ingredients") or []]
    elif isinstance(shop, dict) and shop.get("ingredients"):
        seed_ings = [str(x) for x in shop.get("ingredients") or []]
    if not seed_ings:
        try:
            import food_domain as fd

            seed_ings = fd.ingredient_hints_for(
                suggestion,
                meal_type,
                language=st.session_state.get("language", "sv"),
            ) or None
        except Exception:
            pass
    # Title-only stub seeds break validation — drop them
    if seed_ings and len(seed_ings) == 1:
        if seed_ings[0].strip().lower() == suggestion.strip().lower():
            seed_ings = None

    import shopping as shop_mod
    import shopping_compat as shop_compat

    # Prefer recipe/shopping already on the decision — do NOT re-call Grok here
    # (that was adding 45–90s after Handla & laga). Local catalog only as fill-in.
    has_usable_recipe = (
        isinstance(recipe, dict)
        and bool(recipe.get("steps"))
        and (
            bool(recipe.get("ingredient_lines") or recipe.get("ingredients"))
            or bool(seed_ings)
        )
    )
    if not has_usable_recipe or not shop:
        bundled_recipe, bundled_shop = shop_compat.resolve_meal_bundle(
            suggestion,
            meta={"meal_type": meal_type, "ingredients": seed_ings or []},
            meal_type=meal_type,
            language=st.session_state.get("language", "sv"),
            grok_api_key="",  # local/catalog only — keep Handla snappy
            include_shopping=True,
            active_minutes=active_mins,
        )
        if bundled_recipe and not has_usable_recipe:
            recipe = bundled_recipe
        if bundled_shop and not shop:
            shop = bundled_shop
    if isinstance(recipe, dict) and not shop:
        derived = shop_compat.shopping_from_recipe(recipe, suggestion=suggestion)
        if derived and derived.get("to_buy"):
            shop = derived

    # Persist rebuilt shopping onto the decision so accept/merge/Skapa lista see it
    if isinstance(shop, dict) and shop.get("to_buy"):
        cur = _store_shopping_on_current(shop)
        ctx = _as_dict(cur.get("context"))
        if isinstance(recipe, dict):
            ctx = dict(ctx)
            ctx["recipe"] = recipe
            cur = dict(cur)
            cur["context"] = ctx
            st.session_state.current = cur

    if not isinstance(recipe, dict) or not recipe.get("steps"):
        try:
            import recipe_engine as reng

            recipe = reng.materialize_recipe(
                suggestion,
                seed_ings,
                meal_type=meal_type,
                active_minutes=active_mins,
                language=st.session_state.get("language", "sv"),
                grok_api_key="",
                allow_llm=False,
            )
        except Exception as exc2:
            log.error("recipe catalog fallback failed: %s", exc2)
            recipe = shop_compat.resolve_meal_bundle(
                suggestion,
                meta={"meal_type": meal_type, "ingredients": seed_ings or []},
                meal_type=meal_type,
                language=st.session_state.get("language", "sv"),
                grok_api_key="",
                include_shopping=False,
                active_minutes=active_mins,
            )[0] or shop_mod.build_recipe(
                suggestion,
                seed_ings,
                meal_type=meal_type,
                active_minutes=active_mins,
                language=st.session_state.get("language", "sv"),
                grok_api_key="",
            )

    # Meta row: time · portions · nutrition (per portion)
    meta_bits: list[str] = []
    if isinstance(recipe, dict):
        try:
            import shopping as shopping_mod

            recipe = shopping_mod.ensure_recipe_nutrition(
                recipe,
                suggestion=suggestion,
                allow_estimate=True,
            )
        except Exception:
            pass
        mins = recipe.get("active_minutes") or recipe.get("total_minutes")
        if mins is not None:
            try:
                meta_bits.append(f"⏱ {t('recipe_mins').format(mins=int(mins))}")
            except Exception:
                pass
        portions = recipe.get("portioner") or recipe.get("portions")
        if portions:
            try:
                n = int(portions)
                if language == "en":
                    meta_bits.append(f"{n} servings")
                else:
                    meta_bits.append(f"{n} portioner")
            except (TypeError, ValueError):
                pass
        nut_line, has_nut = _nutrition_display_line(recipe)
        if has_nut:
            meta_bits.append(nut_line)
    if meta_bits:
        st.markdown(
            f'<div class="oc-exec-meta">{html.escape(" · ".join(meta_bits))}</div>',
            unsafe_allow_html=True,
        )

    did = _active_decision_id(cur)
    try:
        render_decision_shopping_added(
            shop,
            language,
            recipe=recipe if isinstance(recipe, dict) else None,
        )
    except Exception as exc:
        log.warning("shopping list render failed: %s", exc)

    ings_fallback = (
        list(recipe.get("ingredient_lines") or recipe.get("ingredients") or [])
        if isinstance(recipe, dict)
        else []
    )
    try:
        # Checklist IS the ingredient list — recipe card shows steps only
        render_food_recipe(
            recipe if isinstance(recipe, dict) else None,
            ings_fallback,
            include_ingredients=False,
        )
    except Exception as exc:
        log.warning("recipe render failed: %s", exc)
        steps = list((recipe or {}).get("steps") or []) if isinstance(recipe, dict) else []
        if steps:
            st.markdown("**" + t("steps_title") + "**")
            for i, step in enumerate(steps, 1):
                st.markdown(f"{i}. {step}")

    try:
        render_execute_sticky_cta(shop if isinstance(shop, dict) else None)
    except Exception as exc:
        log.warning("sticky CTA render failed: %s", exc)

    if st.button(
        t("back_to_decision"),
        type="secondary",
        use_container_width=True,
        key="exec_back",
    ):
        st.session_state.page = "result"
        st.rerun()
    nav()

    # Safety net if accept was deferred earlier in the page
    try:
        _flush_db_accept()
    except Exception as exc:
        log.warning("post-paint accept failed: %s", exc)


def page_lista() -> None:
    # Honour clear request before any widgets — set by Rensa klara form
    if st.session_state.pop("_lista_clear_request", False):
        ids = [
            int(i)
            for i in (st.session_state.pop("_lista_clear_ids", None) or [])
            if int(i) > 0
        ]
        if ids:
            n = _clear_done_shopping_items([{"id": i} for i in ids])
            try:
                safe_toast(f'{t("list_clear_done")} · {n}')
            except Exception:
                pass

    render_top_chrome()
    require_auth_context()
    head_l, head_r = st.columns([3, 1], gap="small")
    with head_l:
        st.markdown(
            f'<p class="oc-logo" style="font-size:1.35rem">{html.escape(t("list_title"))}</p>',
            unsafe_allow_html=True,
        )
    with head_r:
        try:
            render_share_list()
        except BaseException as exc:
            if _is_streamlit_control_flow(exc):
                raise
            log.exception("lista share failed: %s", exc)
    if st.session_state.guest_mode:
        st.caption(t("list_guest_login_hint"))
    with st.container(key="lista_add_row"):
        with st.form("shop_add_form", clear_on_submit=True):
            cols = st.columns([4, 1], gap="small")
            with cols[0]:
                added = st.text_input(
                    t("list_add_placeholder"),
                    label_visibility="collapsed",
                    key="shop_add_input",
                    placeholder=t("list_add_placeholder"),
                )
            with cols[1]:
                submitted = st.form_submit_button("＋", use_container_width=True)
            if submitted:
                uid = _shopping_list_user_id()
                if uid and str(added or "").strip():
                    try:
                        db.add_manual_shopping_item(
                            uid,
                            str(added).strip(),
                            grok_api_key=resolve_grok_api_key(),
                        )
                        st.session_state.shopping_list_cache = None
                    except Exception as exc:
                        log.warning("manual shopping add failed: %s", exc)
                    st.rerun()
    err = st.session_state.get("shopping_list_error")
    if err:
        st.warning(t("list_error"))
    items = _load_shopping_items()
    if not items:
        st.markdown(
            f'<p class="oc-meta">{html.escape(t("list_empty"))}</p>',
            unsafe_allow_html=True,
        )
        if st.button(t("home"), type="primary", use_container_width=True, key="lista_go_home"):
            _go_home_chooser()
            return
        if st.button(
            t("list_open_history"),
            type="secondary",
            use_container_width=True,
            key="lista_go_history",
        ):
            st.session_state.page = "history"
            st.rerun()
        nav()
        return
    render_persistent_shopping_list()
    nav()


def page_history() -> None:
    _ensure_db_api()
    render_top_chrome()
    require_auth_context()
    st.markdown(
        f'<p class="oc-logo" style="font-size:1.35rem">{html.escape(t("history_title"))}</p>',
        unsafe_allow_html=True,
    )
    fav_label = t("history_seg_favorites")
    hist_label = t("history_seg_history")
    with st.container(key="hist_seg"):
        seg = st.pills(
            "hist_seg",
            options=[fav_label, hist_label],
            selection_mode="single",
            default=hist_label,
            label_visibility="collapsed",
            key="history_segment",
        )
    show_favs = seg == fav_label

    if show_favs:
        rows = _list_decisions(
            st.session_state.user_id, favorite=True, limit=40
        )
        if not rows:
            st.info(t("history_favorites_empty"))
        else:
            for r in rows:
                rid = r.get("id")
                st.markdown(
                    _favorite_card_html(r, st.session_state.get("language", "sv")),
                    unsafe_allow_html=True,
                )
                cols = st.columns(2, gap="small")
                with cols[0]:
                    if rid is not None and st.button(
                        t("history_open"),
                        key=f"fav_open_{rid}",
                        use_container_width=True,
                        type="secondary",
                    ):
                        _restore_decision_from_row(r)
                        st.rerun()
                with cols[1]:
                    if rid is not None and st.button(
                        t("cook_tonight"),
                        key=f"fav_cook_{rid}",
                        use_container_width=True,
                        type="primary",
                    ):
                        _cook_favorite_tonight(r)
        nav()
        return

    st.markdown(
        f'<p class="oc-meta">{html.escape(t("history_hint"))}</p>',
        unsafe_allow_html=True,
    )
    if st.button(t("list_go"), type="secondary", use_container_width=True, key="hist_open_list"):
        st.session_state.page = "lista"
        st.rerun()
    rows = _list_decisions(st.session_state.user_id, limit=30)
    if not rows:
        st.info(t("history_empty"))
    else:
        for r in rows:
            rid = r.get("id")
            status = str(r.get("status") or "")
            status_lbl = _history_status_label(status)
            when = str(r.get("created_at") or "")
            if "T" in when:
                when = when.replace("T", " ")[:16]
            st.markdown(
                f'<div class="oc-hist"><strong>{html.escape(str(r.get("suggestion") or ""))}</strong>'
                f'<span>{html.escape(when)} · {html.escape(status_lbl)} · '
                f'{html.escape(domain_label(r.get("domain") or ""))}</span></div>',
                unsafe_allow_html=True,
            )
            if rid is not None and st.button(
                t("history_open"),
                key=f"hist_open_{rid}",
                use_container_width=True,
                type="secondary",
            ):
                _restore_decision_from_row(r)
                st.rerun()
    nav()


def page_profile() -> None:
    import json

    import clothes_domain as cd

    render_top_chrome()
    require_auth_context()
    st.markdown(
        f'<div class="oc-pro"><h2>{html.escape(t("pro_title"))}</h2>'
        f'<p>{html.escape(t("pro_desc"))}</p>'
        f'<div class="oc-price">{html.escape(t("pro_price"))}</div></div>',
        unsafe_allow_html=True,
    )
    import supabase_client as sb

    if st.session_state.user_email:
        st.caption(f"{t('logged_in_as')} {st.session_state.user_email}")
    elif st.session_state.guest_mode:
        st.caption("Guest / lokal demo")

    if sb.is_configured():
        st.caption(t("auth_cloud_ok"))
    else:
        st.caption(t("auth_cloud_off"))

    if st.session_state.guest_mode:
        st.caption(t("auth_login_prompt"))
        if sb.is_configured():
            if st.button(t("login_cta"), type="primary", use_container_width=True, key="profile_login"):
                _go_to_auth_page(mode="login")
                st.rerun()
        else:
            st.info(t("no_supabase"))

    # AI status — owner diagnostics. Makes silent LLM failure VISIBLE on device.
    try:
        import llm_config

        d = llm_config.DIAGNOSTICS
        if d.get("status") in ("ok", "override", "probe_partial"):
            st.caption(f"AI: {d.get('model')} ✓")
        elif d.get("status") == "no_key":
            st.caption("AI: offline — API-nyckel saknas")
        elif d.get("status") == "all_failed":
            st.caption(f"AI: offline — ingen modell svarade ({d.get('detail', '')[:120]})")
        else:
            st.caption("AI: ej testad ännu")
    except Exception:
        pass
    try:
        import subprocess

        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        if sha:
            st.caption(f"Build: {sha} · {BUILD_ID}")
        else:
            st.caption(f"Build: {BUILD_ID}")
    except Exception:
        st.caption(f"Build: {BUILD_ID}")

    user = db.ensure_user(st.session_state.user_id)
    if user.get("is_pro") or st.session_state.is_pro:
        st.success(t("pro_on"))
    else:
        if st.button(t("pro_cta"), type="primary", use_container_width=True):
            st.info("Stripe checkout — demo mode.")
        if st.button(t("pro_demo"), use_container_width=True):
            db.update_user(st.session_state.user_id, is_pro=1)
            st.session_state.is_pro = True
            st.rerun()

    # --- Clothes onboarding (section + sizes) — used by the clothes generator ---
    st.markdown(
        f'<p class="oc-logo" style="font-size:1.15rem;margin-top:1.4rem">'
        f'{html.escape(t("clothes_profile_title"))}</p>',
        unsafe_allow_html=True,
    )
    raw_profile = user.get("profile_json") or {}
    if isinstance(raw_profile, str):
        try:
            raw_profile = json.loads(raw_profile)
        except json.JSONDecodeError:
            raw_profile = {}
    ensured = cd.ensure_clothes_profile(raw_profile if isinstance(raw_profile, dict) else {})
    clothes = ensured.get("clothes") or {}

    section = st.selectbox(
        t("clothes_section"),
        options=["herr", "dam", "båda"],
        index=["herr", "dam", "båda"].index(str(clothes.get("section") or "båda")),
        key="prof_clothes_section",
    )
    st.caption(t("clothes_sizes"))
    c1, c2, c3 = st.columns(3)
    with c1:
        top = st.text_input("Topp", value=str((clothes.get("sizes") or {}).get("top") or "M"), key="prof_size_top")
    with c2:
        bottom = st.text_input(
            "Byxa",
            value=str((clothes.get("sizes") or {}).get("bottom") or "32"),
            key="prof_size_bottom",
        )
    with c3:
        shoes = st.text_input(
            "Skor",
            value=str((clothes.get("sizes") or {}).get("shoes") or "42"),
            key="prof_size_shoes",
        )
    if st.button(t("clothes_save"), use_container_width=True, key="save_clothes_profile"):
        new_profile = dict(ensured)
        new_profile["clothes"] = {
            **clothes,
            "section": section,
            "sizes": {"top": top.strip() or "M", "bottom": bottom.strip() or "32", "shoes": shoes.strip() or "42"},
            "onboarded": True,
            "retailers": clothes.get("retailers") or ["Zalando", "H&M", "Lindex"],
        }
        db.update_user(st.session_state.user_id, profile_json=new_profile)
        safe_toast(t("clothes_saved"))
        st.rerun()

    # --- Opt-in nutrition estimates (recipe view only) ---
    st.markdown(
        f'<p class="oc-logo" style="font-size:1.15rem;margin-top:1.4rem">'
        f'{html.escape(t("nutrition_section"))}</p>',
        unsafe_allow_html=True,
    )
    food_prof = dict((ensured if isinstance(ensured, dict) else {}).get("food") or {})
    show_nut = bool(food_prof.get("show_nutrition", True))
    st.caption(t("nutrition_hint"))
    if hasattr(st, "toggle"):
        new_show_nut = st.toggle(
            t("nutrition_title"),
            value=show_nut,
            key="prof_show_nutrition",
        )
    else:
        new_show_nut = st.checkbox(
            t("nutrition_title"),
            value=show_nut,
            key="prof_show_nutrition",
        )
    if new_show_nut != show_nut:
        new_profile = dict(ensured) if isinstance(ensured, dict) else {}
        food_row = dict(new_profile.get("food") or {})
        food_row["show_nutrition"] = bool(new_show_nut)
        new_profile["food"] = food_row
        db.update_user(st.session_state.user_id, profile_json=new_profile)
        safe_toast(t("nutrition_saved"))
        st.rerun()

    # --- GDPR: export + hard delete (Art. 17 / 20) ---
    import gdpr as gdpr_mod

    st.markdown(
        f'<p class="oc-logo" style="font-size:1.15rem;margin-top:1.4rem">'
        f'{html.escape(t("gdpr_title"))}</p>',
        unsafe_allow_html=True,
    )
    if st.session_state.guest_mode:
        st.caption(t("gdpr_guest_note"))
    st.caption(t("gdpr_export_hint"))
    if st.button(t("gdpr_export"), use_container_width=True, key="gdpr_export_btn"):
        try:
            payload = gdpr_mod.export_user_data(str(st.session_state.user_id))
            blob = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
            st.download_button(
                label=t("gdpr_export"),
                data=blob.encode("utf-8"),
                file_name=f"onechoice-data-{str(st.session_state.user_id)[:8]}.json",
                mime="application/json",
                use_container_width=True,
                key="gdpr_export_dl",
            )
        except Exception as exc:
            st.error(str(exc))

    if st.button(t("gdpr_delete"), use_container_width=True, key="gdpr_delete_btn"):
        st.session_state["gdpr_delete_pending"] = True
        st.rerun()
    if st.session_state.get("gdpr_delete_pending"):
        st.error(t("gdpr_delete_confirm"))
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("gdpr_delete_yes"), type="primary", use_container_width=True, key="gdpr_delete_yes"):
                try:
                    gdpr_mod.delete_user_account(
                        str(st.session_state.user_id),
                        access_token=st.session_state.get("access_token"),
                        refresh_token=st.session_state.get("refresh_token"),
                    )
                except Exception as exc:
                    st.error(str(exc))
                else:
                    db.clear_auth()
                    for key in (
                        "user_id",
                        "user_email",
                        "access_token",
                        "refresh_token",
                        "current",
                        "guest_mode",
                        "gdpr_delete_pending",
                        "fridge_photos",
                    ):
                        st.session_state[key] = None if key != "guest_mode" else False
                    st.session_state.page = "auth"
                    st.success(t("gdpr_delete_done"))
                    st.rerun()
        with c2:
            if st.button(t("home"), use_container_width=True, key="gdpr_delete_cancel"):
                st.session_state["gdpr_delete_pending"] = False
                st.rerun()

    privacy_url = gdpr_mod.privacy_policy_url() or "?privacy=1"
    st.markdown(
        f'<p style="text-align:center;margin:1rem 0 0.5rem">'
        f'<a href="{html.escape(privacy_url)}">{html.escape(t("privacy_link"))}</a></p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="oc-meta" style="text-align:center;margin:0 0 0.6rem">'
        'Filmdata från TMDB</p>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("access_token") and not st.session_state.guest_mode:
        import supabase_client as sb

        if st.button(t("logout"), use_container_width=True):
            sb.sign_out(st.session_state.access_token, st.session_state.refresh_token)
            _go_to_auth_page(mode="login")
            st.rerun()
    nav()


def page_privacy() -> None:
    """In-app privacy policy (Swedish). Override with PRIVACY_URL secret if hosted elsewhere."""
    render_top_chrome()
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("privacy_link"))}</p>',
        unsafe_allow_html=True,
    )
    path = Path(__file__).resolve().parent / "PRIVACY.md"
    if path.exists():
        st.markdown(path.read_text(encoding="utf-8"))
    else:
        st.info("Integritetspolicyn saknas i repot (PRIVACY.md).")
    if st.button(t("home"), use_container_width=True, key="privacy_home"):
        st.session_state.page = "home" if st.session_state.get("user_id") else "auth"
        try:
            del st.query_params["privacy"]
        except Exception:
            pass
        st.rerun()


def handle_query_params() -> None:
    qp = st.query_params
    _bootstrap_guest_session()

    privacy = _qp_one(qp.get("privacy"))
    if privacy in ("1", "true", "yes") or st.session_state.get("page") == "privacy":
        st.session_state.page = "privacy"

    # Public share landing — distribution channel; works without login
    share_tok = _qp_one(qp.get("share"))
    ref = _qp_one(qp.get("ref")) or "share"
    did_q = _qp_one(qp.get("decision_id"))
    if share_tok:
        row = db.get_public_share(share_tok)
        if row:
            st.session_state.shared_token = share_tok
            st.session_state.shared_payload = row.get("payload") or {}
            st.session_state.shared_ref = ref
            log_key = f"_share_logged_{share_tok}"
            if not st.session_state.get(log_key):
                try:
                    did_int = None
                    if did_q is not None:
                        try:
                            did_int = int(did_q)
                        except (TypeError, ValueError):
                            did_int = row.get("decision_id")
                    else:
                        did_int = row.get("decision_id")
                    db.log_share_open(share_tok, decision_id=did_int, ref=ref)
                    st.session_state[log_key] = True
                except Exception as exc:
                    log.exception("share open log failed: %s", exc)
            st.session_state.page = "shared"
            return
        try:
            del st.query_params["share"]
        except Exception:
            pass

    if st.session_state.page == "auth" and not st.session_state.user_id:
        # still allow language toggle on auth
        pass
    lang = _qp_one(qp.get("lang"))
    if lang in ("sv", "en"):
        st.session_state.language = lang
        if st.session_state.user_id:
            require_auth_context()
            try:
                db.update_user(st.session_state.user_id, language=lang)
            except Exception:
                pass
        try:
            del st.query_params["lang"]
        except Exception:
            pass
        st.rerun()

    if st.session_state.page == "auth" and not _is_authenticated() and not st.session_state.get("guest_mode"):
        return

    nav_q = _qp_one(qp.get("nav"))
    if nav_q in ("home", "lista", "history", "profile"):
        st.session_state.page = nav_q
        try:
            del st.query_params["nav"]
        except Exception:
            pass
        st.rerun()

    shop_toggle = _qp_one(qp.get("shop_toggle"))
    if shop_toggle:
        try:
            _optimistic_toggle_shopping_item(int(shop_toggle))
        except (TypeError, ValueError) as exc:
            log.warning("invalid shop_toggle %r: %s", shop_toggle, exc)
        for key in ("shop_toggle", "guest"):
            try:
                del st.query_params[key]
            except Exception:
                pass
        if st.session_state.get("guest_mode"):
            _set_guest_query_param()
        st.rerun()

    shop_check = _qp_one(qp.get("shop_check"))
    if shop_check is not None:
        try:
            idx = int(shop_check)
            did = _active_decision_id()
            _toggle_shop_check(did, idx)
        except (TypeError, ValueError) as exc:
            log.warning("invalid shop_check %r: %s", shop_check, exc)
        for key in ("shop_check", "guest"):
            try:
                del st.query_params[key]
            except Exception:
                pass
        if st.session_state.get("guest_mode"):
            _set_guest_query_param()
        st.rerun()

    domain = _qp_one(qp.get("domain"))
    auto = _qp_one(qp.get("auto"))
    if auto in ("1", "true", "yes") and domain in pipeline.ALLOWED_DOMAINS:
        for key in ("auto", "domain", "meal"):
            try:
                del st.query_params[key]
            except Exception:
                pass
        inferred = infer_home_hero(language=st.session_state.get("language", "sv"))
        if domain != str(inferred.get("domain") or "food"):
            inferred = {**inferred, "domain": domain}
        _run_inferred_home_decision(inferred)
        return

    if domain in pipeline.ALLOWED_DOMAINS:
        try:
            del st.query_params["domain"]
        except Exception:
            pass
        if domain == "clothes":
            st.session_state.last_domain_hint = "clothes"
            st.session_state.pending_clothes_question = pipeline._default_question(
                "clothes", st.session_state.get("language", "sv")
            )
            st.session_state.clothes_occasion = None
            st.session_state.page = "clothes_occasion"
            st.rerun()
            return
        if domain == "food":
            import food_domain as fd

            if st.session_state.get("food_meal_type") not in fd.MEAL_TYPES:
                st.session_state.food_meal_type = fd.default_meal_type()
        run_decision(question="", domain_hint=domain, reroll=False, via_router=False)

    fridge_q = _qp_one(qp.get("fridge"))
    if fridge_q in ("1", "true", "yes"):
        try:
            del st.query_params["fridge"]
        except Exception:
            pass
        st.session_state.fridge_step = "capture"
        st.session_state.fridge_inventory = []
        st.session_state.fridge_mode = False
        st.session_state.page = "fridge"
        st.rerun()
        return

    # Clothes occasion chips
    import clothes_domain as cd
    import food_domain as fd

    occasion = _qp_one(qp.get("occasion"))
    if occasion in cd.OCCASIONS:
        try:
            del st.query_params["occasion"]
        except Exception:
            pass
        from datetime import datetime

        hour = str(datetime.now().astimezone().hour)
        hist = dict(st.session_state.get("occasion_by_hour") or {})
        hist[hour] = occasion
        st.session_state.occasion_by_hour = hist
        st.session_state.clothes_occasion = occasion
        pending = (
            st.session_state.get("pending_clothes_question")
            or st.session_state.get("last_question")
            or pipeline._default_question("clothes", st.session_state.get("language", "sv"))
        )
        st.session_state.last_domain_hint = "clothes"
        run_decision(
            question=pending,
            domain_hint="clothes",
            reroll=False,
            via_router=False,
        )
        return

    # Food meal-type override chips (confirm, don't interrogate)
    meal = _qp_one(qp.get("meal"))
    if meal in fd.MEAL_TYPES:
        try:
            del st.query_params["meal"]
        except Exception:
            pass
        prev = st.session_state.get("food_meal_type")
        st.session_state.food_meal_type = meal
        # Only regenerate when user actually changed the inferred type
        if prev != meal or st.session_state.get("page") == "result":
            pending = (
                st.session_state.get("last_question")
                or pipeline._default_question("food", st.session_state.get("language", "sv"))
            )
            st.session_state.last_domain_hint = "food"
            st.session_state.accepted = False
            run_decision(
                question=pending,
                domain_hint="food",
                reroll=False,
                via_router=False,
            )
        return

    # AMBIGUOUS resolution chips
    pick = _qp_one(qp.get("pick"))
    if pick in pipeline.ALLOWED_DOMAINS or pick == "other":
        try:
            del st.query_params["pick"]
        except Exception:
            pass
        pending = st.session_state.pending_free_text or st.session_state.last_question or ""
        st.session_state.force_route_domain = pick
        st.session_state.last_domain_hint = pick
        st.session_state.pending_free_text = None
        if pick == "clothes":
            st.session_state.pending_clothes_question = pending
            st.session_state.clothes_occasion = None
            st.session_state.page = "clothes_occasion"
            st.rerun()
            return
        run_decision(
            question=pending,
            domain_hint=pick,
            reroll=False,
            via_router=True,
        )


def page_shared() -> None:
    """Public read-only decision landing — what recipients see from every share."""
    render_share_landing_chrome()
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("share_landing_sub"))}</p>',
        unsafe_allow_html=True,
    )

    payload = st.session_state.get("shared_payload") or {}
    token = st.session_state.get("shared_token")
    if not payload and token:
        row = db.get_public_share(str(token))
        payload = (row or {}).get("payload") or {}
        st.session_state.shared_payload = payload

    if not isinstance(payload, dict) or not payload.get("suggestion"):
        st.markdown(
            f'<div class="oc-refuse"><p>{html.escape(t("history_empty"))}</p></div>',
            unsafe_allow_html=True,
        )
        if st.button(t("share_cta"), type="primary", use_container_width=True, key="share_cta_empty"):
            st.session_state.page = "home"
            st.session_state.shared_token = None
            st.session_state.shared_payload = None
            st.rerun()
        return

    language = payload.get("language") or st.session_state.get("language", "sv")
    domain = str(payload.get("domain") or "")
    suggestion = str(payload.get("suggestion") or "")
    justification = str(payload.get("justification") or "")
    ctx = payload.get("context") if isinstance(payload.get("context"), dict) else {}

    if domain == "movie":
        lock_label_html = f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
        lock_body_html = (
            f"<p>{html.escape(justification)}</p>" if justification else None
        )
        st.markdown(
            _render_movie_card_html(
                language=language,
                suggestion=suggestion,
                justification=justification,
                ctx=_as_dict(ctx),
                lock_label_html=lock_label_html,
                lock_body_html=lock_body_html,
            ),
            unsafe_allow_html=True,
        )
    elif domain == "food":
        st.markdown(
            _render_food_card_html(
                language=language,
                suggestion=suggestion,
                justification=justification,
                ctx=_as_dict(ctx),
                lock_label_html=f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>',
                lock_body_html=(
                    f"<p>{html.escape(justification)}</p>" if justification else None
                ),
            ),
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="oc-decision">'
            f'<div class="label">{html.escape(domain_label(domain))}</div>'
            f"<h1>{html.escape(suggestion)}</h1>"
            f"{('<p>' + html.escape(justification) + '</p>') if justification else ''}"
            f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

    if domain == "food":
        shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
        recipe = ctx.get("recipe") if isinstance(ctx.get("recipe"), dict) else None
        if not recipe and shop:
            recipe = shop.get("recipe") if isinstance(shop.get("recipe"), dict) else None
        if shop:
            render_shopping_card(shop, language)
        if isinstance(recipe, dict):
            if recipe.get("active_minutes") is not None:
                st.caption(t("recipe_mins").format(mins=int(recipe["active_minutes"])))
            render_food_recipe(
                recipe, list(shop.get("ingredients") or []) if shop else None
            )
    elif domain == "workout" or payload.get("execution_type") == "workout":
        workout = ctx.get("workout") if isinstance(ctx.get("workout"), dict) else None
        if workout:
            try:
                import workout_domain as wd

                w = wd.finalize_workout(workout, language=language)
                blocks = w.get("blocks") or []
                lines = []
                for b in blocks:
                    name = html.escape(str(b.get("name") or ""))
                    if b.get("type") == "time":
                        detail = f"{int(b.get('seconds') or 0)}s"
                    else:
                        detail = f"{int(b.get('sets') or 1)}×{int(b.get('reps') or 0)}"
                    lines.append(
                        f"<li><strong>{name}</strong> · {html.escape(detail)}</li>"
                    )
                st.markdown(
                    f'<div class="oc-recipe"><div class="oc-shop-title">'
                    f'{html.escape(t("share_open_workout"))}</div>'
                    f'<ul>{"".join(lines)}</ul></div>',
                    unsafe_allow_html=True,
                )
            except Exception as exc:
                log.exception("shared workout render failed: %s", exc)
        detail = ctx.get("execution_detail")
        if detail:
            st.markdown(
                f'<p class="oc-meta">{html.escape(str(detail))}</p>',
                unsafe_allow_html=True,
            )
    else:
        detail = ctx.get("execution_detail")
        if detail:
            st.markdown(
                f'<p class="oc-meta">{html.escape(str(detail))}</p>',
                unsafe_allow_html=True,
            )
        exec_url = payload.get("execution_url")
        if exec_url:
            label = payload.get("execution_label") or t("do_it")
            st.link_button(
                str(label), str(exec_url), use_container_width=True, type="secondary"
            )

    st.markdown(
        f'<p class="oc-share-cta-note">{html.escape(t("share_landing_sub"))}</p>',
        unsafe_allow_html=True,
    )
    if st.button(
        t("share_cta"), type="primary", use_container_width=True, key="share_cta_main"
    ):
        st.session_state.page = "home"
        st.session_state.shared_token = None
        st.session_state.shared_payload = None
        for k in ("share", "ref", "decision_id"):
            try:
                del st.query_params[k]
            except Exception:
                pass
        st.rerun()


def main() -> None:
    init_state()
    if not st.session_state.get("_auth_cookie_checked"):
        st.stop()
    # Heal stale db module before any page that needs favorites/shopping APIs
    try:
        _ensure_db_api()
    except Exception as exc:
        log.warning("db API ensure failed: %s", exc)
    inject_css()
    require_auth_context()

    # Resolve a WORKING LLM model once per session (probes candidate list).
    # Result + failure reasons land in llm_config.DIAGNOSTICS → shown in Profil.
    if not st.session_state.get("llm_probe_done"):
        try:
            import llm_config

            llm_config.resolve_text_model(resolve_grok_api_key())
        except Exception as exc:
            log.warning("llm model probe failed: %s", exc)
        st.session_state.llm_probe_done = True

    # Handla & laga / Starta — on_click queue (must run before page render)
    try:
        _drain_pending_open_execute()
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.exception("drain pending open execute failed: %s", exc)
        st.session_state.page = "execute"
        st.session_state.accepted = True
        st.session_state.ui_error = None

    # Friendly error REPLACES the content area — never stacks under a decision card
    if st.session_state.get("ui_error"):
        render_error_boundary()
        return

    try:
        handle_query_params()
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        log.error("query-param handler failed:\n%s", traceback.format_exc())
        st.session_state._last_ui_error = f"{type(exc).__name__}: {exc}"
        st.session_state.ui_error = True
        st.rerun()
        return

    pages: dict[str, Callable[[], None]] = {
        "auth": page_auth,
        "result": page_result,
        "execute": page_execute,
        "lista": page_lista,
        "history": page_history,
        "profile": page_profile,
        "privacy": page_privacy,
        "ambiguous": page_ambiguous,
        "not_a_decision": page_not_a_decision,
        "clothes_occasion": page_clothes_occasion,
        "fridge": page_fridge,
        "shared": page_shared,
        "home": page_home,
    }
    page_name = st.session_state.get("page") or "home"
    render = pages.get(page_name, page_home)
    if not callable(render):
        log.error("page %r mapped to non-callable %r — falling back to home", page_name, render)
        render = page_home

    try:
        render()
    except BaseException as exc:
        if _is_streamlit_control_flow(exc):
            raise
        # Never blank the screen — show friendly error
        log.error("page render failed (%s):\n%s", page_name, traceback.format_exc())
        st.session_state._last_ui_error = f"{type(exc).__name__}: {exc}"
        # Soft recover for Handla/execute/result — full boundary was a dead end on Cloud
        if page_name in ("execute", "result"):
            st.session_state.ui_error = None
            st.session_state.page = "execute" if page_name == "execute" else page_name
            st.markdown(
                f'<div class="oc-error"><p>{html.escape(t("error_friendly"))}</p></div>',
                unsafe_allow_html=True,
            )
            # Do not render raw exception text — already logged above
            cur = st.session_state.get("current") or {}
            if isinstance(cur, dict) and cur.get("suggestion"):
                st.markdown(
                    f'<div class="oc-decision"><h1>{html.escape(str(cur.get("suggestion")))}</h1></div>',
                    unsafe_allow_html=True,
                )
            if st.button(t("retry"), type="primary", use_container_width=True, key="soft_retry"):
                st.session_state.page = "execute"
                st.session_state.accepted = True
                st.rerun()
            if st.button(t("home"), use_container_width=True, key="soft_home"):
                st.session_state.page = "home"
                st.rerun()
            nav()
            return
        st.session_state.ui_error = True
        st.rerun()


if __name__ == "__main__":
    main()
