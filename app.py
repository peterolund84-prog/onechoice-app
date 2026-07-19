# -*- coding: utf-8 -*-
"""
OneChoice — one everyday decision. Never a list.
Premium mobile-first Streamlit UI.

---------------------------------------------------------------------------
STATE DIAGRAM (pages / session_state / buttons) — keep code in sync
---------------------------------------------------------------------------

Pages:
  auth              → login / signup / guest
  home              → free text + domain chips
  ambiguous         → domain pick after free-text AMBIGUOUS
  not_a_decision    → soft refuse (not a decision question)
  result            → ONE decision card (food / other domains)
  execute           → food only: checkable shopping + full recipe
  history | profile

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

  [result] food primary "Handla & laga"  (accepted is False)
        → accept_decision(decision_id)  # DB status=accepted
        → current.locked=True, accepted=True, disable rerolls
        → page=execute

  [result] food primary "Handla & laga"  (accepted is True / locked card)
        → page=execute only (no second DB write; lock already permanent)

  [result] non-food primary (link / "Gör det nu")
        → accept_decision if decision_id; toast; stay on result

  [result] "Nytt förslag"  (only if not accepted and not reroll-locked)
        → run_decision(reroll=True)

  [execute] "Tillbaka"
        → page=result  (shows Låst: <suggestion> + only Handla & laga)

  [any] error boundary catch
        → log full traceback server-side; user sees Swedish retry UI
---------------------------------------------------------------------------
"""

from __future__ import annotations

import html
import logging
import traceback
import uuid
from typing import Any, Callable

import streamlit as st

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

PRIMARY = "#5A8BFF"
PRIMARY_SOFT = "#EAF1FF"
BG = "#F4F6F8"
BG_SOFT = "#EEF2F7"
INK = "#1C1C1E"
MUTED = "#6B6B76"
NAVY = "#3E5B84"
SHADOW = "0 12px 40px rgba(62, 91, 132, 0.08)"

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

