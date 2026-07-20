# -*- coding: utf-8 -*-
"""Regression: no leaked widget labels (q, duplicate Måltid) or nutrition crashes."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db


class UiLeakTests(unittest.TestCase):
    def test_home_has_no_stray_q_label(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        body = " ".join(str(m.value or "") for m in at.markdown)
        caps = " ".join(str(c.value or "") for c in at.caption)
        # Collapsed textarea label must not leak as a lone "q"
        self.assertNotRegex(body + caps, r"(?<![a-zA-ZåäöÅÄÖ])q(?![a-zA-ZåäöÅÄÖ])")
        self.assertIn("oc-chip-row", body)

    def test_food_result_single_meal_label(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.query_params["domain"] = "food"
        at.run()
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-sec-label", body)
        # One section label — not caption + pills label duplicate
        self.assertLessEqual(body.lower().count("måltid"), 2)

    def test_nutrition_survives_missing_format_fn(self) -> None:
        import app as app_mod
        import shopping

        recipe = {
            "title": "Havregrynsgröt med banan",
            "ingredients": ["havregryn", "mjölk", "banan"],
            "steps": ["Koka."],
            "kcal_per_portion": 350,
            "protein_g_per_portion": 15,
            "portioner": 1,
        }
        with mock.patch.object(shopping, "format_nutrition_line", None, create=True):
            with mock.patch.object(shopping, "ensure_recipe_nutrition", None, create=True):
                with mock.patch.object(app_mod.st, "session_state", {"language": "sv"}):
                    line, has_vals = app_mod._nutrition_display_line(recipe)
        self.assertIn("≈", line)
        self.assertIn("kcal", line.lower())
        self.assertTrue(has_vals)

    def test_accept_food_does_not_crash_execute(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "frukost"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if b.label and "Ät nu" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(at.exception)
        self.assertFalse(bool(at.session_state["ui_error"]))
        body = " ".join(str(m.value or "") for m in at.markdown).lower()
        self.assertNotIn("attributeerror", body)
        self.assertIn("recept", body)


if __name__ == "__main__":
    unittest.main()
