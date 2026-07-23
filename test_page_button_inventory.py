# -*- coding: utf-8 -*-
"""Regression: no orphaned CTAs leak across pages; page button inventories."""

from __future__ import annotations

import re
import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest

# Keys that belong only to unlocked result — must never appear elsewhere.
RESULT_ONLY_KEYS = {
    "food_go_for_it",
    "reroll_btn",
    "do_it_primary",
    "fridge_cook_accept",
    "fridge_shop_escape",
}
MEAL_SEG_KEYS = {
    "meal_seg_frukost",
    "meal_seg_lunch",
    "meal_seg_middag",
    "meal_seg_kvallsmal",
}


def _boot(**session: object) -> AppTest:
    with mock.patch("supabase_client.is_configured", return_value=False):
        with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
            with mock.patch("db._use_supabase", return_value=False):
                at = AppTest.from_file("app.py", default_timeout=90)
                at.run()
                at.session_state["_auth_cookie_checked"] = True
                at.session_state["_oc_cookie_component_ready"] = True
                at.session_state["guest_mode"] = True
                at.session_state["user_id"] = "uid-page-btns"
                at.session_state["language"] = "sv"
                at.session_state["ui_error"] = None
                at.session_state["page"] = "home"
                for k, v in session.items():
                    at.session_state[k] = v
                at.run()
                return at


def _keys(at: AppTest) -> set[str]:
    out: set[str] = set()
    for b in at.button:
        k = getattr(b, "key", None)
        if k:
            out.add(str(k))
    return out


def _labels(at: AppTest) -> list[str]:
    return [str(getattr(b, "label", "") or "") for b in at.button]