I18N = {
    "sv": {
        "tagline": "Ett beslut. Klart.",
        "ask": "Vad behöver du bestämma?",
        "decide": "Bestäm åt mig",
        "new": "Nytt förslag",
        "lock_msg": "Det är {suggestion}. Kör.",
        "do_it": "Gör det nu",
        "handla_laga": "Handla & laga",
        "accepted": "Sparat — bra val.",
        "locked_title": "Låst: {suggestion}",
        "shop_title": "Inköpslista",
        "recipe_title": "Recept",
        "ingredients_title": "Ingredienser",
        "steps_title": "Gör så här",
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
        "guest": "Fortsätt som gäst (lokal demo)",
        "auth_hint": "Supabase Auth — spara beslut i molnet",
        "no_supabase": "Supabase saknas i secrets — kör i lokalt demläge.",
        "logged_in_as": "Inloggad som",
        "too_long": "Max 200 tecken.",
        "ambiguous": "Välj vad det handlar om — så tar jag beslutet.",
        "other": "Annat",
        "not_a_decision": "Jag tar beslut, inte frågor. Vad behöver du bestämma?",
    },
    "en": {
        "tagline": "One decision. Done.",
        "ask": "What do you need decided?",
        "decide": "Decide for me",
        "new": "New suggestion",
        "lock_msg": "It’s {suggestion}. Go.",
        "do_it": "Do it now",
        "handla_laga": "Shop & cook",
        "accepted": "Saved — good call.",
        "locked_title": "Locked: {suggestion}",
        "shop_title": "Shopping list",
        "recipe_title": "Recipe",
        "ingredients_title": "Ingredients",
        "steps_title": "Steps",
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
        "guest": "Continue as guest (local demo)",
        "auth_hint": "Supabase Auth — save decisions in the cloud",
        "no_supabase": "Supabase missing in secrets — running local demo.",
        "logged_in_as": "Signed in as",
        "too_long": "Max 200 characters.",
        "ambiguous": "Pick what this is about — then I’ll decide.",
        "other": "Other",
        "not_a_decision": "I make decisions, not answer questions. What do you need decided?",
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


def inject_css() -> None:
    st.markdown(
        f"""
<style>
@import url("https://fonts.googleapis.com/css2?family=Manrope:wght@500;700&display=swap");
html, body, .stApp, [data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(110% 70% at 80% -5%, rgba(90,139,255,0.12) 0%, transparent 52%),
        linear-gradient(180deg, {BG} 0%, {BG_SOFT} 100%) !important;
    font-family: "Manrope", "Helvetica Neue", sans-serif !important;
    font-weight: 500;
    color: {INK}; -webkit-font-smoothing: antialiased;
}}
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], .stDeployButton,
[data-testid="stSidebar"], [data-testid="stHeader"] {{ display: none !important; }}
.block-container {{
    max-width: 420px !important;
    padding: 1.2rem 1.2rem 9rem !important;
    margin: 0 auto !important;
}}
@media (max-width: 768px) {{
    .block-container {{ padding: 1rem 0.75rem 9rem !important; }}
}}
.oc-logo {{
    text-align: center; font-weight: 700; font-size: 1.55rem;
    letter-spacing: -0.05em; color: {INK}; margin: 0.4rem 0 0.2rem;
}}
.oc-logo em {{ font-style: normal; color: {PRIMARY}; }}
.oc-tagline {{
    text-align: center; color: {MUTED}; font-size: 1rem;
    margin: 0 0 1.4rem; letter-spacing: -0.01em;
}}
.oc-lang {{
    position: fixed !important; top: max(0.75rem, env(safe-area-inset-top)) !important;
    right: 0.75rem !important; z-index: 1100 !important;
    display: grid !important; grid-template-columns: auto auto !important; gap: 0.4rem !important;
}}
.oc-lang a {{
    display: inline-flex !important; align-items: center; justify-content: center;
    width: 40px; height: 40px; border-radius: 50%; text-decoration: none;
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.04em;
    box-shadow: 0 4px 14px rgba(62,91,132,0.1);
}}
.oc-domains {{
    display: grid !important; grid-template-columns: 1fr 1fr !important;
    gap: 0.55rem !important; margin: 0 0 1.1rem !important;
}}
@media (min-width: 380px) {{
    .oc-domains {{ grid-template-columns: repeat(3, 1fr) !important; }}
}}
.oc-domains a {{
    display: flex !important; align-items: center; justify-content: center;
    min-height: 2.7rem; border-radius: 999px; text-decoration: none;
    background: #fff; color: #444; font-weight: 600; font-size: 0.88rem;
    border: 1px solid rgba(62,91,132,0.08); box-shadow: {SHADOW};
}}
div[data-testid="stTextArea"] > div, .stTextArea > div, .stTextArea [data-baseweb="textarea"] {{
    background: transparent !important; border: none !important; box-shadow: none !important;
}}
.stTextArea textarea {{
    background: #fff !important; border: 1px solid rgba(62,91,132,0.06) !important;
    border-radius: 22px !important; min-height: 110px !important;
    font-size: 1.05rem !important; padding: 1.1rem 1.2rem !important;
    box-shadow: {SHADOW} !important; color: {INK} !important;
    font-family: "Manrope", sans-serif !important;
}}
div.stButton {{ display: flex !important; justify-content: center !important; }}
div.stButton > button[data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important; color: #fff !important; border: none !important;
    border-radius: 16px !important; font-weight: 700 !important; font-size: 1.05rem !important;
    height: 54px !important; width: 100% !important;
    box-shadow: 0 12px 28px rgba(90,139,255,0.32) !important;
    font-family: "Manrope", sans-serif !important;
}}
div.stButton > button[data-testid="baseButton-secondary"] {{
    background: transparent !important; color: {MUTED} !important;
    border: none !important; box-shadow: none !important;
    border-radius: 0 !important; font-weight: 500 !important;
    min-height: 36px !important; width: auto !important;
    font-size: 0.95rem !important; text-decoration: underline !important;
    text-underline-offset: 3px !important;
    font-family: "Manrope", sans-serif !important;
}}
div.stButton > button[kind="secondary"] {{
    background: transparent !important; color: {MUTED} !important;
    border: none !important; box-shadow: none !important;
}}
@media (max-width: 768px) {{
    div.stButton > button[data-testid="baseButton-primary"] {{
        height: 52px !important; font-size: 1rem !important;
    }}
}}
.oc-decision {{
    background: #fff; border-radius: 28px;
    padding: 2.4rem 1.5rem 2.1rem;
    box-shadow: {SHADOW}; text-align: center;
    margin: 1.1rem 0 1.35rem;
    border: 1px solid rgba(62,91,132,0.04);
}}
.oc-decision .label {{
    font-size: 0.72rem; color: {MUTED}; letter-spacing: 0.08em;
    text-transform: uppercase; margin-bottom: 1.15rem; font-weight: 700;
}}
.oc-decision h1 {{
    font-size: clamp(2.125rem, 7.2vw, 2.45rem); font-weight: 700;
    letter-spacing: -0.045em; line-height: 1.12; margin: 0 0 1.1rem; color: {INK};
}}
.oc-decision p {{
    font-size: 1.05rem; color: #3a3a42; line-height: 1.45; margin: 0;
    max-width: 22rem; margin-left: auto; margin-right: auto;
}}
.oc-lock {{
    display: inline-block; margin-top: 1.1rem; background: {PRIMARY_SOFT};
    color: {PRIMARY}; font-weight: 700; font-size: 0.8rem;
    padding: 0.35rem 0.8rem; border-radius: 999px;
}}
.oc-refuse {{
    background: #fff; border-radius: 24px; padding: 1.6rem 1.3rem;
    text-align: center; box-shadow: {SHADOW}; color: #3a3a42; font-size: 1.05rem;
    line-height: 1.45; margin: 1rem 0;
}}
.oc-meta {{ text-align: center; color: {MUTED}; font-size: 1rem; margin: 0.4rem 0 0.8rem; }}
.oc-rerolls {{
    display: flex; justify-content: center; gap: 0.45rem;
    margin: 0.15rem 0 1.15rem;
}}
.oc-rerolls i {{
    display: block; width: 7px; height: 7px; border-radius: 50%;
    background: {PRIMARY}; opacity: 1;
    transition: opacity 0.25s ease;
}}
.oc-rerolls i.used {{ opacity: 0.22; background: {MUTED}; }}
.oc-shop {{
    background: #fff; border-radius: 22px; padding: 1.25rem 1.2rem 1.1rem;
    box-shadow: {SHADOW}; margin: 0 0 1.25rem;
    border: 1px solid rgba(62,91,132,0.04); text-align: left;
}}
.oc-shop .oc-shop-title {{
    font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase;
    color: {MUTED}; font-weight: 700; margin: 0 0 0.85rem;
}}
.oc-shop .oc-sec {{
    font-size: 0.68rem; letter-spacing: 0.09em; text-transform: uppercase;
    color: {MUTED}; font-weight: 700; margin: 0.95rem 0 0.4rem;
}}
.oc-shop .oc-sec:first-of-type {{ margin-top: 0; }}
.oc-shop ul {{ list-style: none; margin: 0; padding: 0; }}
.oc-shop li {{
    display: flex; align-items: flex-start; gap: 0.65rem;
    font-size: 1rem; color: {INK}; line-height: 1.4;
    padding: 0.38rem 0;
}}
.oc-shop li::before {{
    content: ""; flex: 0 0 1.05rem; width: 1.05rem; height: 1.05rem;
    margin-top: 0.12rem; border-radius: 50%;
    border: 1.5px solid rgba(62,91,132,0.28);
    box-sizing: border-box;
}}
.oc-shop .oc-assumed {{
    margin: 1rem 0 0; padding-top: 0.75rem;
    border-top: 1px solid rgba(62,91,132,0.08);
    font-size: 0.92rem; color: {MUTED}; line-height: 1.4;
}}
.oc-recipe {{
    background: #fff; border-radius: 22px; padding: 1.25rem 1.2rem 1.2rem;
    box-shadow: {SHADOW}; margin: 0 0 1.25rem;
    border: 1px solid rgba(62,91,132,0.04); text-align: left;
}}
.oc-recipe .oc-shop-title {{
    font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase;
    color: {MUTED}; font-weight: 700; margin: 0 0 0.85rem;
}}
.oc-recipe .oc-sec {{
    font-size: 0.68rem; letter-spacing: 0.09em; text-transform: uppercase;
    color: {MUTED}; font-weight: 700; margin: 0.95rem 0 0.4rem;
}}
.oc-recipe ol {{
    margin: 0; padding-left: 1.2rem; color: {INK}; font-size: 1rem; line-height: 1.45;
}}
.oc-recipe ol li {{ margin: 0.45rem 0; }}
.oc-recipe ul {{ list-style: none; margin: 0; padding: 0; }}
.oc-recipe ul li {{
    font-size: 1rem; color: {INK}; line-height: 1.4; padding: 0.28rem 0;
}}
.oc-error {{
    background: #fff; border-radius: 24px; padding: 1.8rem 1.4rem;
    text-align: center; box-shadow: {SHADOW}; margin: 2rem 0 1rem;
}}
.oc-error p {{ color: #3a3a42; font-size: 1.1rem; margin: 0 0 0.4rem; }}
.oc-link-wrap {{
    text-align: center; margin: 0.35rem 0 0.9rem;
}}
/* Show checkbox labels (shopping list) — override global widget-label hide */
.oc-checks [data-testid="stWidgetLabel"],
div[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] {{
    display: flex !important;
}}
div[data-testid="stCheckbox"] label {{
    font-family: "Manrope", sans-serif !important;
    color: {INK} !important;
    font-size: 1rem !important;
}}
.oc-sec-label {{
    font-size: 0.68rem; letter-spacing: 0.09em; text-transform: uppercase;
    color: {MUTED}; font-weight: 700; margin: 0.85rem 0 0.35rem;
}}
.oc-hist {{
    background: #fff; border-radius: 18px; padding: 1rem 1.1rem;
    margin-bottom: 0.7rem; box-shadow: {SHADOW};
}}
.oc-hist strong {{ display: block; font-size: 1.05rem; margin-bottom: 0.2rem; }}
.oc-hist span {{ font-size: 0.9rem; color: {MUTED}; }}
.oc-pro {{
    background: #fff; border-radius: 28px; padding: 2rem 1.5rem;
    text-align: center; box-shadow: {SHADOW}; margin-top: 1.5rem;
}}
.oc-pro h2 {{ margin: 0 0 0.5rem; letter-spacing: -0.03em; }}
.oc-price {{ font-size: 1.6rem; font-weight: 700; color: {PRIMARY}; margin: 1.1rem 0; }}
.oc-nav {{
    position: fixed !important; left: 50% !important; transform: translateX(-50%) !important;
    bottom: max(0.85rem, env(safe-area-inset-bottom)) !important;
    width: min(360px, calc(100vw - 1.2rem)) !important; z-index: 1100 !important;
    display: grid !important; grid-template-columns: 1fr 1fr 1fr !important;
    gap: 0.15rem !important; background: rgba(255,255,255,0.96) !important;
    border-radius: 999px !important; padding: 0.35rem 0.4rem !important;
    box-shadow: 0 12px 36px rgba(62,91,132,0.14) !important;
    border: 1px solid rgba(62,91,132,0.06) !important;
}}
.oc-nav a {{
    display: flex !important; flex-direction: column; align-items: center; justify-content: center;
    gap: 0.2rem; text-decoration: none; color: {MUTED}; font-size: 0.68rem; font-weight: 500;
    padding: 0.5rem 0.15rem; border-radius: 999px; line-height: 1.2;
}}
.oc-nav a.active {{ background: {PRIMARY_SOFT}; color: {PRIMARY}; font-weight: 700; }}
.oc-nav .oc-ico {{ width: 1.15rem; height: 1.15rem; display: block; }}
[data-testid="stWidgetLabel"] {{ display: none !important; }}
div[data-testid="stHorizontalBlock"] {{
    display: flex !important; flex-direction: row !important; flex-wrap: nowrap !important;
}}
div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"] {{
    min-width: 0 !important; flex: 1 1 0 !important;
}}
</style>
        """,
        unsafe_allow_html=True,
    )


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
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    # Restore Supabase auth context for RLS-backed writes
    if st.session_state.access_token and st.session_state.refresh_token:
        db.set_auth(st.session_state.access_token, st.session_state.refresh_token)
    else:
        db.clear_auth()

    import supabase_client as sb

    if sb.is_configured() and not st.session_state.user_id and not st.session_state.guest_mode:
        st.session_state.page = "auth"
        return

    # Local / guest fallback
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
    try:
        return str(st.secrets.get(name, default) or default)
    except Exception:
        return default


def require_auth_context() -> None:
    if st.session_state.access_token and st.session_state.refresh_token:
        db.set_auth(st.session_state.access_token, st.session_state.refresh_token)


def page_auth() -> None:
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("auth_hint"))}</p>',
        unsafe_allow_html=True,
    )

    import supabase_client as sb

    if not sb.is_configured():
        st.warning(t("no_supabase"))
        if st.button(t("guest"), type="primary", use_container_width=True):
            db.init_db()
            st.session_state.guest_mode = True
            st.session_state.user_id = str(uuid.uuid4())
            db.ensure_user(st.session_state.user_id, language=st.session_state.language)
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
                sess = sb.sign_in(email.strip(), password)
                st.session_state.user_id = sess["user_id"]
                st.session_state.user_email = sess.get("email")
                st.session_state.access_token = sess["access_token"]
                st.session_state.refresh_token = sess["refresh_token"]
                st.session_state.guest_mode = False
                db.set_auth(sess["access_token"], sess["refresh_token"])
                db.ensure_user(
                    sess["user_id"],
                    language=st.session_state.language,
                    email=sess.get("email"),
                )
                st.session_state.page = "home"
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if st.button(t("signup_title"), use_container_width=True):
            st.session_state.auth_mode = "signup"
            st.rerun()
    else:
        if st.button(t("signup_cta"), type="primary", use_container_width=True):
            try:
                sess = sb.sign_up(
                    email.strip(), password, language=st.session_state.language
                )
                if sess.get("access_token") and sess.get("refresh_token"):
                    st.session_state.user_id = sess["user_id"]
                    st.session_state.user_email = sess.get("email")
                    st.session_state.access_token = sess["access_token"]
                    st.session_state.refresh_token = sess["refresh_token"]
                    st.session_state.guest_mode = False
                    db.set_auth(sess["access_token"], sess["refresh_token"])
                    db.ensure_user(
                        sess["user_id"],
                        language=st.session_state.language,
                        email=sess.get("email"),
                    )
                    st.session_state.page = "home"
                    st.success("Konto skapat.")
                    st.rerun()
                else:
                    st.info(
                        "Konto skapat. Bekräfta e-post i Supabase (om aktiverat), sedan logga in."
                    )
                    st.session_state.auth_mode = "login"
            except Exception as exc:
                st.error(str(exc))
        if st.button(t("login_title"), use_container_width=True):
            st.session_state.auth_mode = "login"
            st.rerun()

    st.markdown("<div style='height:0.8rem'></div>", unsafe_allow_html=True)
    if st.button(t("guest"), use_container_width=True):
        db.clear_auth()
        db.init_db()
        st.session_state.guest_mode = True
        st.session_state.access_token = None
        st.session_state.refresh_token = None
        st.session_state.user_id = str(uuid.uuid4())
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)
        st.session_state.page = "home"
        st.rerun()


