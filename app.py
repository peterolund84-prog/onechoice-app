# -*- coding: utf-8 -*-
"""
OneChoice – generell AI-beslutshjälpare
Minimalistisk premium koreansk estetik.
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import requests
import streamlit as st
import streamlit.components.v1 as components

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("onechoice")

st.set_page_config(
    page_title="OneChoice",
    page_icon="\u25cb",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Design – premium Korean minimal
# ---------------------------------------------------------------------------
BG = "#F4F6F8"
BG_SOFT = "#EEF2F7"
PRIMARY = "#5A8BFF"
PRIMARY_SOFT = "#EAF1FF"
BEIGE = "#F3EEE6"
PASTEL = "#E8F0FA"
NAVY = "#3E5B84"
GREEN = "#4CAF70"
INK = "#1C1C1E"
MUTED = "#8A8A96"
SHADOW = "0 12px 40px rgba(62, 91, 132, 0.08)"
SHADOW_SOFT = "0 6px 24px rgba(62, 91, 132, 0.06)"
FREE_LIMIT = 5

IMAGES: dict[str, list[str]] = {
    "food": [
        "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=800&h=800&fit=crop&q=80",
    ],
    "clothes": [
        "https://images.unsplash.com/photo-1542272604-787c3835535d?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=800&h=800&fit=crop&q=80",
    ],
    "travel": [
        "https://images.unsplash.com/photo-1513622470522-26c3c8a854bc?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1449158743715-0a90ebb4d4f8?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=800&h=800&fit=crop&q=80",
    ],
    "career": [
        "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1521737711867-e3b97375f902?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&h=800&fit=crop&q=80",
    ],
    "evening": [
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=800&h=800&fit=crop&q=80",
    ],
    "general": [
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=800&h=800&fit=crop&q=80",
        "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=800&h=800&fit=crop&q=80",
    ],
}

# Unicode-escapes = s\u00e4kra \u00e5/\u00e4/\u00f6 p\u00e5 Windows
I18N: dict[str, dict[str, str]] = {
    "sv": {
        "tagline": "Vad beh\u00f6ver du hj\u00e4lp att v\u00e4lja idag?",
        "cta": "F\u00e5 f\u00f6rslag",
        "decision": "Ditt beslut:",
        "recommended": "Rekommenderat",
        "info_food": "Se recept",
        "info_other": "Mer info",
        "order": "Best\u00e4ll nu",
        "share": "Dela detta val",
        "home": "Hem",
        "history": "Historik",
        "profile": "Profil",
        "history_title": "Din historik",
        "history_empty": "Ingen historik \u00e4nnu.",
        "clear": "Rensa",
        "pro_title": "OneChoice Pro",
        "pro_desc": "Obegr\u00e4nsad historik och fler f\u00f6rslag.",
        "pro_price": "49 kr/m\u00e5n",
        "pro_cta": "Uppgradera till Pro",
        "pro_on": "Pro aktivt",
        "pro_demo": "Aktivera Pro (demo)",
        "loading": "T\u00e4nker igenom dina alternativ\u2026",
        "empty": "Skriv in din fr\u00e5ga f\u00f6rst.",
        "api_err": "Kunde inte n\u00e5 Grok. Visar lokala f\u00f6rslag.",
        "back": "Tillbaka",
        "view": "Visa",
        "free": "Gratis: 5 poster.",
        "stripe_off": "Stripe saknas \u2013 anv\u00e4nd demo.",
        "topic": "\u00c4mne",
    },
    "en": {
        "tagline": "What decision do you need help with today?",
        "cta": "Get Choices",
        "decision": "Your Decision:",
        "recommended": "Recommended",
        "info_food": "See recipe",
        "info_other": "More info",
        "order": "Order now",
        "share": "Share this choice",
        "home": "Home",
        "history": "History",
        "profile": "Profile",
        "history_title": "Your history",
        "history_empty": "No history yet.",
        "clear": "Clear",
        "pro_title": "OneChoice Pro",
        "pro_desc": "Unlimited history and more suggestions.",
        "pro_price": "$5/mo",
        "pro_cta": "Upgrade to Pro",
        "pro_on": "Pro active",
        "pro_demo": "Activate Pro (demo)",
        "loading": "Thinking through your options\u2026",
        "empty": "Please enter your question first.",
        "api_err": "Could not reach Grok. Showing local suggestions.",
        "back": "Back",
        "view": "View",
        "free": "Free: 5 items.",
        "stripe_off": "Stripe missing \u2013 use demo.",
        "topic": "Topic",
    },
}

TOPIC_LABELS = {
    "sv": {
        "food": "Mat",
        "clothes": "Kl\u00e4der",
        "travel": "Resor",
        "career": "Karri\u00e4r",
        "evening": "Kv\u00e4ll",
        "general": "Generellt",
    },
    "en": {
        "food": "Food",
        "clothes": "Clothes",
        "travel": "Travel",
        "career": "Career",
        "evening": "Evening",
        "general": "General",
    },
}


def init_state() -> None:
    defaults: dict[str, Any] = {
        "language": "sv",
        "page": "home",
        "is_pro": False,
        "history": [],
        "current_question": "",
        "current_choices": [],
        "current_category": "general",
        "last_error": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def t(key: str) -> str:
    lang = st.session_state.get("language", "sv")
    return I18N.get(lang, I18N["sv"]).get(key, key)


def topic_label(cat: str) -> str:
    lang = st.session_state.get("language", "sv")
    return TOPIC_LABELS.get(lang, TOPIC_LABELS["sv"]).get(cat, cat)


def inject_css() -> None:
    st.markdown(
        f"""
