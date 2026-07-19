# -*- coding: utf-8 -*-
"""
OneChoice – generell AI-beslutshjälpare
Minimalistisk premium koreansk estetik.
"""

from __future__ import annotations

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
# Design
# ---------------------------------------------------------------------------
BG = "#f8f9fa"
PRIMARY = "#5A8BFF"
BEIGE = "#F5F0E6"
PASTEL = "#E8F0FA"
NAVY = "#3E5B84"
GREEN = "#4CAF70"
SHADOW = "0 10px 36px rgba(0, 0, 0, 0.06)"
FREE_LIMIT = 5

IMAGES: dict[str, list[str]] = {
    "food": [
        "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1579871494447-9811cf80d66c?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1621996346565-e3dbc646d9a9?w=500&h=500&fit=crop",
    ],
    "clothes": [
        "https://images.unsplash.com/photo-1542272604-787c3835535d?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1434389677669-e08b4cac3105?w=500&h=500&fit=crop",
    ],
    "travel": [
        "https://images.unsplash.com/photo-1513622470522-26c3c8a854bc?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1449158743715-0a90ebb4d4f8?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1555881400-74d7acaacd8b?w=500&h=500&fit=crop",
    ],
    "career": [
        "https://images.unsplash.com/photo-1586281380349-632531db7ed4?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1521737711867-e3b97375f902?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=500&h=500&fit=crop",
    ],
    "evening": [
        "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1414235077428-338989a2e8c0?w=500&h=500&fit=crop",
    ],
    "general": [
        "https://images.unsplash.com/photo-1499750310107-5fef28a66643?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1506784983877-45594efa4cbe?w=500&h=500&fit=crop",
        "https://images.unsplash.com/photo-1484480974693-6ca0a78fb36b?w=500&h=500&fit=crop",
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
html, body, .stApp, [data-testid="stAppViewContainer"] {{
    background: {BG} !important;
    font-family: "Helvetica Neue", Helvetica, "Apple SD Gothic Neo",
                 system-ui, -apple-system, "Segoe UI", sans-serif !important;
    color: #1a1a1a;
}}
#MainMenu, footer, header, [data-testid="stToolbar"],
[data-testid="stDecoration"], .stDeployButton,
[data-testid="stSidebar"], [data-testid="stHeader"] {{
    display: none !important;
}}
.block-container {{
    max-width: 420px !important;
    padding: 1.75rem 1.5rem 8.5rem !important;
}}
@media (max-width: 480px) {{
    .block-container {{ padding: 1.25rem 1.1rem 8rem !important; }}
}}
.oc-logo {{
    text-align: center; font-weight: 700; font-size: 1.55rem;
    letter-spacing: -0.045em; color: #111;
}}
.oc-logo em {{ font-style: normal; color: {PRIMARY}; }}
.oc-logo-sm {{
    text-align: center; font-weight: 600; font-size: 1.35rem; color: #111;
}}
.oc-hero {{
    background: #fff; border-radius: 28px 28px 0 0;
    padding: 1.85rem 1.55rem 0.1rem; margin-top: 2.5rem;
}}
.oc-hero h1 {{
    font-size: 1.28rem; font-weight: 600; letter-spacing: -0.03em;
    line-height: 1.35; margin: 0; color: #111;
}}
.oc-topic {{
    display: inline-block; background: {PASTEL}; color: {PRIMARY};
    font-size: 0.72rem; font-weight: 600; padding: 0.28rem 0.7rem;
    border-radius: 999px; margin: 0 0 1rem;
}}
div[class*="st-key-lang_sv"] button,
div[class*="st-key-lang_en"] button {{
    width: 40px !important; height: 40px !important; min-height: 40px !important;
    max-width: 40px !important; padding: 0 !important; border-radius: 50% !important;
    font-size: 0.7rem !important; font-weight: 700 !important;
}}
div[class*="st-key-lang_sv"] button[data-testid="baseButton-primary"],
div[class*="st-key-lang_en"] button[data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important; color: #fff !important; border: none !important;
}}
div[class*="st-key-lang_sv"] button[data-testid="baseButton-secondary"],
div[class*="st-key-lang_en"] button[data-testid="baseButton-secondary"] {{
    background: #fff !important; color: #888 !important; border: 1px solid #e8e8ec !important;
}}
div[data-testid="stTextArea"] {{
    background: #fff !important; border-radius: 0 0 28px 28px !important;
    box-shadow: {SHADOW} !important; padding: 0.55rem 1.4rem 1.6rem !important;
    margin: 0 0 1.2rem !important; position: relative !important; z-index: 5 !important;
}}
.stTextArea label {{ display: none !important; }}
.stTextArea > div {{ border: none !important; background: transparent !important; }}
.stTextArea textarea {{
    font-family: inherit !important; font-size: 1.05rem !important;
    background: transparent !important; border: none !important;
    min-height: 170px !important; color: #222 !important;
    padding: 0.35rem 0.15rem !important; box-shadow: none !important;
    caret-color: {PRIMARY} !important; pointer-events: auto !important; z-index: 6 !important;
}}
.stTextArea textarea:focus {{
    border: none !important; box-shadow: none !important; outline: none !important;
}}
div.stButton > button[data-testid="baseButton-primary"] {{
    background: {PRIMARY} !important; color: #fff !important; border: none !important;
    border-radius: 18px !important; font-weight: 600 !important; font-size: 1.05rem !important;
    height: 3.45rem !important; width: 100% !important;
    box-shadow: 0 8px 24px rgba(90, 139, 255, 0.3) !important;
}}
div.stButton > button[data-testid="baseButton-secondary"] {{
    background: #fff !important; color: #555 !important; border: 1px solid #e8e8ec !important;
    border-radius: 14px !important; font-weight: 500 !important; font-size: 0.8rem !important;
    min-height: 2.55rem !important; width: 100% !important;
}}
.oc-label {{ text-align: center; font-size: 0.95rem; color: #888; margin: 0.75rem 0 0; }}
.oc-q {{
    text-align: center; font-size: 1.7rem; font-weight: 700;
    letter-spacing: -0.035em; line-height: 1.2; margin: 0.3rem 0 0.75rem; color: #111;
}}
.oc-card {{
    background: #fff; border-radius: 24px; padding: 1.25rem 1.2rem 0.35rem;
    margin-bottom: 0.35rem; position: relative; box-shadow: {SHADOW};
}}
.oc-card.tint-blue {{ background: {PASTEL}; }}
.oc-card.tint-beige {{ background: {BEIGE}; }}
.oc-row {{ display: flex; align-items: center; gap: 1rem; }}
.oc-col {{ display: flex; flex-direction: column; gap: 0.75rem; }}
.oc-img {{
    width: 78px; height: 78px; border-radius: 50%; object-fit: cover; flex-shrink: 0;
    box-shadow: 0 4px 14px rgba(0,0,0,0.07); background: #fff;
}}
.oc-img-rect {{
    width: 108px; height: 88px; border-radius: 18px; object-fit: cover; flex-shrink: 0;
}}
.oc-card h3 {{
    font-size: 1.18rem; font-weight: 700; margin: 0 0 0.25rem; letter-spacing: -0.025em;
}}
.oc-card p {{ font-size: 0.8rem; color: #6e6e76; margin: 0; line-height: 1.4; }}
.oc-badge {{
    position: absolute; top: 0.9rem; left: 0.9rem; background: {GREEN}; color: #fff;
    font-size: 0.68rem; font-weight: 600; padding: 0.3rem 0.75rem; border-radius: 999px; z-index: 2;
}}
div[data-testid="stLinkButton"] a {{
    border-radius: 14px !important; font-weight: 600 !important; font-size: 0.78rem !important;
    min-height: 2.55rem !important; display: flex !important; justify-content: center !important;
    align-items: center !important; text-decoration: none !important;
}}
div:has(> #share-mark) + div button[data-testid="baseButton-primary"] {{
    background: {NAVY} !important; box-shadow: none !important; border-radius: 20px !important;
}}
.oc-hist {{
    background: #fff; border-radius: 20px; padding: 1.15rem 1.25rem;
    margin-bottom: 0.8rem; box-shadow: {SHADOW};
}}
.oc-hist strong {{ display: block; font-size: 1.05rem; margin-bottom: 0.2rem; }}
.oc-hist span {{ font-size: 0.75rem; color: #999; }}
.oc-pro {{
    background: #fff; border-radius: 28px; padding: 2.1rem 1.6rem;
    text-align: center; box-shadow: {SHADOW}; margin-top: 1.75rem;
}}
.oc-pro h2 {{ font-size: 1.65rem; margin: 0 0 0.55rem; }}
.oc-pro p {{ color: #6e6e76; font-size: 0.92rem; margin: 0; line-height: 1.45; }}
.oc-price {{ font-size: 1.65rem; font-weight: 700; color: {PRIMARY}; margin: 1.3rem 0 0.2rem; }}
.oc-pill {{
    display: inline-block; background: {PASTEL}; color: {PRIMARY}; font-weight: 600;
    font-size: 0.88rem; padding: 0.55rem 1.25rem; border-radius: 999px; margin-top: 0.85rem;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"]) {{
    position: fixed !important; left: 50% !important; transform: translateX(-50%) !important;
    bottom: 0.9rem !important; width: min(380px, calc(100% - 2rem)) !important;
    background: #ebeaf2 !important; border-radius: 22px !important;
    padding: 0.35rem 0.3rem 0.45rem !important;
    box-shadow: 0 6px 28px rgba(0,0,0,0.06) !important; z-index: 1000 !important; gap: 0 !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton > button {{
    background: transparent !important; border: none !important; box-shadow: none !important;
    color: #8e8e9a !important; font-size: 0.68rem !important; font-weight: 500 !important;
    white-space: pre-line !important; line-height: 1.25 !important;
    height: 3.5rem !important; padding: 0.25rem !important;
}}
div[data-testid="stHorizontalBlock"]:has(div[class*="st-key-nav_home"])
div.stButton > button[data-testid="baseButton-primary"] {{
    background: transparent !important; color: {PRIMARY} !important;
    font-weight: 700 !important; box-shadow: none !important;
}}
[data-testid="stWidgetLabel"] {{ display: none !important; }}
</style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# \u00c4mnesdetektering + l\u00e4nkar
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
    a, b = st.columns(2)
    with a:
        if st.button("SV", key="lang_sv", type="primary" if st.session_state.language == "sv" else "secondary", use_container_width=True):
            st.session_state.language = "sv"
            st.rerun()
    with b:
        if st.button("EN", key="lang_en", type="primary" if st.session_state.language == "en" else "secondary", use_container_width=True):
            st.session_state.language = "en"
            st.rerun()


def header(mode: str = "home") -> None:
    _, mid, right = st.columns([0.9, 2.2, 1.1])
    with mid:
        if mode == "results":
            st.markdown('<div class="oc-logo-sm">One</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="oc-logo"><em>One</em>Choice</div>', unsafe_allow_html=True)
    with right:
        lang_switcher()


def nav() -> None:
    page = st.session_state.page
    home_on = page in ("home", "results")
    icons = {"home": ("\U0001f3e0", t("home")), "history": ("\U0001f552", t("history")), "profile": ("\U0001f464", t("profile"))}
    cols = st.columns(3)
    for col, key in zip(cols, ("home", "history", "profile")):
        with col:
            active = (key == "home" and home_on) or page == key
            icon, name = icons[key]
            if st.button(f"{icon}\n{name}", key=f"nav_{key}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state.page = key
                st.rerun()


def result_card(choice: dict[str, Any], index: int) -> None:
    title = choice.get("title", "")
    desc = choice.get("description", "")
    cat = choice.get("category", "general")
    imgs = IMAGES.get(cat, IMAGES["general"])
    img = choice.get("image_url", imgs[index % 3])
    tint = "tint-blue" if index == 0 else "tint-beige"
    badge = f'<span class="oc-badge">{t("recommended")}</span>' if choice.get("recommended") else ""

    if index == 0:
        html = f'<div class="oc-card {tint}"><div class="oc-row"><img class="oc-img" src="{img}" alt="" /><div><h3>{title}</h3><p>{desc}</p></div></div></div>'
    elif index == 1:
        html = f'<div class="oc-card {tint}"><div class="oc-row"><div style="flex:1"><h3>{title}</h3><p>{desc}</p></div><img class="oc-img-rect" src="{img}" alt="" /></div></div>'
    else:
        html = f'<div class="oc-card {tint}">{badge}<div class="oc-col" style="padding-top:0.4rem"><img class="oc-img" src="{img}" alt="" /><div><h3>{title}</h3><p>{desc}</p></div></div></div>'

    st.markdown(html, unsafe_allow_html=True)

    label = t("info_food") if cat == "food" else t("info_other")
    c1, c2 = st.columns(2)
    with c1:
        st.link_button(label, choice.get("info_url") or info_url(title, cat), use_container_width=True, type="secondary")
    with c2:
        st.link_button(t("order"), choice.get("order_url") or order_url(title, index, cat), use_container_width=True, type="primary")
    st.markdown("<div style='height:0.65rem'></div>", unsafe_allow_html=True)


def page_home() -> None:
    header("home")
    st.markdown(f'<div class="oc-hero"><h1>{t("tagline")}</h1></div>', unsafe_allow_html=True)

    # Endast key= – annars nollställs texten vid varje tangenttryck
    q_raw = st.text_area("q", height=170, label_visibility="collapsed", key="home_input")

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
        f'<p class="oc-q">{question}</p>'
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

    st.markdown('<div id="share-mark"></div>', unsafe_allow_html=True)
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