def lang_bar() -> None:
    lang = st.session_state.language
    sv = "background:#5A8BFF;color:#fff;" if lang == "sv" else "background:#fff;color:#8A8A96;border:1px solid rgba(62,91,132,0.1);"
    en = "background:#5A8BFF;color:#fff;" if lang == "en" else "background:#fff;color:#8A8A96;border:1px solid rgba(62,91,132,0.1);"
    st.markdown(
        f'<div class="oc-lang"><a href="?lang=sv" style="{sv}">SV</a>'
        f'<a href="?lang=en" style="{en}">EN</a></div>',
        unsafe_allow_html=True,
    )


def nav() -> None:
    page = st.session_state.page
    items = (
        ("home", ICON_HOME, t("home"), page in ("home", "result")),
        ("history", ICON_CLOCK, t("history"), page == "history"),
        ("profile", ICON_USER, t("profile"), page == "profile"),
    )
    links = []
    for key, icon, name, active in items:
        cls = "active" if active else ""
        links.append(
            f'<a class="{cls}" href="?nav={key}">{icon}<span>{html.escape(name)}</span></a>'
        )
    st.markdown(
        f'<nav class="oc-nav" aria-label="Navigation">{"".join(links)}</nav>',
        unsafe_allow_html=True,
    )


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
    store = shop.get("store") or "ICA"
    sections.append(f'<div class="oc-shop-title">{html.escape(f"{title} · {store}")}</div>')
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

    try:
        with st.spinner(t("loading")):
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
    return name in ("RerunException", "StopException") or "Rerun" in name


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


