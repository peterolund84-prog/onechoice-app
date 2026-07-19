# -*- coding: utf-8 -*-
"""
OneChoice — one everyday decision. Never a list.
Premium mobile-first Streamlit UI.
"""

from __future__ import annotations

import html
import logging
import uuid
from typing import Any

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
MUTED = "#8A8A96"
NAVY = "#3E5B84"
SHADOW = "0 12px 40px rgba(62, 91, 132, 0.08)"

I18N = {
    "sv": {
        "tagline": "Ett beslut. Klart.",
        "ask": "Vad behöver du bestämma?",
        "decide": "Bestäm åt mig",
        "new": "Nytt förslag",
        "lock_msg": "Det är {suggestion}. Kör.",
        "do_it": "Gör det nu",
        "accepted": "Sparat — bra val.",
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
    },
    "en": {
        "tagline": "One decision. Done.",
        "ask": "What do you need decided?",
        "decide": "Decide for me",
        "new": "New suggestion",
        "lock_msg": "It’s {suggestion}. Go.",
        "do_it": "Do it now",
        "accepted": "Saved — good call.",
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
    },
}


def t(key: str) -> str:
    lang = st.session_state.get("language", "sv")
    return I18N.get(lang, I18N["sv"]).get(key, key)


def domain_label(domain: str) -> str:
    lang = st.session_state.get("language", "sv")
    return I18N.get(lang, I18N["sv"])["domains"].get(domain, domain)


