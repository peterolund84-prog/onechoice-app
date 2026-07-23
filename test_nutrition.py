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
        self.assertTrue(line.startswith("Ca "))
        self.assertIn("kcal", line)
        self.assertIn("per portion", line)
        self.assertIn("protein", line)
        self.assertIn("fett", line)
        self.assertIn("kolh", line)
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
        self.assertIn("Ca ", line)
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

    def test_profile_nutrition_on_by_default(self) -> None:
        profile = feasibility.parse_profile({"id": "u", "profile_json": {}}, {})
        self.assertTrue(profile["food"]["show_nutrition"])

    def test_leftover_reheat_nutrition_hidden(self) -> None:
        import food_domain as fd

        recipe = fd.reheat_execution_recipe("Matlåda från gårdagens pasta")
        self.assertFalse(shopping.nutrition_segment_visible(recipe))
        line = shopping.format_nutrition_line(recipe.get("nutrition"), language="sv", recipe=recipe)
        self.assertEqual(line, "Näringsvärden saknas")

    def test_profile_nutrition_opt_out_persists(self) -> None:
        profile = feasibility.parse_profile(
            {"id": "u", "profile_json": {"food": {"show_nutrition": False}}},
            {},
        )
        self.assertFalse(profile["food"]["show_nutrition"])


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

    def test_recipe_block_shows_stat_row_when_on(self) -> None:
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
        self.assertIn("oc-nut-stats", blob)
        self.assertIn("oc-nut-val", blob)
        self.assertIn("KCAL", blob)
        self.assertIn("PROTEIN", blob)
        self.assertIn("FETT", blob)
        self.assertIn("KOLH", blob)
        self.assertIn("Per portion", blob)
        self.assertIn("oc-nut-per", blob)
        # No boxed legacy sentence on the recipe card
        self.assertNotIn("oc-nutrition", blob)
        self.assertNotIn("Ca ", blob)
        # Stat row sits under RECEPT title, before ingredients
        title_i = blob.lower().find("recept")
        nut_i = blob.find("oc-nut-stats")
        ings_i = blob.find("Ingredienser") if "Ingredienser" in blob else blob.lower().find("ingredients")
        self.assertGreater(nut_i, title_i)
        self.assertLess(nut_i, ings_i)

    def test_recipe_block_legacy_empty_hides_nutrition(self) -> None:
        import app as app_mod

        html_chunks: list[str] = []

        def fake_markdown(body, **kwargs):
            html_chunks.append(str(body))

        with mock.patch.object(app_mod.st, "markdown", side_effect=fake_markdown):
            with mock.patch.object(app_mod.st, "session_state", {"language": "sv"}):
                with mock.patch.object(
                    app_mod,
                    "_nutrition_stat_row_html",
                    return_value="",
                ):
                    app_mod.render_recipe_block(
                        {"title": "X", "ingredients": [], "steps": ["Ät"]},
                        show_nutrition=True,
                    )
        blob = " ".join(html_chunks)
        self.assertNotIn("Näringsvärden saknas", blob)
        self.assertNotIn("kcal", blob.lower())
        self.assertNotIn("oc-nut-stats", blob)

    def test_decision_result_has_no_nutrition_copy(self) -> None:
        """Decision card path must not surface kcal (opt-in lives in profile + recipe card)."""
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
    def _enable_profile_nutrition(self, at) -> None:
        """Opt-in via profile — not an execute-screen toggle."""
        uid = at.session_state["user_id"]
        import db

        user = db.ensure_user(uid)
        raw = user.get("profile_json") or {}
        if not isinstance(raw, dict):
            raw = {}
        food = dict(raw.get("food") or {})
        food["show_nutrition"] = True
        raw["food"] = food
        db.update_user(uid, profile_json=raw)

    def test_profile_nutrition_shows_stat_row_on_execute(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        # Nutrition is ON by default — profile opt-out remains available
        at.session_state["food_meal_type"] = "kvallsmal"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-nut-stats", body)
        self.assertIn("KCAL", body)
        self.assertIn("PROTEIN", body)
        self.assertIn("FETT", body)
        self.assertIn("KOLH", body)
        self.assertIn("Per portion", body)
        self.assertNotIn("oc-nut-banner", body)
        self.assertNotIn("None", body)
        self.assertNotRegex(body, r"Ca\s+\d+\s*kcal")

    def test_legacy_history_recipe_without_fields_on_execute(self) -> None:
        """Old accepted decision missing nutrition fields must still paint a stat row."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "kvallsmal"
        at.query_params["domain"] = "food"
        at.run()
        cur = dict(at.session_state["current"] or {})
        ctx = dict(cur.get("context") or {})
        ctx["recipe"] = {
            "title": cur.get("suggestion") or "Smörgås med ost",
            "ingredients": ["bröd 2 skivor", "ost 2 skivor", "smör 1 tsk"],
            "steps": [
                "Ta fram 2 skivor bröd och 2 skivor ost.",
                "Bred 1 tsk smör på brödet och lägg på osten.",
                "Servera direkt — eller grilla 1 min om du vill ha den varm.",
            ],
            "nutrition": {"kcal": 450, "protein_g": 20, "fat_g": 25, "carbs_g": 35},
        }
        cur["context"] = ctx
        at.session_state["current"] = cur
        at.session_state["accepted"] = True
        at.session_state["page"] = "execute"
        at.run()
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(at.exception)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-nut-stats", body)
        self.assertIn("KCAL", body)
        self.assertNotIn("Näringsvärden saknas", body)
        self.assertNotIn("None", body)

    def test_all_food_recipe_paths_use_render_food_recipe(self) -> None:
        """Execute leftover, main recipe, and shared landing share one kcal path."""
        import inspect
        import app as app_mod

        src = inspect.getsource(app_mod.page_execute)
        self.assertIn("render_food_recipe", src)
        self.assertNotIn("show_nutrition=False", src)
        share_src = inspect.getsource(app_mod.page_shared)
        self.assertIn("render_food_recipe", share_src)
        food_src = inspect.getsource(app_mod.render_food_recipe)
        self.assertIn("show_nutrition = True", food_src)

    def test_css_uses_st_key_for_lang_and_nav(self) -> None:
        import inspect
        from pathlib import Path

        import app as app_mod

        css_src = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        self.assertIn("st-key-oc_lang_bar", css_src)
        self.assertIn("st-key-oc_nav_bar", css_src)
        lang_src = inspect.getsource(app_mod.lang_bar)
        self.assertIn('key="oc_lang_bar"', lang_src)
        nav_src = inspect.getsource(app_mod.nav)
        self.assertIn('key="oc_nav_bar"', nav_src)
        self.assertIn('key=f"nav_', nav_src)


if __name__ == "__main__":
    unittest.main()