def accept_and_open_execute(cur: dict[str, Any]) -> None:
    """Handla & laga: accept (all-domain pipeline) then open execute view."""
    accept_current_decision(cur)
    st.session_state.page = "execute"
    st.rerun()


def raise_ui_error(where: str, exc: BaseException | None = None) -> None:
    """Replace the whole content area with the friendly error (never stack mid-page)."""
    if exc is not None:
        log.error("ui error at %s:\n%s", where, traceback.format_exc())
    else:
        log.error("ui error at %s", where)
    st.session_state.ui_error = True
    st.rerun()


def render_checkable_shopping(shop: dict[str, Any] | None, decision_id: int | None) -> None:
    """Checkable shopping list grouped by store layout."""
    if not shop or not isinstance(shop, dict):
        return
    to_buy = shop.get("to_buy") or {}
    if not to_buy:
        return
    import shopping as shopping_mod

    language = st.session_state.get("language", "sv")
    store = shop.get("store") or "ICA"
    st.markdown(
        f'<div class="oc-shop-title" style="margin:0.4rem 0 0.6rem">'
        f'{html.escape(t("shop_title"))} · {html.escape(str(store))}</div>',
        unsafe_allow_html=True,
    )
    did = decision_id if decision_id is not None else "x"
    idx = 0
    for section, items in to_buy.items():
        if not items:
            continue
        st.markdown(
            f'<div class="oc-sec-label">{html.escape(str(section))}</div>',
            unsafe_allow_html=True,
        )
        for item in items:
            # Unique widget key — do not also write the same key into a dict
            # (Streamlit owns session_state[widget_key]).
            wkey = f"shop_chk_{did}_{idx}"
            idx += 1
            st.checkbox(str(item), key=wkey)

    assumed = shop.get("assumed_at_home") or ["salt", "peppar", "olja"]
    assumed_line = shopping_mod.format_assumed_line(list(assumed), language=language)
    st.caption(assumed_line)


