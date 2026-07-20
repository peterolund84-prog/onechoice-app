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

    def test_build_recipe_includes_top_level_portion_fields(self) -> None:
        recipe = shopping.build_recipe(
            "Kycklingwok med ris",
            ["kycklingfilé", "ris", "broccoli", "olja", "salt", "peppar"],
        )
        self.assertIsInstance(recipe.get("kcal_per_portion"), int)
        self.assertIsInstance(recipe.get("protein_g_per_portion"), int)
        self.assertIsInstance(recipe.get("portioner"), int)
        self.assertGreater(recipe["kcal_per_portion"], 0)
        self.assertGreaterEqual(recipe["protein_g_per_portion"], 0)
        self.assertGreaterEqual(recipe["portioner"], 1)
        nut = recipe.get("nutrition") or {}
        self.assertEqual(nut.get("kcal"), recipe["kcal_per_portion"])
        self.assertEqual(nut.get("protein_g"), recipe["protein_g_per_portion"])
        line = shopping.format_nutrition_line(nut, language="sv", recipe=recipe)
        self.assertTrue(line.startswith("≈ "))
        self.assertIn("kcal", line)
        self.assertIn("protein", line)
        self.assertIn("/ portion", line)
        self.assertNotIn("None", line)
        self.assertNotIn("null", line.lower())

    def test_eggs_scramble_is_one_portion(self) -> None:
        recipe = shopping.build_recipe("Äggröra", ["ägg", "smör", "salt"])
        self.assertEqual(recipe.get("portioner"), 1)
        self.assertEqual((recipe.get("nutrition") or {}).get("servings"), 1)

    def test_legacy_recipe_without_nutrition_heals(self) -> None:
        """History payloads missing fields must not crash — estimate fills them."""
        old = {
            "title": "Äggröra",
            "ingredients": ["ägg", "smör", "salt"],
            "steps": ["Rör om äggen.", "Ät."],
        }
        healed = shopping.ensure_recipe_nutrition(old, suggestion="Äggröra")
        self.assertTrue(
            shopping.nutrition_fields_valid(
                healed.get("kcal_per_portion"),
                healed.get("protein_g_per_portion"),
                healed.get("portioner"),
            )
        )
        line = shopping.format_nutrition_line(None, language="sv", recipe=healed)
        self.assertIn("≈", line)
        self.assertIn("kcal", line)

    def test_format_missing_never_empty(self) -> None:
        line = shopping.format_nutrition_line(None, language="sv")
        self.assertEqual(line, "Näringsvärden saknas")
        line_en = shopping.format_nutrition_line({}, language="en")
        self.assertEqual(line_en, "Nutrition unavailable")

    def test_non_numeric_fields_trigger_reestimate(self) -> None:
        bad = {
            "title": "Lax med potatis",
            "ingredients": ["lax", "potatis", "smör"],
            "steps": ["Ugn"],
            "kcal_per_portion": "mycket",
            "protein_g_per_portion": None,
            "portioner": "två",
        }
        healed = shopping.ensure_recipe_nutrition(bad, suggestion="Lax med potatis")
        self.assertIsInstance(healed["kcal_per_portion"], int)
        self.assertIsInstance(healed["protein_g_per_portion"], int)
        self.assertIsInstance(healed["portioner"], int)

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
        html_chunks: list[str] = []

        def fake_markdown(body, **kwargs):
            html_chunks.append(str(body))

        with mock.patch.object(app_mod.st, "markdown", side_effect=fake_markdown):
            with mock.patch.object(app_mod.st, "session_state", {"language": "sv"}):
                app_mod.render_recipe_block(recipe, show_nutrition=False)
        blob = " ".join(html_chunks).lower()
        self.assertIn("recept", blob)
        self.assertNotIn("kcal", blob)
        self.assertNotIn("näringsvärden saknas", blob)

    def test_recipe_block_shows_approx_line_when_on(self) -> None:
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
        self.assertIn("≈", blob)
        self.assertIn("kcal", blob)
        self.assertIn("protein", blob)
        self.assertIn("/ portion", blob)
        # Under ingredients, before steps
        ings_i = blob.find("Ingredienser") if "Ingredienser" in blob else blob.lower().find("ingredients")
        nut_i = blob.find("≈")
        steps_i = blob.find("Gör så här") if "Gör så här" in blob else blob.lower().find("steps")
        self.assertGreater(nut_i, ings_i)
        if steps_i > 0:
            self.assertLess(nut_i, steps_i)

    def test_recipe_block_legacy_empty_shows_missing_not_blank(self) -> None:
        import app as app_mod

        # Force no estimate by empty ingredients + disallow via mocking ensure
        html_chunks: list[str] = []

        def fake_markdown(body, **kwargs):
            html_chunks.append(str(body))

        with mock.patch.object(app_mod.st, "markdown", side_effect=fake_markdown):
            with mock.patch.object(app_mod.st, "session_state", {"language": "sv"}):
                with mock.patch.object(
                    app_mod,
                    "_nutrition_display_line",
                    return_value=("Näringsvärden saknas", False),
                ):
                    app_mod.render_recipe_block(
                        {"title": "X", "ingredients": [], "steps": ["Ät"]},
                        show_nutrition=True,
                    )
        blob = " ".join(html_chunks)
        self.assertIn("Näringsvärden saknas", blob)
        self.assertNotIn("None", blob)
        self.assertNotIn("null", blob.lower())

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
        self.assertNotIn("≈", card)
        recipe = (r.context or {}).get("recipe") or {}
        if isinstance(recipe, dict):
            self.assertIn("kcal_per_portion", recipe)


class NutritionExecuteFlowTests(unittest.TestCase):
    def test_new_recipe_toggle_shows_approx_values(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "kvallsmal"
        at.query_params["domain"] = "food"
        at.run()
        hit = False
        for b in at.button:
            if b.label and "Ät nu" in b.label:
                b.click().run()
                hit = True
                break
        self.assertTrue(hit)
        self.assertEqual(at.session_state["page"], "execute")
        # Turn nutrition on
        for tgl in at.toggle:
            tgl.set_value(True).run()
            break
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("≈", body)
        self.assertIn("kcal", body.lower())
        self.assertIn("protein", body.lower())
        self.assertIn("oc-nut-banner", body)
        self.assertNotIn("None", body)
        self.assertRegex(body, r"≈\s*\d+\s*kcal")

    def test_legacy_history_recipe_without_fields_on_execute(self) -> None:
        """Old accepted decision missing nutrition fields must still paint a line."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "kvallsmal"
        at.query_params["domain"] = "food"
        at.run()
        cur = dict(at.session_state["current"] or {})
        ctx = dict(cur.get("context") or {})
        # Strip nutrition like an old history row
        ctx["recipe"] = {
            "title": cur.get("suggestion") or "Ostsmörgås",
            "ingredients": ["bröd", "ost", "smör"],
            "steps": ["Bred smör.", "Lägg ost.", "Ät."],
        }
        cur["context"] = ctx
        at.session_state["current"] = cur
        at.session_state["accepted"] = True
        at.session_state["page"] = "execute"
        at.session_state["exec_show_nutrition"] = True
        at.run()
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(at.exception)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("≈", body)
        self.assertIn("kcal", body.lower())
        self.assertNotIn("Näringsvärden saknas", body)
        self.assertNotIn("None", body)


if __name__ == "__main__":
    unittest.main()