<style>
@import url("https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css");

html, body, .stApp, [data-testid="stAppViewContainer"] {{
    background:
        radial-gradient(110% 70% at 80% -5%, rgba(90,139,255,0.14) 0%, transparent 50%),
        radial-gradient(90% 60% at 10% 0%, rgba(245,240,230,0.55) 0%, transparent 45%),
        linear-gradient(180deg, {BG} 0%, {BG_SOFT} 100%) !important;
    font-family: "Pretendard", "Apple SD Gothic Neo", "Noto Sans KR",
                 "Helvetica Neue", Helvetica, sans-serif !important;
    color: {INK};
    -webkit-font-smoothing: antialiased;
}}
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], .stDeployButton,
[data-testid="stSidebar"], [data-testid="stHeader"] {{
    display: none !important;
}}
.block-container {{
    max-width: 680px !important;
    padding: 1.2rem 1.3rem 9.5rem !important;
    margin: 0 auto !important;
}}
@media (max-width: 768px) {{
    .block-container {{ padding: 1rem 0.5rem 9rem !important; }}
    .oc-hero h1, h1 {{ font-size: 1.8rem !important; }}
    div.stButton > button {{
        height: 48px !important; min-height: 48px !important;
        font-size: 15px !important;
    }}
    div[data-testid="stHorizontalBlock"] {{
        flex-wrap: nowrap !important;
    }}
}}
@media (max-width: 480px) {{
    .block-container {{ padding: 1rem 0.5rem 9rem !important; }}
}}

/* ----- Brand ----- */
.oc-topbar {{
    display: flex; align-items: center; justify-content: center;
    position: relative; min-height: 2.85rem; margin: 0.1rem 0 0.35rem;
}}
.oc-logo {{
    text-align: center; font-weight: 700; font-size: 1.62rem;
    letter-spacing: -0.055em; color: {INK}; line-height: 1;
}}
.oc-logo em {{ font-style: normal; color: {PRIMARY}; }}
.oc-logo-sm {{
    text-align: center; font-weight: 600; font-size: 1.32rem;
    letter-spacing: -0.04em; color: {INK};
}}

/* ----- Round SV/EN top-right ----- */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-lang_sv"]) {{
    position: absolute !important;
    top: 1.05rem !important;
    right: max(0.95rem, calc(50% - 340px + 0.95rem)) !important;
    width: auto !important;
    max-width: 100px !important;
    gap: 0.4rem !important;
    z-index: 60 !important;
    justify-content: flex-end !important;
    margin: 0 !important;
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-lang_sv"])
> div[data-testid="stColumn"] {{
    width: auto !important; flex: 0 0 auto !important; min-width: 0 !important;
    max-width: 44px !important; padding: 0 !important;
}}
@media (max-width: 768px) {{
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-lang_sv"]) {{
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        right: 0.75rem !important;
        top: 0.85rem !important;
    }}
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-lang_sv"])
    > div[data-testid="stColumn"] {{
        width: auto !important; flex: 0 0 auto !important; max-width: 44px !important;
    }}
}}
div[class*="st-key-lang_sv"],
div[class*="st-key-lang_en"] {{
    width: 40px !important;
}}
div[class*="st-key-lang_sv"] button,
div[class*="st-key-lang_en"] button {{
    width: 40px !important; height: 40px !important;
    min-height: 40px !important; max-width: 40px !important;
    padding: 0 !important; border-radius: 50% !important;
    font-size: 0.66rem !important; font-weight: 700 !important;
    letter-spacing: 0.04em !important;
    box-shadow: 0 4px 14px rgba(62, 91, 132, 0.08) !important;
    transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease !important;
}}
div[class*="st-key-lang_sv"] button:hover,
div[class*="st-key-lang_en"] button:hover {{
    transform: translateY(-1px) scale(1.03) !important;
}}
div[class*="st-key-lang_sv"] button[data-testid="baseButton-primary"],
div[class*="st-key-lang_en"] button[data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important; color: #fff !important; border: none !important;
    box-shadow: 0 8px 18px rgba(90, 139, 255, 0.38) !important;
}}
div[class*="st-key-lang_sv"] button[data-testid="baseButton-secondary"],
div[class*="st-key-lang_en"] button[data-testid="baseButton-secondary"] {{
    background: rgba(255,255,255,0.95) !important; color: {MUTED} !important;
    border: 1px solid rgba(62, 91, 132, 0.07) !important;
}}

/* ----- Hero (text only, no box) ----- */
.oc-hero {{
    background: transparent; padding: 2.15rem 0.4rem 1.05rem;
    margin: 0; text-align: center;
}}
.oc-hero h1 {{
    font-size: clamp(1.2rem, 4.6vw, 1.45rem); font-weight: 600;
    letter-spacing: -0.035em; line-height: 1.4; margin: 0; color: {INK};
}}
.oc-topic {{
    display: inline-block; background: {PRIMARY_SOFT}; color: {PRIMARY};
    font-size: 0.7rem; font-weight: 600; padding: 0.34rem 0.9rem;
    border-radius: 999px; margin: 0.25rem 0 1.15rem; letter-spacing: 0.01em;
}}