def render_recipe_block(recipe: dict[str, Any] | None, fallback_ings: list[str] | None = None) -> None:
    if not recipe or not isinstance(recipe, dict):
        if fallback_ings:
            recipe = {"ingredients": fallback_ings, "steps": []}
        else:
            return
    ings = recipe.get("ingredients") or fallback_ings or []
    steps = recipe.get("steps") or []
    st.markdown(
        f'<div class="oc-recipe">'
        f'<div class="oc-shop-title">{html.escape(t("recipe_title"))}</div>'
        f'<div class="oc-sec">{html.escape(t("ingredients_title"))}</div>'
        f'<ul>{"".join(f"<li>{html.escape(str(i))}</li>" for i in ings)}</ul>'
        f'<div class="oc-sec">{html.escape(t("steps_title"))}</div>'
        f'<ol>{"".join(f"<li>{html.escape(str(s))}</li>" for s in steps)}</ol>'
        f"</div>",
        unsafe_allow_html=True,
    )


def render_error_boundary() -> None:
    """Friendly Swedish error — never show a traceback to the user."""
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="oc-error"><p>{html.escape(t("error_friendly"))}</p></div>',
        unsafe_allow_html=True,
    )
    if st.button(t("retry"), type="primary", use_container_width=True, key="ui_error_retry"):
        st.session_state.ui_error = None
        # Stay on a safe page
        if st.session_state.get("page") not in (
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


def page_home() -> None:
    import router as rt

    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="oc-tagline">{html.escape(t("tagline"))}</p>', unsafe_allow_html=True)

    domains = ("food", "clothes", "movie", "workout", "weekend")
    chips = "".join(
        f'<a href="?domain={d}">{html.escape(domain_label(d))}</a>' for d in domains
    )
    st.markdown(f'<div class="oc-domains">{chips}</div>', unsafe_allow_html=True)

    q = st.text_area(
        "q",
        height=110,
        label_visibility="collapsed",
        key="home_input",
        placeholder=t("ask"),
        max_chars=rt.MAX_INPUT_CHARS,
    )
    st.caption(f"{len(q or '')}/{rt.MAX_INPUT_CHARS}")
    if st.button(t("decide"), type="primary", use_container_width=True):
        question = (q or "").strip()
        if not question:
            st.warning(t("empty"))
        elif len(question) > rt.MAX_INPUT_CHARS:
            st.warning(t("too_long"))
        else:
            run_decision(question=question, domain_hint=None, reroll=False, via_router=True)
    nav()


def page_clothes_occasion() -> None:
    """One-tap 'Vart ska du?' — primary input before any clothes decision."""
    import clothes_domain as cd
    from datetime import datetime

    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
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

    # Chip grid via query params — same pattern as domains (one tap)
    chips = []
    for key in cd.OCCASION_ORDER:
        label = cd.occasion_label(key, language)
        style = ""
        if key == preselect:
            style = ' style="background:#EAF1FF;color:#5A8BFF;font-weight:700;"'
        chips.append(f'<a href="?occasion={key}"{style}>{html.escape(label)}</a>')
    st.markdown(f'<div class="oc-domains">{"".join(chips)}</div>', unsafe_allow_html=True)

    if st.button(t("home"), use_container_width=True, key="occasion_home"):
        st.session_state.page = "home"
        st.session_state.clothes_occasion = None
        st.rerun()
    nav()


def page_ambiguous() -> None:
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    st.markdown(
        f'<p class="oc-tagline">{html.escape(t("ambiguous"))}</p>',
        unsafe_allow_html=True,
    )
    domains = ("food", "clothes", "movie", "workout", "weekend")
    chips = "".join(
        f'<a href="?pick={d}">{html.escape(domain_label(d))}</a>' for d in domains
    )
    chips += f'<a href="?pick=other">{html.escape(t("other"))}</a>'
    st.markdown(f'<div class="oc-domains">{chips}</div>', unsafe_allow_html=True)
    if st.button(t("home"), use_container_width=True):
        st.session_state.page = "home"
        st.session_state.pending_free_text = None
        st.rerun()
    nav()


def render_meal_type_chips(cur: dict[str, Any]) -> None:
    """Four meal chips above the food decision — preselected from clock, one tap to change."""
    import food_domain as fd

    language = st.session_state.get("language", "sv")
    current = (
        (cur.get("context") or {}).get("meal_type")
        or st.session_state.get("food_meal_type")
        or fd.default_meal_type()
    )
    if current not in fd.MEAL_TYPES:
        current = fd.default_meal_type()
    st.session_state.food_meal_type = current

    chips = []
    for key in fd.MEAL_ORDER:
        label = fd.meal_label(key, language)
        style = ""
        if key == current:
            style = ' style="background:#EAF1FF;color:#5A8BFF;font-weight:700;"'
        chips.append(f'<a href="?meal={key}"{style}>{html.escape(label)}</a>')
    st.markdown(
        f'<div class="oc-domains" style="margin-bottom:0.75rem">{"".join(chips)}</div>',
        unsafe_allow_html=True,
    )


def page_not_a_decision() -> None:
    lang_bar()
    cur = st.session_state.current or {}
    msg = cur.get("ui_message") or t("not_a_decision")
    st.markdown(f'<div class="oc-refuse">{html.escape(msg)}</div>', unsafe_allow_html=True)
    if st.button(t("home"), use_container_width=True):
        st.session_state.page = "home"
        st.rerun()
    nav()


def page_result() -> None:
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    cur = st.session_state.get("current") or {}
    if not isinstance(cur, dict):
        cur = {}
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
        # Lock card — only Handla & laga to open/reopen execute (no rerolls)
        title = (
            t("locked_title").format(suggestion=suggestion)
            if accepted
            else suggestion
        )
        if accepted:
            body = ""
        else:
            body = f"<p>{html.escape(t('lock_msg').format(suggestion=suggestion))}</p>"
        st.markdown(
            f'<div class="oc-decision">'
            f'<div class="label">{html.escape(domain_label(domain))}</div>'
            f"<h1>{html.escape(title)}</h1>"
            f"{body}"
            f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if food_cook:
            ctx_l = cur.get("context") or {}
            mt = ctx_l.get("meal_type") or st.session_state.get("food_meal_type")
            show_shop = True
            try:
                import food_domain as fd

                show_shop = fd.show_shopping(str(mt or "middag"))
            except Exception:
                pass
            if show_shop:
                if st.button(
                    t("handla_laga"),
                    type="primary",
                    use_container_width=True,
                    key="handla_reopen",
                ):
                    accept_and_open_execute(cur)
            else:
                label = cur.get("execution_label") or (
                    "Ät nu" if language == "sv" else "Eat now"
                )
                if st.button(label, type="primary", use_container_width=True, key="eat_reopen"):
                    safe_toast(t("accepted"))
        else:
            exec_url = cur.get("execution_url")
            exec_label = cur.get("execution_label") or t("do_it")
            if exec_url:
                st.link_button(exec_label, exec_url, use_container_width=True, type="primary")
            elif st.button(exec_label, type="primary", use_container_width=True, key="do_it_locked"):
                accept_current_decision(cur)
                safe_toast(t("accepted"))
        if st.button(t("home"), key="back_home_locked", type="secondary", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        nav()
        return

    # Unlocked decision card
    # Food: meal-type chips ABOVE the decision (inferred, one tap to change)
    if domain == "food" and not accepted:
        render_meal_type_chips(cur)

    st.markdown(
        f'<div class="oc-decision">'
        f'<div class="label">{html.escape(domain_label(domain))}</div>'
        f"<h1>{html.escape(suggestion)}</h1>"
        f"<p>{html.escape(justification)}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    render_reroll_dots(reroll_index)

    # Preview shopping on result (read-only) for dinner only
    ctx = cur.get("context") or {}
    shop = ctx.get("shopping")
    meal_type = ctx.get("meal_type") or st.session_state.get("food_meal_type")
    show_shop = True
    if domain == "food":
        try:
            import food_domain as fd

            show_shop = fd.show_shopping(str(meal_type or "middag"))
        except Exception:
            show_shop = True
    if food_cook and show_shop and isinstance(shop, dict):
        render_shopping_card(shop, language)
    elif domain == "food":
        exec_detail = ctx.get("execution_detail")
        if exec_detail:
            st.markdown(
                f'<p class="oc-meta">{html.escape(str(exec_detail))}</p>',
                unsafe_allow_html=True,
            )
    else:
        exec_detail = ctx.get("execution_detail")
        if exec_detail:
            st.markdown(
                f'<p class="oc-meta">{html.escape(str(exec_detail))}</p>',
                unsafe_allow_html=True,
            )

    if food_cook and show_shop:
        # Primary: Handla & laga → accept + execute view (middag)
        label = cur.get("execution_label") or t("handla_laga")
        if st.button(label, type="primary", use_container_width=True, key="handla_accept"):
            accept_and_open_execute(cur)
    elif food_cook and not show_shop:
        # Frukost / lunch / kvällsmål — accept without shopping execute
        label = cur.get("execution_label") or ("Ät nu" if language == "sv" else "Eat now")
        if st.button(label, type="primary", use_container_width=True, key="eat_now_accept"):
            accept_current_decision(cur)
            safe_toast(t("accepted"))
            st.rerun()
    else:
        # Shared accept for clothes / movie / workout / weekend
        exec_label = cur.get("execution_label") or t("do_it")
        if st.button(exec_label, type="primary", use_container_width=True, key="do_it_primary"):
            accept_current_decision(cur)
            safe_toast(t("accepted"))
            st.rerun()

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
        st.session_state.page = "home"
        st.rerun()
    nav()


def page_execute() -> None:
    """Execution view after Handla & laga: shopping (checkable) + full recipe."""
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    cur = st.session_state.get("current") or {}
    if not isinstance(cur, dict) or not cur.get("suggestion"):
        st.session_state.page = "home"
        st.rerun()
        return

    # Must be accepted/locked to be here; enforce
    if not (st.session_state.get("accepted") or cur.get("accepted") or cur.get("locked")):
        # User navigated here without accept — send to result
        st.session_state.page = "result"
        st.rerun()
        return

    suggestion = str(cur.get("suggestion") or "")
    st.markdown(
        f'<div class="oc-decision" style="padding:1.4rem 1.2rem 1.2rem;margin-bottom:0.9rem">'
        f'<div class="label">{html.escape(domain_label(cur.get("domain") or "food"))}</div>'
        f'<h1 style="font-size:1.55rem">{html.escape(suggestion)}</h1>'
        f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    ctx = cur.get("context") or {}
    shop = ctx.get("shopping") if isinstance(ctx.get("shopping"), dict) else None
    recipe = ctx.get("recipe") or (shop or {}).get("recipe")
    import shopping as shopping_mod

    # Always rebuild recipe from shopping ingredients so dish-name protein is present
    if shop:
        recipe = shopping_mod.build_recipe(suggestion, shop.get("ingredients"))
        # Keep session current in sync for back-nav
        ctx = dict(ctx)
        ctx["recipe"] = recipe
        if "kyckling" in suggestion.lower() or "chicken" in suggestion.lower():
            # Guarantee kyckling on the shopping payload shown in execute
            flat = [
                shopping_mod._strip_hint(i)
                for section in (shop.get("to_buy") or {}).values()
                for i in section
            ]
            if shopping_mod._missing_main_protein(suggestion, flat):
                rebuilt = shopping_mod.build_shopping(
                    suggestion, meta={"ingredients": shop.get("ingredients") or []}
                )
                if rebuilt:
                    shop = rebuilt
                    ctx["shopping"] = rebuilt
                    recipe = rebuilt.get("recipe") or recipe
        cur = dict(cur)
        cur["context"] = ctx
        st.session_state.current = cur
    elif not recipe:
        recipe = shopping_mod.build_recipe(suggestion)

    did = _active_decision_id(cur)
    render_checkable_shopping(shop, did)
    render_recipe_block(
        recipe if isinstance(recipe, dict) else None,
        list((shop or {}).get("ingredients") or []) if isinstance(shop, dict) else None,
    )

    if st.button(
        t("back_to_decision"),
        type="secondary",
        use_container_width=True,
        key="exec_back",
    ):
        st.session_state.page = "result"
        st.rerun()
    nav()


def page_history() -> None:
    lang_bar()
    require_auth_context()
    st.markdown(
        f'<p class="oc-logo" style="font-size:1.35rem">{html.escape(t("history_title"))}</p>',
        unsafe_allow_html=True,
    )
    rows = db.list_decisions(st.session_state.user_id, limit=30)
    if not rows:
        st.info(t("history_empty"))
    else:
        for r in rows:
            st.markdown(
                f'<div class="oc-hist"><strong>{html.escape(r.get("suggestion",""))}</strong>'
                f'<span>{html.escape(r.get("created_at",""))} · {html.escape(r.get("status",""))} · '
                f'{html.escape(domain_label(r.get("domain","")))}</span></div>',
                unsafe_allow_html=True,
            )
    nav()


def page_profile() -> None:
    import json

    import clothes_domain as cd

    lang_bar()
    require_auth_context()
    st.markdown(
        f'<div class="oc-pro"><h2>{html.escape(t("pro_title"))}</h2>'
        f'<p>{html.escape(t("pro_desc"))}</p>'
        f'<div class="oc-price">{html.escape(t("pro_price"))}</div></div>',
        unsafe_allow_html=True,
    )
    if st.session_state.user_email:
        st.caption(f"{t('logged_in_as')} {st.session_state.user_email}")
    elif st.session_state.guest_mode:
        st.caption("Guest / lokal demo")

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

    if st.button(t("logout"), use_container_width=True):
        import supabase_client as sb

        sb.sign_out(st.session_state.access_token, st.session_state.refresh_token)
        db.clear_auth()
        for key in (
            "user_id",
            "user_email",
            "access_token",
            "refresh_token",
            "current",
            "guest_mode",
        ):
            st.session_state[key] = None if key != "guest_mode" else False
        st.session_state.page = "auth"
        st.rerun()
    nav()


def handle_query_params() -> None:
    if st.session_state.page == "auth" and not st.session_state.user_id:
        # still allow language toggle on auth
        pass
    qp = st.query_params
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

    if st.session_state.page == "auth" and not st.session_state.user_id:
        return

    nav_q = _qp_one(qp.get("nav"))
    if nav_q in ("home", "history", "profile"):
        st.session_state.page = nav_q
        try:
            del st.query_params["nav"]
        except Exception:
            pass
        st.rerun()

    domain = _qp_one(qp.get("domain"))
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
        run_decision(question="", domain_hint=domain, reroll=False, via_router=False)

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


def main() -> None:
    init_state()
    inject_css()
    require_auth_context()

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
        st.session_state.ui_error = True
        st.rerun()
        return

    pages: dict[str, Callable[[], None]] = {
        "auth": page_auth,
        "result": page_result,
        "execute": page_execute,
        "history": page_history,
        "profile": page_profile,
        "ambiguous": page_ambiguous,
        "not_a_decision": page_not_a_decision,
        "clothes_occasion": page_clothes_occasion,
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
        # Rerun into clean error-only view (do not paint error under partial page)
        log.error("page render failed (%s):\n%s", page_name, traceback.format_exc())
        st.session_state.ui_error = True
        st.rerun()


if __name__ == "__main__":
    main()
