# -*- coding: utf-8 -*-
"""Regression: widget keys must never render as visible labels (layout thieves)."""

from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

# Keys / key-shaped identifiers that have leaked into visible UI before.
KNOWN_LEAK_KEYS = (
    "meal_pills",
    "movie_format_pills",
    "movie_mood_pills",
    "ambiguous_pick",
    "hist_seg",
    "domain_chips",
    "home_free_input",
    "shop_add_input",
    "fridge_add_input",
    "oc_lang_pills",
    "ambig_domain_pills",
    "history_segment",
)

KEY_SHAPE = re.compile(r"\b[a-z][a-z0-9]*_(?:pills|input|select|field|btn)\b")
STYLE_BLOCK = re.compile(r"<style\b[^>]*>.*?</style>", re.IGNORECASE | re.DOTALL)

# Pages that render without a live decision payload.
SIMPLE_PAGES = (
    "home",
    "auth",
    "lista",
    "history",
    "profile",
    "privacy",
    "ambiguous",
    "not_a_decision",
    "clothes_occasion",
    "fridge",
)


def _visible_text(at: AppTest) -> str:
    """User-visible markdown/text — strip injected CSS so .st-key-* rules don't false-positive."""
    chunks: list[str] = []
    for attr in ("markdown", "caption", "text", "title", "header", "subheader"):
        for el in getattr(at, attr, []) or []:
            raw = str(getattr(el, "value", None) or "")
            chunks.append(STYLE_BLOCK.sub(" ", raw))
    return " ".join(chunks)


def _boot() -> AppTest:
    with mock.patch("supabase_client.is_configured", return_value=False):
        with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
            with mock.patch("db._use_supabase", return_value=False):
                at = AppTest.from_file("app.py", default_timeout=90)
                at.run()
                at.session_state["_auth_cookie_checked"] = True
                at.session_state["_oc_cookie_component_ready"] = True
                at.session_state["guest_mode"] = True
                at.session_state["user_id"] = "uid-label-leak"
                at.session_state["language"] = "sv"
                at.session_state["page"] = "home"
                at.session_state["ui_error"] = None
                at.run()
                return at


class NoWidgetLabelLeaksTests(unittest.TestCase):
    def test_collapsed_widgets_use_blank_labels_in_source(self) -> None:
        """Static guard: collapsed widgets must not use key-like / translated label strings."""
        src = Path("app.py").read_text(encoding="utf-8")
        # Bound each call: label arg within ~400 chars of label_visibility=collapsed.
        call_re = re.compile(
            r"st\.(?:text_input|pills|segmented_control|selectbox|number_input|"
            r"text_area|file_uploader|camera_input)\(\s*"
            r'(?P<label>"[^"]*"|\'[^\']*\'|t\([^)]+\))'
            r"(?P<body>.{0,500}?label_visibility\s*=\s*[\"']collapsed[\"'])",
            re.DOTALL,
        )
        bad: list[str] = []
        for m in call_re.finditer(src):
            raw = m.group("label")
            if raw.startswith("t("):
                bad.append(raw)
                continue
            label = raw[1:-1]
            if label.strip() and KEY_SHAPE.search(label):
                bad.append(label)
            if label in KNOWN_LEAK_KEYS or label in ("lang", "domain_chips", "ambiguous_pick", "hist_seg"):
                bad.append(label)
        self.assertEqual(bad, [], f"collapsed widgets still use key-like labels: {bad}")

        # Known offenders must never reappear as the first string arg.
        for key in ("meal_pills", "movie_format_pills", "movie_mood_pills", "ambiguous_pick", "hist_seg"):
            self.assertNotRegex(
                src,
                rf'st\.pills\(\s*["\']' + re.escape(key) + r'["\']',
                msg=f"st.pills still labelled {key!r}",
            )

    def test_no_widget_label_leaks_on_pages(self) -> None:
        at = _boot()
        self.assertFalse(at.exception)

        for page in SIMPLE_PAGES:
            at.session_state["page"] = page
            if page == "clothes_occasion":
                at.session_state["pending_clothes_question"] = "Vad ska jag ha på mig?"
            at.session_state["ui_error"] = None
            at.run()
            self.assertFalse(at.exception, page)
            body = _visible_text(at)
            for key in KNOWN_LEAK_KEYS:
                self.assertNotIn(key, body, f"{key!r} leaked on page={page}")
            shaped = KEY_SHAPE.findall(body)
            self.assertEqual(shaped, [], f"key-shaped tokens on page={page}: {shaped}")

        # Food result — meal segmented control must not leak its key.
        at.session_state["page"] = "result"
        at.session_state["food_meal_type"] = "middag"
        at.session_state["accepted"] = False
        at.session_state["current"] = {
            "ok": True,
            "domain": "food",
            "suggestion": "Kycklingwok med ris",
            "justification": "Test",
            "accepted": False,
            "locked": False,
            "reroll_index": 0,
            "context": {"meal_type": "middag", "dish_category": "wok"},
            "execution_type": "checklist",
            "execution_label": "Laga",
        }
        at.run()
        self.assertFalse(at.exception)
        body = _visible_text(at)
        self.assertNotIn("meal_pills", body)
        meal = next(
            (p for p in at.pills if "Frukost" in list(getattr(p, "options", []) or [])),
            None,
        )
        self.assertIsNotNone(meal)
        self.assertEqual(getattr(meal, "label", None), " ")
        opts = list(meal.options)
        for needle in ("Frukost", "Lunch", "Middag", "Kvällsmål"):
            self.assertIn(needle, opts)

        # Movie result — format/mood pills.
        at.session_state["page"] = "result"
        at.session_state["current"] = {
            "ok": True,
            "domain": "movie",
            "suggestion": "Testfilm",
            "justification": "Test",
            "accepted": False,
            "locked": False,
            "reroll_index": 0,
            "context": {"format": "movie", "mood": "feelgood"},
            "execution_type": "link",
            "execution_label": "Öppna",
        }
        at.run()
        self.assertFalse(at.exception)
        body = _visible_text(at)
        self.assertNotIn("movie_format_pills", body)
        self.assertNotIn("movie_mood_pills", body)


if __name__ == "__main__":
    unittest.main()