def inject_css() -> None:
    st.markdown(
        f"""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");
html, body, .stApp, [data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(110% 70% at 80% -5%, rgba(90,139,255,0.14) 0%, transparent 50%),
        linear-gradient(180deg, {BG} 0%, {BG_SOFT} 100%) !important;
    font-family: "Pretendard", "Apple SD Gothic Neo", "Helvetica Neue", sans-serif !important;
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
    text-align: center; color: {MUTED}; font-size: 0.95rem;
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
    background: #fff; color: #444; font-weight: 600; font-size: 0.82rem;
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
}}
div.stButton {{ display: flex !important; justify-content: center !important; }}
div.stButton > button[data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important; color: #fff !important; border: none !important;
    border-radius: 16px !important; font-weight: 600 !important; font-size: 1.05rem !important;
    height: 52px !important; width: 100% !important;
    box-shadow: 0 12px 28px rgba(90,139,255,0.32) !important;
}}
div.stButton > button[data-testid="baseButton-secondary"] {{
    background: #fff !important; color: #555 !important;
    border: 1px solid rgba(62,91,132,0.08) !important;
    border-radius: 16px !important; font-weight: 500 !important;
    min-height: 48px !important; width: 100% !important;
}}
@media (max-width: 768px) {{
    div.stButton > button {{ height: 48px !important; font-size: 15px !important; }}
}}
.oc-decision {{
    background: #fff; border-radius: 28px; padding: 1.75rem 1.4rem 1.4rem;
    box-shadow: {SHADOW}; text-align: center; margin: 0.5rem 0 1rem;
    border: 1px solid rgba(62,91,132,0.04);
}}
.oc-decision .label {{
    font-size: 0.75rem; color: {MUTED}; letter-spacing: 0.04em;
    text-transform: uppercase; margin-bottom: 0.65rem;
}}
.oc-decision h1 {{
    font-size: clamp(1.55rem, 6vw, 1.95rem); font-weight: 700;
    letter-spacing: -0.04em; line-height: 1.2; margin: 0 0 0.75rem; color: {INK};
}}
.oc-decision p {{
    font-size: 0.95rem; color: #5c5c66; line-height: 1.45; margin: 0;
}}
.oc-lock {{
    display: inline-block; margin-top: 0.9rem; background: {PRIMARY_SOFT};
    color: {PRIMARY}; font-weight: 700; font-size: 0.78rem;
    padding: 0.35rem 0.8rem; border-radius: 999px;
}}
.oc-refuse {{
    background: #fff; border-radius: 24px; padding: 1.6rem 1.3rem;
    text-align: center; box-shadow: {SHADOW}; color: #555; font-size: 1rem;
    line-height: 1.45; margin: 1rem 0;
}}
.oc-meta {{ text-align: center; color: {MUTED}; font-size: 0.8rem; margin: 0.4rem 0 0.8rem; }}
.oc-hist {{
    background: #fff; border-radius: 18px; padding: 1rem 1.1rem;
    margin-bottom: 0.7rem; box-shadow: {SHADOW};
}}
.oc-hist strong {{ display: block; font-size: 1.02rem; margin-bottom: 0.2rem; }}
.oc-hist span {{ font-size: 0.74rem; color: #999; }}
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
    border-radius: 999px !important; padding: 0.3rem 0.35rem !important;
    box-shadow: 0 12px 36px rgba(62,91,132,0.14) !important;
    border: 1px solid rgba(62,91,132,0.06) !important;
}}
.oc-nav a {{
    display: flex !important; flex-direction: column; align-items: center; justify-content: center;
    gap: 0.1rem; text-decoration: none; color: {MUTED}; font-size: 0.62rem; font-weight: 500;
    padding: 0.45rem 0.15rem; border-radius: 999px; line-height: 1.25;
}}
.oc-nav a.active {{ background: {PRIMARY_SOFT}; color: {PRIMARY}; font-weight: 700; }}
.oc-nav a span {{ font-size: 1.05rem; line-height: 1; }}
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
        "reroll_index": 0,
        "last_question": "",
        "last_domain_hint": None,
        "guest_mode": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

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
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)


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
        ("home", "\U0001f3e0", t("home"), page in ("home", "result")),
        ("history", "\U0001f552", t("history"), page == "history"),
        ("profile", "\U0001f464", t("profile"), page == "profile"),
    )
    links = []
    for key, icon, name, active in items:
        cls = "active" if active else ""
        links.append(
            f'<a class="{cls}" href="?nav={key}"><span>{icon}</span>{html.escape(name)}</a>'
        )
    st.markdown(
        f'<nav class="oc-nav" aria-label="Navigation">{"".join(links)}</nav>',
        unsafe_allow_html=True,
    )


def run_decision(*, question: str, domain_hint: str | None, reroll: bool) -> None:
    require_auth_context()
    if not st.session_state.user_id:
        db.init_db()
        st.session_state.user_id = str(uuid.uuid4())
        st.session_state.guest_mode = True
        db.ensure_user(st.session_state.user_id, language=st.session_state.language)

    if reroll:
        st.session_state.reroll_index = int(st.session_state.reroll_index or 0) + 1
    else:
        st.session_state.reroll_index = 0
        st.session_state.last_question = question or ""
        st.session_state.last_domain_hint = domain_hint

    q = (st.session_state.last_question or question or "").strip()
    hint = st.session_state.last_domain_hint or domain_hint
    if not q and hint:
        q = pipeline._default_question(str(hint), st.session_state.language)
        st.session_state.last_question = q

    prev_id = None
    cur = st.session_state.current
    if reroll and isinstance(cur, dict):
        prev_id = cur.get("decision_id")

    try:
        with st.spinner(t("loading")):
            result = pipeline.decide(
                str(st.session_state.user_id),
                q,
                domain_hint=str(hint) if hint else None,
                language=st.session_state.language,
                reroll=reroll,
                reroll_index=int(st.session_state.reroll_index or 0),
                previous_decision_id=prev_id,
                grok_api_key=get_secret("GROK_API_KEY"),
            )
    except Exception as exc:
        log.exception("decide failed: %s", exc)
        st.error("Kunde inte skapa beslut just nu. Försök igen.")
        st.session_state.page = "home"
        return

    st.session_state.current = result.to_dict()
    st.session_state.page = "result"
    st.rerun()


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
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="oc-tagline">{html.escape(t("tagline"))}</p>', unsafe_allow_html=True)

    domains = ("food", "clothes", "movie", "workout", "weekend")
    chips = "".join(
        f'<a href="?domain={d}">{html.escape(domain_label(d))}</a>' for d in domains
    )
    st.markdown(f'<div class="oc-domains">{chips}</div>', unsafe_allow_html=True)

    q = st.text_area("q", height=110, label_visibility="collapsed", key="home_input", placeholder=t("ask"))
    if st.button(t("decide"), type="primary", use_container_width=True):
        question = (q or "").strip()
        if not question:
            st.warning(t("empty"))
        else:
            run_decision(question=question, domain_hint=None, reroll=False)
    nav()


def page_result() -> None:
    lang_bar()
    st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    cur = st.session_state.current or {}

    if cur.get("refused"):
        msg = cur.get("refusal_message") or t("refuse")
        st.markdown(f'<div class="oc-refuse">{html.escape(msg)}</div>', unsafe_allow_html=True)
        if st.button(t("home"), use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        nav()
        return

    suggestion = html.escape(str(cur.get("suggestion") or ""))
    justification = html.escape(str(cur.get("justification") or ""))
    domain = cur.get("domain") or ""
    locked = bool(cur.get("locked"))
    reroll_index = int(cur.get("reroll_index") or 0)
    left = max(0, pipeline.MAX_REROLLS - reroll_index)

    lock_html = ""
    if locked:
        lock_line = t("lock_msg").format(suggestion=cur.get("suggestion") or "")
        lock_html = f'<div class="oc-lock">{html.escape(t("locked_label"))}</div>'
        justification = html.escape(lock_line)

    st.markdown(
        f'<div class="oc-decision">'
        f'<div class="label">{html.escape(domain_label(domain))}</div>'
        f"<h1>{suggestion}</h1>"
        f"<p>{justification}</p>"
        f"{lock_html}"
        f"</div>",
        unsafe_allow_html=True,
    )

    if not locked:
        st.markdown(
            f'<p class="oc-meta">{html.escape(t("rerolls_left").format(n=left))}</p>',
            unsafe_allow_html=True,
        )

    # Execution CTA
    exec_url = cur.get("execution_url")
    exec_label = cur.get("execution_label") or t("do_it")
    exec_detail = (cur.get("context") or {}).get("execution_detail")
    if exec_detail:
        st.markdown(
            f'<p class="oc-meta">{html.escape(str(exec_detail))}</p>',
            unsafe_allow_html=True,
        )
    if exec_url:
        st.link_button(exec_label, exec_url, use_container_width=True, type="primary")
    elif exec_detail and not exec_url:
        st.button(exec_label, type="primary", use_container_width=True, disabled=True)

    if locked:
        if cur.get("decision_id") and st.button(t("accepted"), use_container_width=True):
            pipeline.accept_decision(int(cur["decision_id"]))
            st.toast(t("accepted"))
    else:
        c1, c2 = st.columns(2)
        with c1:
            if st.button(t("new"), use_container_width=True):
                run_decision(
                    question=st.session_state.last_question,
                    domain_hint=st.session_state.last_domain_hint,
                    reroll=True,
                )
        with c2:
            if st.button(t("do_it"), type="primary", use_container_width=True):
                if cur.get("decision_id"):
                    pipeline.accept_decision(int(cur["decision_id"]))
                st.toast(t("accepted"))
                if exec_url:
                    st.markdown(
                        f'<meta http-equiv="refresh" content="0;url={html.escape(exec_url, quote=True)}">',
                        unsafe_allow_html=True,
                    )

    if st.button(t("home"), key="back_home", use_container_width=True):
        st.session_state.page = "home"
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
        run_decision(question="", domain_hint=domain, reroll=False)


def main() -> None:
    init_state()
    inject_css()
    require_auth_context()
    handle_query_params()
    {
        "auth": page_auth,
        "result": page_result,
        "history": page_history,
        "profile": page_profile,
    }.get(st.session_state.page, page_home)()


if __name__ == "__main__":
    main()