/* ----- Clean single input field ----- */
div[data-testid="stTextArea"],
div[data-testid="stTextArea"] > div,
div[data-testid="stTextArea"] > div > div,
.stTextArea, .stTextArea > div, .stTextArea [data-baseweb="textarea"] {{
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important;
}}
div[data-testid="stTextArea"] {{ margin: 0 0 1.35rem !important; }}
.stTextArea label {{ display: none !important; }}
.stTextArea textarea {{
    font-family: inherit !important; font-size: 1.06rem !important;
    line-height: 1.55 !important; background: #fff !important;
    border: 1px solid rgba(62, 91, 132, 0.05) !important;
    border-radius: 16px !important;
    min-height: 200px !important;
    color: {INK} !important; padding: 1.4rem 1.45rem !important;
    box-shadow: {SHADOW} !important; caret-color: {PRIMARY} !important;
    resize: none !important; transition: box-shadow 0.2s ease, border-color 0.2s ease !important;
}}
.stTextArea textarea:focus {{
    border-color: rgba(90, 139, 255, 0.32) !important;
    box-shadow: 0 14px 42px rgba(90, 139, 255, 0.14) !important;
    outline: none !important;
}}

/* ----- Primary / secondary Streamlit buttons ----- */
div.stButton {{ display: flex !important; justify-content: center !important; }}
div.stButton > button {{
    transition: transform 0.18s ease, box-shadow 0.18s ease !important;
}}
div.stButton > button:hover {{ transform: translateY(-1px) !important; }}
div.stButton > button[data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important; color: #fff !important; border: none !important;
    border-radius: 16px !important; font-weight: 600 !important;
    font-size: 1.06rem !important; letter-spacing: -0.01em !important;
    height: 52px !important; width: 100% !important; max-width: 360px !important;
    box-shadow: 0 12px 28px rgba(90, 139, 255, 0.32) !important;
}}
div.stButton > button[data-testid="baseButton-secondary"] {{
    background: #fff !important; color: #555 !important;
    border: 1px solid rgba(62, 91, 132, 0.08) !important;
    border-radius: 16px !important; font-weight: 500 !important;
    font-size: 0.88rem !important; min-height: 52px !important; height: 52px !important;
    width: 100% !important;
    box-shadow: {SHADOW_SOFT} !important;
}}
div[data-testid="stLinkButton"] a {{
    border-radius: 16px !important; font-weight: 600 !important;
    font-size: 0.82rem !important; min-height: 52px !important; width: 100% !important;
    display: flex !important; justify-content: center !important;
    align-items: center !important; text-decoration: none !important;
}}

.oc-spacer {{ height: 0.75rem; }}
.oc-label {{
    text-align: center; font-size: 0.86rem; color: {MUTED};
    margin: 0.85rem 0 0; letter-spacing: 0.02em;
}}
.oc-q {{
    text-align: center; font-size: clamp(1.35rem, 5vw, 1.65rem); font-weight: 700;
    letter-spacing: -0.04em; line-height: 1.25; margin: 0.35rem 0 0.75rem; color: {INK};
}}

