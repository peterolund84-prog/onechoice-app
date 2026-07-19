# -*- coding: utf-8 -*-
"""Opt-in nutrition estimates — recipe view only, never decision card."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import feasibility
import shopping


class NutritionEstimateTests(unittest.TestCase):
    def test_round_aggressive(self) -> None:
        r = shopping.round_nutrition(523, 43, 17, 58)
        self.assertEqual(r["kcal"], 500)
        self.assertEqual(r["protein_g"], 45)
        self.assertEqual(r["fat_g"], 15)
        self.assertEqual(r["carbs_g"], 60)

    def test_build_recipe_includes_ca_nutrition(self) -> None:
        recipe = shopping.build_recipe(
            "Kycklingwok med ris",
            ["kycklingfilé", "ris", "broccoli", "olja", "salt", "peppar"],
        )
        nut = recipe.get("nutrition") or {}
        self.assertEqual(nut.get("label"), "ca-värden")
        self.assertEqual(nut.get("per"), "portion")
        self.assertIn(nut.get("kcal"), range(0, 2001))
        self.assertEqual(nut["kcal"] % 50, 0)
        self.assertEqual(nut["protein_g"] % 5, 0)
        line = shopping.format_nutrition_line(nut, language="sv")
        self.assertIn("ca-värden", line)
        self.assertIn("kcal", line)
        self.assertIn("protein", line)
        self.assertNotIn("mål", line.lower())
        self.assertNotIn("streak", line.lower())

    def test_eggs_scramble_is_one_portion(self) -> None:
        recipe = shopping.build_recipe("Äggröra", ["ägg", "smör", "salt"])
        self.assertEqual((recipe.get("nutrition") or {}).get("servings"), 1)

    def test_profile_nutrition_off_by_default(self) -> None:
        profile = feasibility.parse_profile({"id": "u", "profile_json": {}}, {})
        self.assertFalse(profile["food"]["show_nutrition"])

    def test_profile_nutrition_opt_in_persists(self) -> None:
        profile = feasibility.parse_profile(
            {"id": "u", "profile_json": {"food": {"show_nutrition": True}}},
            {},
        )
        self.assertTrue(profile["food"]["show_nutrition"])


class NutritionUiPlacementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_recipe_block_hides_nutrition_when_off(self) -> None:
        import app as app_mod

        recipe = shopping.build_recipe(
            "Proteinomelett med grönt",
            ["ägg", "mjölk", "ost", "spenat", "smör"],
        )
        # Capture markdown HTML without running full Streamlit
        html_chunks: list[str] = []

        def fake_markdown(body, **kwargs):
            html_chunks.append(str(body))

        with mock.patch.object(app_mod.st, "markdown", side_effect=fake_markdown):
            with mock.patch.object(app_mod.st, "session_state", {"language": "sv"}):
                app_mod.render_recipe_block(recipe, show_nutrition=False)
        blob = " ".join(html_chunks).lower()
        self.assertIn("recept", blob)
        self.assertNotIn("ca-värden", blob)
        self.assertNotIn("kcal", blob)

    def test_recipe_block_shows_muted_line_when_on(self) -> None:
        import app as app_mod

        recipe = shopping.build_recipe(
            "Proteinomelett med grönt",
            ["ägg", "mjölk", "ost", "spenat", "smör"],
        )
        html_chunks: list[str] = []

        def fake_markdown(body, **kwargs):
            html_chunks.append(str(body))

        with mock.patch.object(app_mod.st, "markdown", side_effect=fake_markdown):
            with mock.patch.object(app_mod.st, "session_state", {"language": "sv"}):
                app_mod.render_recipe_block(recipe, show_nutrition=True)
        blob = " ".join(html_chunks)
        self.assertIn("oc-nutrition", blob)
        self.assertIn("ca-värden", blob)
        # Under ingredients, before steps
        ings_i = blob.find("Ingredienser") if "Ingredienser" in blob else blob.lower().find("ingredients")
        nut_i = blob.find("ca-värden")
        steps_i = blob.find("Gör så här") if "Gör så här" in blob else blob.lower().find("steps")
        self.assertGreater(nut_i, ings_i)
        if steps_i > 0:
            self.assertLess(nut_i, steps_i)

    def test_decision_result_has_no_nutrition_copy(self) -> None:
        """Decision card path must not surface kcal (opt-in lives on execute only)."""
        import pipeline

        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta till middag?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={"meal_type": "middag"},
        )
        self.assertTrue(r.ok)
        card = f"{r.suggestion} {r.justification}".lower()
        self.assertNotIn("kcal", card)
        self.assertNotIn("ca-värden", card)
        # Recipe payload may still carry estimates for later execute view
        recipe = (r.context or {}).get("recipe") or {}
        if isinstance(recipe, dict) and recipe.get("nutrition"):
            self.assertEqual(recipe["nutrition"].get("label"), "ca-värden")


if __name__ == "__main__":
    unittest.main()