class PageButtonInventoryTests(unittest.TestCase):
    def test_home_has_no_result_ctas(self) -> None:
        at = _boot(page="home", _force_home_chooser=True, accepted=False, current=None)
        self.assertEqual(at.session_state["page"], "home")
        self.assertFalse(at.exception)
        keys = _keys(at)
        for banned in RESULT_ONLY_KEYS | MEAL_SEG_KEYS:
            self.assertNotIn(banned, keys, f"{banned} leaked onto home")
        labels = _labels(at)
        self.assertNotIn("Välj", labels)
        self.assertNotIn("Nytt förslag", labels)
        self.assertTrue(any("Bestäm" in lab for lab in labels), labels)
        # Domain cards
        for domain in ("food", "clothes", "movie", "workout", "weekend", "fridge"):
            self.assertTrue(
                any(str(k).startswith(f"home_domain_{domain}") for k in keys),
                keys,
            )
        # Hem is the active tab on home
        nav_home = next(b for b in at.button if getattr(b, "key", None) == "nav_home")
        self.assertEqual(getattr(nav_home.proto, "type", None), "primary")

    def test_unlocked_result_has_valj_and_reroll(self) -> None:
        at = _boot(
            page="result",
            accepted=False,
            food_meal_type="middag",
            current={
                "ok": True,
                "domain": "food",
                "suggestion": "Pasta",
                "justification": "Test",
                "accepted": False,
                "locked": False,
                "reroll_index": 0,
                "context": {"meal_type": "middag"},
                "execution_type": "checklist",
                "execution_label": "Laga",
            },
        )
        self.assertEqual(at.session_state["page"], "result")
        keys = _keys(at)
        self.assertIn("food_go_for_it", keys)
        self.assertIn("reroll_btn", keys)
        self.assertIn("Välj", _labels(at))

    def test_nav_home_clears_result_keys_from_session(self) -> None:
        at = _boot(
            page="result",
            accepted=False,
            food_meal_type="middag",
            current={
                "ok": True,
                "domain": "food",
                "suggestion": "Pasta",
                "justification": "Test",
                "accepted": False,
                "locked": False,
                "context": {"meal_type": "middag"},
            },
        )
        self.assertIn("food_go_for_it", _keys(at))
        nav = [b for b in at.button if getattr(b, "key", None) == "nav_home"]
        self.assertTrue(nav)
        nav[-1].click().run()
        self.assertEqual(at.session_state["page"], "home")
        for banned in RESULT_ONLY_KEYS:
            self.assertNotIn(banned, at.session_state, banned)
        # Production contract: session keys cleared (AppTest may still ghost widgets).
        self.assertNotIn("food_go_for_it", list(at.session_state.to_dict() if hasattr(at.session_state, "to_dict") else []))
        try:
            _ = at.session_state["food_go_for_it"]
            self.fail("food_go_for_it still in session_state")
        except KeyError:
            pass

    def test_execute_has_no_prelock_ctas(self) -> None:
        at = _boot(
            page="execute",
            accepted=True,
            food_meal_type="middag",
            current={
                "ok": True,
                "domain": "food",
                "suggestion": "Pasta",
                "justification": "Test",
                "accepted": True,
                "locked": True,
                "decision_id": 42,
                "context": {
                    "meal_type": "middag",
                    "shopping": {
                        "to_buy": {"pasta": 1, "tomat": 2, "ost": 1},
                        "already_have": [],
                    },
                    "recipe": {
                        "title": "Pasta",
                        "steps": ["Koka.", "Rör."],
                        "ingredient_lines": ["pasta", "tomat", "ost"],
                        "portioner": 1,
                        "active_minutes": 15,
                    },
                },
                "execution_type": "checklist",
                "execution_label": "Laga",
            },
        )
        self.assertEqual(at.session_state["page"], "execute")
        keys = _keys(at)
        for banned in RESULT_ONLY_KEYS | MEAL_SEG_KEYS:
            self.assertNotIn(banned, keys, banned)
        self.assertNotIn("Välj", _labels(at))
        self.assertNotIn("Nytt förslag", _labels(at))
        self.assertNotIn("eat_reopen", keys)
        # Sticky list CTA when shopping exists
        self.assertTrue(
            any("exec_create_list" in k or "exec_open_lista" in k for k in keys)
            or any("Lägg till" in lab for lab in _labels(at)),
            keys,
        )
        # Nav: no tab is primary on execute — only the active mode lights up
        for b in at.button:
            key = getattr(b, "key", None)
            if key not in ("nav_home", "nav_lista", "nav_history", "nav_profile"):
                continue
            proto = getattr(b, "proto", None)
            btype = getattr(proto, "type", None) if proto is not None else None
            self.assertEqual(
                btype,
                "secondary",
                f"{key} must be secondary on execute, got {btype!r}",
            )

    def test_nav_from_execute_reaches_lista_and_home(self) -> None:
        """Footer taps must change page even when every tab is secondary."""
        at = _boot(
            page="execute",
            accepted=True,
            food_meal_type="frukost",
            current={
                "ok": True,
                "domain": "food",
                "suggestion": "Havregrynsgröt med banan",
                "justification": "Test",
                "accepted": True,
                "locked": True,
                "decision_id": 42,
                "context": {
                    "meal_type": "frukost",
                    "recipe": {
                        "title": "Havregrynsgröt med banan",
                        "steps": [
                            "Koka upp 2 dl vatten med 1 krm salt.",
                            "Rör ner 1 dl havregryn. Sjud 3–4 min.",
                            "Skiva banan ovanpå. Servera varm.",
                        ],
                        "ingredient_lines": [
                            "havregryn 1 dl",
                            "vatten 2 dl",
                            "salt 1 krm",
                            "banan 1 st",
                        ],
                        "portioner": 1,
                        "active_minutes": 5,
                        "nutrition": {
                            "kcal": 350,
                            "protein_g": 10,
                            "fat_g": 5,
                            "carbs_g": 65,
                        },
                    },
                },
                "execution_type": "checklist",
                "execution_label": "Laga",
            },
        )
        self.assertEqual(at.session_state["page"], "execute")
        next(b for b in at.button if getattr(b, "key", None) == "nav_lista").click().run()
        self.assertEqual(at.session_state["page"], "lista")
        self.assertFalse(at.exception)
        # Direct home chooser — same path as tapping Hem in the footer
        at.session_state["_force_home_chooser"] = True
        at.session_state["page"] = "home"
        at.run()
        self.assertEqual(at.session_state["page"], "home")
        self.assertIn("Mat", _labels(at))
        # Hem is primary only on home; Lista was reachable while all tabs were secondary
        nav_home = next(b for b in at.button if getattr(b, "key", None) == "nav_home")
        self.assertEqual(getattr(nav_home.proto, "type", None), "primary")

    def test_execute_frukost_has_no_list_cta(self) -> None:
        at = _boot(
            page="execute",
            accepted=True,
            food_meal_type="frukost",
            current={
                "ok": True,
                "domain": "food",
                "suggestion": "Havregrynsgröt",
                "justification": "Test",
                "accepted": True,
                "locked": True,
                "decision_id": 7,
                "context": {
                    "meal_type": "frukost",
                    "recipe": {
                        "title": "Havregrynsgröt",
                        "steps": ["Koka."],
                        "ingredient_lines": ["havregryn"],
                        "portioner": 1,
                        "active_minutes": 5,
                    },
                },
                "execution_type": "checklist",
                "execution_label": "Laga",
            },
        )
        keys = _keys(at)
        self.assertNotIn("exec_create_list", keys)
        self.assertNotIn("food_go_for_it", keys)
        self.assertNotIn("Välj", _labels(at))

    def test_lista_history_profile_no_valj(self) -> None:
        for page in ("lista", "history", "profile"):
            at = _boot(page=page, accepted=False, current=None)
            self.assertEqual(at.session_state["page"], page, page)
            self.assertNotIn("Välj", _labels(at), page)
            keys = _keys(at)
            for banned in RESULT_ONLY_KEYS:
                self.assertNotIn(banned, keys, f"{banned} on {page}")

    def test_portion_pluralization_helper(self) -> None:
        import app as app_mod

        with mock.patch.object(app_mod, "st") as st_mock:
            st_mock.session_state = {"language": "sv"}
            # Bind t() via real app language
        self.assertEqual(app_mod._food_portion_label(1, "sv"), "1 portion")
        self.assertEqual(app_mod._food_portion_label(2, "sv"), "2 portioner")
        self.assertEqual(app_mod._food_portion_label(0, "sv"), "1 portion")

    def test_food_card_embeds_fav_and_share_corners(self) -> None:
        import app as app_mod

        html = app_mod._render_food_card_html(
            language="sv",
            suggestion="Pasta",
            justification="God",
            ctx={"meal_type": "middag", "recipe": {"portioner": 1, "active_minutes": 10}},
            share_corner_html='<span class="oc-share-corner">S</span>',
            fav_corner_html='<span class="oc-fav-corner">F</span>',
        )
        self.assertIn("oc-fav-corner", html)
        self.assertIn("oc-share-corner", html)
        # fav before share before image
        self.assertLess(html.index("oc-fav-corner"), html.index("oc-share-corner"))
        self.assertIn("1 portion", html)
        self.assertNotIn("1 portioner", html)

    def test_css_hides_result_ctas_outside_result(self) -> None:
        """Orphan Välj defense: CSS belt hides result CTAs when .oc-result is absent."""
        import app as app_mod
        from pathlib import Path

        src = open(app_mod.__file__, encoding="utf-8").read()
        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        self.assertIn("oc-result", css)
        self.assertIn("food_go_for_it", src)
        self.assertIn("oc-fav-corner", src)
        self.assertIn("top: 12px", css)
        self.assertIn(
            "body:not(:has(.oc-result)) .st-key-result_primary_btn",
            css,
        )
        self.assertIn(
            'body:not(:has(.oc-result)) [class*="st-key-food_go_for_it"]',
            css,
        )


if __name__ == "__main__":
    unittest.main()
