# -*- coding: utf-8 -*-
"""Canonical happy-path smoke test — login → home → food → execute → lista → home."""

from __future__ import annotations

import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest


class HappyPathSmokeTest(unittest.TestCase):
    """End-to-end AppTest: session-safe navigation and auth preserved throughout."""

    def _click_nav(self, at: AppTest, target: str) -> None:
        key = f"nav_{target}"
        matches = [b for b in at.button if getattr(b, "key", None) == key]
        if not matches:
            self.fail(
                f"nav button {key!r} not in {[getattr(b, 'key', None) for b in at.button]}"
            )
        # AppTest may retain prior-page nav widgets after page transitions — use latest.
        matches[-1].click().run()

    def _boot_authenticated(self) -> AppTest:
        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("db._use_supabase", return_value=False):
                    at = AppTest.from_file("app.py", default_timeout=120)
                    at.run()
                    at.session_state["access_token"] = "smoke-at"
                    at.session_state["refresh_token"] = "smoke-rt"
                    at.session_state["user_id"] = "uid-smoke"
                    at.session_state["guest_mode"] = False
                    at.session_state["page"] = "home"
                    at.session_state["_auth_cookie_checked"] = True
                    at.session_state["food_meal_type"] = "middag"
                    at.run()
                    return at

    def _assert_authenticated(self, at: AppTest) -> None:
        self.assertNotEqual(at.session_state["page"], "auth")
        self.assertEqual(at.session_state["access_token"], "smoke-at")
        self.assertEqual(at.session_state["user_id"], "uid-smoke")
        self.assertFalse(bool(at.session_state["guest_mode"]))

    def test_full_happy_path(self) -> None:
        at = self._boot_authenticated()
        self._assert_authenticated(at)

        at.session_state["food_meal_type"] = "middag"
        # Home → Mat card
        mat = next(b for b in at.button if (b.label or "") == "Mat")
        mat.click().run()
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "result")

        # Decision → Gör det → execute (no intermediate lock card)
        go = next(b for b in at.button if (b.label or "") == "Gör det")
        go.click().run()
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "execute")
        self.assertTrue(at.session_state["accepted"])

        # Toggle checklist items
        boxes = list(at.checkbox)
        self.assertGreaterEqual(len(boxes), 2, [getattr(c, "label", None) for c in boxes])
        boxes[0].check().run()
        self.assertEqual(at.session_state["page"], "execute")
        boxes = list(at.checkbox)
        boxes[1].check().run()
        self.assertEqual(at.session_state["page"], "execute")

        # Lägg till i listan
        add_btn = next(
            b for b in at.button if b.label and "Lägg till i listan (2)" in b.label
        )
        add_btn.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "execute")
        cache = at.session_state["shopping_list_cache"]
        self.assertIsInstance(cache, list)
        self.assertGreaterEqual(len(cache), 2)
        self.assertIsNotNone(at.session_state["shopping_merged_for"])

        # Lista nav
        self._click_nav(at, "lista")
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "lista")
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Inköpslista", body)

        # Hem nav from lista
        self._click_nav(at, "home")
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "home")

    def test_home_nav_from_execute(self) -> None:
        """Regression: Hem must work inside execute view (not a dead pill)."""
        at = self._boot_authenticated()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Gör det":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")

        self._click_nav(at, "home")
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "home")


if __name__ == "__main__":
    unittest.main()