/* ----- Elegant result cards ----- */
.oc-card {{
    background: #fff; border-radius: 28px; padding: 1.15rem 1.15rem 1.2rem;
    margin: 0 0 1.05rem; position: relative; overflow: hidden;
    box-shadow: {SHADOW}; border: 1px solid rgba(62, 91, 132, 0.045);
}}
.oc-card.tint-blue {{ background: linear-gradient(165deg, {PASTEL} 0%, #fff 72%); }}
.oc-card.tint-beige {{ background: linear-gradient(165deg, {BEIGE} 0%, #fff 72%); }}
.oc-card.tint-soft {{ background: linear-gradient(165deg, #F7F8FC 0%, #fff 70%); }}
.oc-card.is-rec {{
    border-color: rgba(76, 175, 112, 0.22);
    box-shadow: 0 14px 40px rgba(76, 175, 112, 0.1), {SHADOW};
}}
.oc-badge {{
    position: absolute; top: 1rem; right: 1rem; background: {GREEN}; color: #fff;
    font-size: 0.66rem; font-weight: 600; padding: 0.34rem 0.78rem;
    border-radius: 999px; z-index: 2; letter-spacing: 0.01em;
    box-shadow: 0 4px 12px rgba(76, 175, 112, 0.3);
}}
.oc-card-inner {{ display: flex; align-items: center; gap: 1.05rem; }}
.oc-card-inner.reverse {{ flex-direction: row-reverse; }}
.oc-card-inner.stack {{
    flex-direction: column; align-items: flex-start; gap: 0.95rem;
    padding-top: 0.35rem;
}}
.oc-img {{
    width: 92px; height: 92px; border-radius: 50%; object-fit: cover; flex-shrink: 0;
    box-shadow: 0 8px 22px rgba(0,0,0,0.08); background: #fff;
    border: 3px solid rgba(255,255,255,0.9);
}}
.oc-img-rect {{
    width: 118px; height: 96px; border-radius: 22px; object-fit: cover; flex-shrink: 0;
    box-shadow: 0 8px 22px rgba(0,0,0,0.08); background: #fff;
}}
.oc-img-hero {{
    width: 100%; height: 148px; border-radius: 20px; object-fit: cover;
    box-shadow: 0 8px 22px rgba(0,0,0,0.07); background: #eee;
}}
.oc-card-copy {{ flex: 1; min-width: 0; }}
.oc-card h3 {{
    font-size: 1.18rem; font-weight: 700; margin: 0 0 0.35rem;
    letter-spacing: -0.03em; color: {INK}; line-height: 1.25;
}}
.oc-card p {{
    font-size: 0.84rem; color: #6a6a74; margin: 0; line-height: 1.5;
}}
.oc-card-actions {{
    display: flex; gap: 0.55rem; margin-top: 1.05rem;
}}
.oc-card-actions a {{
    flex: 1; display: inline-flex; align-items: center; justify-content: center;
    min-height: 2.7rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600;
    text-decoration: none; letter-spacing: -0.01em;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.oc-card-actions a:hover {{ transform: translateY(-1px); }}
.oc-btn-ghost {{
    background: rgba(255,255,255,0.85); color: #4a4a55;
    border: 1px solid rgba(62, 91, 132, 0.1);
    box-shadow: 0 2px 8px rgba(62, 91, 132, 0.04);
}}
.oc-btn-solid {{
    background: {PRIMARY}; color: #fff; border: none;
    box-shadow: 0 8px 18px rgba(90, 139, 255, 0.28);
}}
@media (max-width: 380px) {{
    .oc-img {{ width: 78px; height: 78px; }}
    .oc-img-rect {{ width: 96px; height: 82px; border-radius: 18px; }}
    .oc-img-hero {{ height: 128px; }}
    .oc-card {{ padding: 1rem; border-radius: 24px; }}
    .oc-card h3 {{ font-size: 1.08rem; }}
    .oc-card-actions {{ flex-direction: row; flex-wrap: nowrap; gap: 0.4rem; }}
    .oc-card-actions a {{ font-size: 0.74rem; min-height: 2.5rem; }}
}}

div:has(> #share-mark) + div button[data-testid="baseButton-primary"] {{
    background: {NAVY} !important;
    box-shadow: 0 10px 24px rgba(62, 91, 132, 0.25) !important;
    border-radius: 999px !important; margin-top: 0.35rem !important;
}}
.oc-actions-gap {{ height: 0.55rem; }}

.oc-hist {{
    background: #fff; border-radius: 22px; padding: 1.2rem 1.3rem;
    margin-bottom: 0.9rem; box-shadow: {SHADOW};
    border: 1px solid rgba(62, 91, 132, 0.04);
}}
.oc-hist strong {{ display: block; font-size: 1.02rem; margin-bottom: 0.25rem; }}
.oc-hist span {{ font-size: 0.74rem; color: #999; }}
.oc-pro {{
    background: #fff; border-radius: 30px; padding: 2.3rem 1.7rem;
    text-align: center; box-shadow: {SHADOW}; margin-top: 1.85rem;
    border: 1px solid rgba(62, 91, 132, 0.04);
}}
.oc-pro h2 {{ font-size: 1.65rem; margin: 0 0 0.55rem; letter-spacing: -0.03em; }}
.oc-pro p {{ color: #6e6e76; font-size: 0.94rem; margin: 0; line-height: 1.5; }}
.oc-price {{
    font-size: 1.7rem; font-weight: 700; color: {PRIMARY};
    margin: 1.4rem 0 0.2rem; letter-spacing: -0.02em;
}}
.oc-pill {{
    display: inline-block; background: {PRIMARY_SOFT}; color: {PRIMARY};
    font-weight: 600; font-size: 0.88rem; padding: 0.58rem 1.3rem;
    border-radius: 999px; margin-top: 0.9rem;
}}

/* ----- Bottom nav: always horizontal (incl. mobile) ----- */
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"]),
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])[class] {{
    position: fixed !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    bottom: max(0.85rem, env(safe-area-inset-bottom)) !important;
    width: min(360px, calc(100vw - 1.6rem)) !important;
    max-width: calc(100vw - 1.6rem) !important;
    background: rgba(255,255,255,0.94) !important;
    backdrop-filter: blur(16px) saturate(1.2) !important;
    border-radius: 999px !important;
    padding: 0.3rem 0.35rem !important;
    box-shadow: 0 12px 36px rgba(62, 91, 132, 0.14) !important;
    border: 1px solid rgba(62, 91, 132, 0.06) !important;
    z-index: 1000 !important;
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: stretch !important;
    justify-content: space-between !important;
    gap: 0.15rem !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
> div[data-testid="stColumn"],
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
> div {{
    width: 33.333% !important;
    flex: 1 1 0 !important;
    min-width: 0 !important;
    max-width: none !important;
    padding: 0 !important;
    margin: 0 !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton {{
    width: 100% !important;
    display: block !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton > button,
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton > button[data-testid="baseButton-primary"],
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton > button[data-testid="baseButton-secondary"] {{
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: {MUTED} !important;
    font-size: 0.62rem !important;
    font-weight: 500 !important;
    white-space: pre-line !important;
    line-height: 1.25 !important;
    height: 3.35rem !important;
    min-height: 3.35rem !important;
    max-height: 3.35rem !important;
    padding: 0.15rem 0.1rem !important;
    border-radius: 999px !important;
    max-width: none !important;
    width: 100% !important;
    transform: none !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton > button[data-testid="baseButton-primary"] {{
    background: {PRIMARY_SOFT} !important;
    color: {PRIMARY} !important;
    font-weight: 700 !important;
    box-shadow: none !important;
}}
@media (max-width: 768px) {{
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"]) {{
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        width: min(360px, calc(100vw - 1.2rem)) !important;
    }}
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
    > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
    > div {{
        width: 33.333% !important;
        flex: 1 1 0 !important;
        min-width: 0 !important;
    }}
    div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
    div.stButton > button {{
        height: 3.2rem !important;
        min-height: 3.2rem !important;
        font-size: 0.6rem !important;
    }}
}}

/* Custom HTML bottom nav (bulletproof mobile row) */
.oc-nav {{
    position: fixed; left: 50%; transform: translateX(-50%);
    bottom: max(0.85rem, env(safe-area-inset-bottom));
    width: min(360px, calc(100vw - 1.2rem));
    z-index: 1000;
    display: flex; flex-direction: row; flex-wrap: nowrap;
    align-items: stretch; justify-content: space-between; gap: 0.2rem;
    background: rgba(255,255,255,0.94);
    backdrop-filter: blur(16px) saturate(1.2);
    border-radius: 999px; padding: 0.3rem 0.35rem;
    box-shadow: 0 12px 36px rgba(62, 91, 132, 0.14);
    border: 1px solid rgba(62, 91, 132, 0.06);
}}
.oc-nav a {{
    flex: 1 1 0; min-width: 0; text-align: center; text-decoration: none;
    color: {MUTED}; font-size: 0.62rem; font-weight: 500;
    line-height: 1.25; padding: 0.45rem 0.2rem; border-radius: 999px;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 0.1rem; white-space: nowrap;
}}
.oc-nav a .oc-nav-icon {{ font-size: 1.05rem; line-height: 1; }}
.oc-nav a.active {{
    background: {PRIMARY_SOFT}; color: {PRIMARY}; font-weight: 700;
}}

[data-testid="stWidgetLabel"] {{ display: none !important; }}
div[data-testid="stVerticalBlockBorderWrapper"] {{
    border: none !important; background: transparent !important; box-shadow: none !important;
}}
</style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<style>
    /* Mobiloptimering */
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem 0.5rem;
        }
        .stButton > button {
            height: 48px;
            font-size: 15px;
        }
        /* Bottom nav: keep Hem / Historik / Profil in one row */
        div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"]),
        .oc-nav {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
        }
        div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"]) > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"]) > div {
            width: 33.333% !important;
            flex: 1 1 0 !important;
            min-width: 0 !important;
        }
        div[data-testid="stHorizontalBlock"] {
            flex-wrap: nowrap !important;
        }
        .oc-card-actions {
            flex-direction: row !important;
            flex-wrap: nowrap !important;
        }
    }
    .stApp {
        background-color: #f8f9fa;
    }
    .main .block-container {
        max-width: 680px;
        margin: 0 auto;
    }
    .stButton > button {
        border-radius: 16px;
        height: 52px;
    }
</style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
def detect_category(question: str) -> str:
    q = question.lower()
    rules = [
        ("food", ("äta", "ata", "mat", "lunch", "middag", "frukost", "eat", "food", "dinner", "breakfast", "hungrig", "recept")),
        ("clothes", ("kläd", "klad", "skor", "outfit", "på mig", "pa mig", "ha på", "ha pa", "clothes", "wear", "fashion", "imorgon")),
        ("travel", ("resa", "semester", "flyg", "hotell", "travel", "vacation", "trip", "sommar", "destination")),
        ("career", ("jobb", "karriär", "karriar", "career", "job", "arbete", "intervju", "cv")),
        ("evening", ("ikväll", "ikvall", "kväll", "kvall", "tonight", "evening", "göra", "gora", "helg")),
    ]
    for cat, words in rules:
        if any(w in q for w in words):
            return cat
    return "general"


def info_url(title: str, category: str) -> str:
    if category == "food":
        return f"https://www.google.com/search?q={quote_plus(title + ' recept')}"
    if category == "clothes":
        return f"https://www.google.com/search?q={quote_plus(title + ' outfit inspiration')}"
    if category == "travel":
        return f"https://www.google.com/search?q={quote_plus(title + ' travel guide')}"
    return f"https://www.google.com/search?q={quote_plus(title)}"


def order_url(title: str, index: int, category: str) -> str:
    q = quote_plus(title)
    pools = {
        "food": [
            f"https://www.foodora.se/search?q={q}",
            f"https://www.ubereats.com/se/search?q={q}",
            f"https://wolt.com/en/search?q={q}",
        ],
        "clothes": [
            f"https://www.zalando.se/catalog/?q={q}",
            f"https://www.hm.com/se/search-results.html?q={q}",
            f"https://www.google.com/search?q={quote_plus(title + ' shop')}",
        ],
        "travel": [
            f"https://www.booking.com/searchresults.html?ss={q}",
            f"https://www.google.com/travel/search?q={q}",
            f"https://www.kayak.se/horizon/sem/hotels/results?q={q}",
        ],
        "career": [
            f"https://www.linkedin.com/jobs/search/?keywords={q}",
            f"https://arbetsformedlingen.se/platsbanken/?q={q}",
            f"https://www.google.com/search?q={q}",
        ],
        "evening": [
            f"https://www.google.com/maps/search/{q}",
            f"https://www.foodora.se/search?q={q}",
            f"https://www.google.com/search?q={q}",
        ],
        "general": [
            f"https://www.google.com/search?q={q}",
            f"https://www.google.com/search?q={quote_plus(title + ' near me')}",
            f"https://www.google.com/search?q={quote_plus(title + ' buy')}",
        ],
    }
    links = pools.get(category, pools["general"])
    return links[index % len(links)]


def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default) or default)
    except Exception:
        return default


def enrich(choices: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
    imgs = IMAGES.get(category, IMAGES["general"])
    rec_count = sum(1 for c in choices if c.get("recommended"))
    for i, c in enumerate(choices):
        title = str(c.get("title", "option")).strip() or f"Option {i + 1}"
        c["title"] = title
        c["description"] = str(c.get("description", "")).strip()
        if not c.get("image_url"):
            c["image_url"] = imgs[i % len(imgs)]
        c["info_url"] = info_url(title, category)
        c["order_url"] = order_url(title, i, category)
        c["category"] = category
        if rec_count == 0 and i == len(choices) - 1:
            c["recommended"] = True
        elif rec_count > 1 and i < len(choices) - 1:
            c["recommended"] = False
    return choices


def demo_choices(question: str, language: str) -> list[dict[str, Any]]:
    sv = language == "sv"
    cat = detect_category(question)
    packs: dict[str, list[dict[str, Any]]] = {
        "food": [
            {"title": "Fresh Salad Bowl", "description": "L\u00e4tt och fr\u00e4sch." if sv else "Light and fresh.", "recommended": False},
            {"title": "Sushi Set", "description": "Balanserad smakresa." if sv else "Balanced taste journey.", "recommended": False},
            {"title": "Pasta Primavera", "description": "Varm pasta \u2013 v\u00e5rt tips." if sv else "Warm pasta \u2013 our pick.", "recommended": True},
        ],
        "clothes": [
            {"title": "Casual denim", "description": "Jeans + vit t-shirt." if sv else "Jeans + white tee.", "recommended": False},
            {"title": "Smart casual", "description": "Chinos och skjorta." if sv else "Chinos and a shirt.", "recommended": False},
            {"title": "Neutrala lager" if sv else "Layered neutrals", "description": "Mjuka beige/gr\u00e5 lager." if sv else "Soft beige/grey layers.", "recommended": True},
        ],
        "travel": [
            {"title": "K\u00f6penhamn" if sv else "Copenhagen", "description": "N\u00e4ra och designigt." if sv else "Close and design-forward.", "recommended": False},
            {"title": "Stuga i naturen" if sv else "Nature cabin", "description": "Tystnad och \u00e5terh\u00e4mtning." if sv else "Quiet rest in nature.", "recommended": False},
            {"title": "Lissabon" if sv else "Lisbon", "description": "Sol, mat och vibe." if sv else "Sun, food and vibe.", "recommended": True},
        ],
        "career": [
            {"title": "Uppdatera CV" if sv else "Update your CV", "description": "\u00d6ppnar fler d\u00f6rrar." if sv else "Opens more doors.", "recommended": False},
            {"title": "N\u00e4tverka idag" if sv else "Network today", "description": "Kontakta n\u00e5gon i branschen." if sv else "Reach someone in your field.", "recommended": False},
            {"title": "S\u00f6k en roll" if sv else "Apply to one role", "description": "S\u00f6k nu \u2013 rekommenderas." if sv else "Apply now \u2013 recommended.", "recommended": True},
        ],
        "evening": [
            {"title": "Filmhemma" if sv else "Movie night in", "description": "Mysigt och enkelt." if sv else "Cozy and simple.", "recommended": False},
            {"title": "Promenad + caf\u00e9" if sv else "Walk + caf\u00e9", "description": "Frisk luft och bel\u00f6ning." if sv else "Fresh air and a treat.", "recommended": False},
            {"title": "Middag ute" if sv else "Dinner out", "description": "Byt milj\u00f6 \u2013 v\u00e5rt tips." if sv else "Change of scenery \u2013 our tip.", "recommended": True},
        ],
        "general": [
            {"title": "Alternativ A" if sv else "Option A", "description": "Tryggt och enkelt." if sv else "Safe and simple.", "recommended": False},
            {"title": "Alternativ B" if sv else "Option B", "description": "Lite mer sp\u00e4nnande." if sv else "A bit more exciting.", "recommended": False},
            {"title": "Alternativ C" if sv else "Option C", "description": "B\u00e4sta balansen." if sv else "Best balance.", "recommended": True},
        ],
    }
    return enrich(packs.get(cat, packs["general"]), cat)


def call_grok(question: str, language: str) -> tuple[list[dict[str, Any]], str]:
    """Grok med chain-of-thought; fallback till demo."""
    cat = detect_category(question)
    key = get_secret("GROK_API_KEY")
    if not key or key.startswith("din_"):
        return demo_choices(question, language), cat

    lang = "Swedish" if language == "sv" else "English"
    system = (
        "You are OneChoice, a calm Korean-minimalist decision assistant. "
        "Think step by step internally. Output valid JSON only."
    )
    user = f"""
Decision: "{question}"
Detected topic: {cat}
Language: {lang}

Think step by step (internally):
1) Confirm topic.
2) Brainstorm options that match the topic.
3) Pick best 3; mark exactly one recommended.
4) Short titles, one calm sentence each.

Return ONLY:
{{"topic":"{cat}","choices":[
  {{"title":"...","description":"...","recommended":false}},
  {{"title":"...","description":"...","recommended":false}},
  {{"title":"...","description":"...","recommended":true}}
]}}
"""
    try:
        resp = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "grok-2-latest",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.65,
            },
            timeout=45,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence:
            raw = fence.group(1).strip()
        brace = re.search(r"\{[\s\S]*\"choices\"[\s\S]*\}", raw)
        if brace:
            raw = brace.group(0)
        data = json.loads(raw)
        choices = list(data.get("choices", []))
        if data.get("topic") in IMAGES:
            cat = data["topic"]
        if len(choices) >= 3:
            return enrich(choices[:3], cat), cat
    except Exception as exc:
        log.exception("Grok error: %s", exc)
        st.session_state.last_error = t("api_err")

    return demo_choices(question, language), cat


def stripe_checkout_url() -> str | None:
    secret = get_secret("STRIPE_SECRET_KEY")
    if not secret or secret.startswith("din_"):
        return None
    try:
        import stripe

        stripe.api_key = secret
        sv = st.session_state.language == "sv"
        session = stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{
                "price_data": {
                    "currency": "sek" if sv else "usd",
                    "unit_amount": 4900 if sv else 500,
                    "recurring": {"interval": "month"},
                    "product_data": {"name": "OneChoice Pro"},
                },
                "quantity": 1,
            }],
            success_url="http://localhost:8501/?pro=success",
            cancel_url="http://localhost:8501/?pro=cancel",
        )
        return session.url
    except Exception as exc:
        log.exception("Stripe: %s", exc)
        return None


def save_history(question: str, choices: list[dict[str, Any]]) -> None:
    entry = {
        "question": question,
        "choices": choices,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    hist = [entry] + list(st.session_state.history)
    if not st.session_state.is_pro:
        hist = hist[:FREE_LIMIT]
    st.session_state.history = hist


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def lang_switcher() -> None:
    a, b = st.columns([1, 1], gap="small")
    with a:
        if st.button(
            "SV",
            key="lang_sv",
            type="primary" if st.session_state.language == "sv" else "secondary",
            use_container_width=True,
        ):
            st.session_state.language = "sv"
            st.rerun()
    with b:
        if st.button(
            "EN",
            key="lang_en",
            type="primary" if st.session_state.language == "en" else "secondary",
            use_container_width=True,
        ):
            st.session_state.language = "en"
            st.rerun()


def header(mode: str = "home") -> None:
    lang_switcher()
    st.markdown('<div class="oc-topbar">', unsafe_allow_html=True)
    if mode == "results":
        st.markdown('<div class="oc-logo-sm">One</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def nav() -> None:
    """Bottom navigation that stays in one horizontal row on mobile."""
    page = st.session_state.page
    home_on = page in ("home", "results")
    items = (
        ("home", "\U0001f3e0", t("home"), home_on),
        ("history", "\U0001f552", t("history"), page == "history"),
        ("profile", "\U0001f464", t("profile"), page == "profile"),
    )
    parts = []
    for key, icon, name, active in items:
        cls = "active" if active else ""
        parts.append(
            f'<a class="{cls}" href="?nav={key}">'
            f'<span class="oc-nav-icon">{icon}</span>{html.escape(name)}</a>'
        )
    st.html(f'<nav class="oc-nav" aria-label="Navigation">{"".join(parts)}</nav>')


def result_card(choice: dict[str, Any], index: int) -> None:
    title = html.escape(str(choice.get("title", "")))
    desc = html.escape(str(choice.get("description", "")))
    cat = choice.get("category", "general")
    imgs = IMAGES.get(cat, IMAGES["general"])
    img = html.escape(str(choice.get("image_url", imgs[index % 3])))
    recommended = bool(choice.get("recommended"))
    tint = ("tint-soft" if recommended else "tint-blue" if index == 0 else "tint-beige")
    rec_cls = " is-rec" if recommended else ""
    badge = f'<span class="oc-badge">{html.escape(t("recommended"))}</span>' if recommended else ""
    info_label = html.escape(t("info_food") if cat == "food" else t("info_other"))
    order_label = html.escape(t("order"))
    info_href = html.escape(choice.get("info_url") or info_url(str(choice.get("title", "")), cat), quote=True)
    order_href = html.escape(choice.get("order_url") or order_url(str(choice.get("title", "")), index, cat), quote=True)
    actions = (
        f'<div class="oc-card-actions">'
        f'<a class="oc-btn-ghost" href="{info_href}" target="_blank" rel="noopener noreferrer">{info_label}</a>'
        f'<a class="oc-btn-solid" href="{order_href}" target="_blank" rel="noopener noreferrer">{order_label}</a>'
        f"</div>"
    )

    if recommended:
        body = (
            f'<div class="oc-card-inner stack">'
            f'<img class="oc-img-hero" src="{img}" alt="" loading="lazy" />'
            f'<div class="oc-card-copy"><h3>{title}</h3><p>{desc}</p></div>'
            f"</div>"
        )
    elif index % 2 == 1:
        body = (
            f'<div class="oc-card-inner reverse">'
            f'<img class="oc-img-rect" src="{img}" alt="" loading="lazy" />'
            f'<div class="oc-card-copy"><h3>{title}</h3><p>{desc}</p></div>'
            f"</div>"
        )
    else:
        body = (
            f'<div class="oc-card-inner">'
            f'<img class="oc-img" src="{img}" alt="" loading="lazy" />'
            f'<div class="oc-card-copy"><h3>{title}</h3><p>{desc}</p></div>'
            f"</div>"
        )

    st.html(
        f'<div class="oc-card {tint}{rec_cls}">{badge}{body}{actions}</div>'
    )


def page_home() -> None:
    header("home")
    st.markdown(
        f'<div class="oc-hero"><h1>{t("tagline")}</h1></div>',
        unsafe_allow_html=True,
    )

    # Endast key= – annars nollställs texten vid varje tangenttryck
    q_raw = st.text_area(
        "q",
        height=200,
        label_visibility="collapsed",
        key="home_input",
    )

    st.markdown('<div class="oc-spacer"></div>', unsafe_allow_html=True)

    if st.button(t("cta"), type="primary", use_container_width=True):
        q = (q_raw or "").strip()
        if not q:
            st.warning(t("empty"))
        else:
            with st.spinner(t("loading")):
                choices, cat = call_grok(q, st.session_state.language)
            st.session_state.current_question = q
            st.session_state.current_choices = choices
            st.session_state.current_category = cat
            save_history(q, choices)
            st.session_state.page = "results"
            st.rerun()

    if st.session_state.last_error:
        st.caption(st.session_state.last_error)
        st.session_state.last_error = None
    nav()


def page_results() -> None:
    header("results")
    question = st.session_state.current_question or "\u2014"
    choices = list(st.session_state.current_choices or [])
    cat = st.session_state.get("current_category", "general")

    st.markdown(
        f'<p class="oc-label">{t("decision")}</p>'
        f'<p class="oc-q">{html.escape(question)}</p>'
        f'<div style="text-align:center"><span class="oc-topic">{t("topic")}: {topic_label(cat)}</span></div>',
        unsafe_allow_html=True,
    )

    if choices:
        rec = [c for c in choices if c.get("recommended")]
        rest = [c for c in choices if not c.get("recommended")]
        if rec:
            choices = rest + rec

    for i, c in enumerate(choices[:3]):
        result_card(c, i)

    rec_title = next((c.get("title", "") for c in choices if c.get("recommended")), choices[0].get("title", "") if choices else "")
    share = f"OneChoice: {question} \u2192 {rec_title}"

    st.markdown('<div class="oc-actions-gap"></div><div id="share-mark"></div>', unsafe_allow_html=True)
    if st.button(f"\u22ef  {t('share')}", type="primary", use_container_width=True, key="share_btn"):
        components.html(f"<script>navigator.clipboard.writeText({json.dumps(share)});</script>", height=0)
        st.toast(share)

    if st.button(t("back"), key="back_home", use_container_width=True):
        st.session_state.page = "home"
        st.rerun()
    nav()


def page_history() -> None:
    header("home")
    st.markdown(f'<p class="oc-q" style="text-align:left;font-size:1.45rem">{t("history_title")}</p>', unsafe_allow_html=True)
    if not st.session_state.is_pro:
        st.caption(t("free"))
    hist = st.session_state.history
    if not hist:
        st.info(t("history_empty"))
    else:
        for i, e in enumerate(hist):
            rec = next((c.get("title") for c in e.get("choices", []) if c.get("recommended")), "\u2014")
            st.markdown(
                f'<div class="oc-hist"><strong>{e.get("question", "")}</strong>'
                f'<span>{e.get("timestamp", "")} \u00b7 \u2192 {rec}</span></div>',
                unsafe_allow_html=True,
            )
            if st.button(t("view"), key=f"hist_{i}", use_container_width=True):
                st.session_state.current_question = e["question"]
                st.session_state.current_choices = e["choices"]
                st.session_state.page = "results"
                st.rerun()
        if st.button(t("clear"), key="clear_hist"):
            st.session_state.history = []
            st.rerun()
    nav()


def page_profile() -> None:
    header("home")
    st.markdown(
        f'<div class="oc-pro"><h2>{t("pro_title")}</h2><p>{t("pro_desc")}</p>'
        f'<div class="oc-price">{t("pro_price")}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)

    if st.session_state.is_pro:
        st.markdown(f'<div style="text-align:center"><span class="oc-pill">{t("pro_on")}</span></div>', unsafe_allow_html=True)
    else:
        if st.button(t("pro_cta"), type="primary", use_container_width=True, key="stripe_cta"):
            url = stripe_checkout_url()
            if url:
                st.link_button("Stripe Checkout \u2192", url, use_container_width=True)
            else:
                st.info(t("stripe_off"))
        if st.button(t("pro_demo"), key="pro_demo", use_container_width=True):
            st.session_state.is_pro = True
            st.rerun()

    if st.query_params.get("pro") == "success":
        st.session_state.is_pro = True
        try:
            del st.query_params["pro"]
        except Exception:
            pass
        st.success(t("pro_on"))
    nav()


def main() -> None:
    init_state()
    inject_css()
    nav_q = st.query_params.get("nav")
    if nav_q in ("home", "history", "profile"):
        st.session_state.page = nav_q
        try:
            del st.query_params["nav"]
        except Exception:
            pass
    if st.query_params.get("pro") == "success":
        st.session_state.is_pro = True
        st.session_state.page = "profile"
    {
        "results": page_results,
        "history": page_history,
        "profile": page_profile,
    }.get(st.session_state.page, page_home)()


if __name__ == "__main__":
    main()
