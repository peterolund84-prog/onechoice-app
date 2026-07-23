# -*- coding: utf-8 -*-
"""Structured recipe engine — no stubs, validation, catalog + template fallbacks."""

from __future__ import annotations

import unittest

import recipe_engine as reng
import shopping


class RecipeEngineValidationTests(unittest.TestCase):
    def test_rejects_title_as_only_ingredient(self) -> None:
        stub = {
            "title": "Havregrynsgröt med banan",
            "ingredients": ["Havregrynsgröt med banan"],
            "steps": [
                "Koka 2 dl vatten med salt.",
                "Rör ner 1 dl havregryn och sjud 3 min.",
                "Skiva banan ovanpå och servera.",
            ],
            "nutrition": {"kcal": 350, "protein_g": 10, "fat_g": 5, "carbs_g": 65},
        }
        ok, reason = reng.validate_recipe(stub, title="Havregrynsgröt med banan")
        self.assertFalse(ok)
        self.assertEqual(reason, "too_few_ingredients")

    def test_rejects_placeholder_steps(self) -> None:
        stub = {
            "title": "Test",
            "ingredients": ["a", "b"],
            "steps": [
                "Ta fram det du behöver.",
                "Gör i ordning och ät.",
                "Servera.",
            ],
            "nutrition": {"kcal": 100, "protein_g": 5, "fat_g": 5, "carbs_g": 10},
        }
        ok, _ = reng.validate_recipe(stub, title="Test")
        self.assertFalse(ok)

    def test_rejects_ungrounded_step_food(self) -> None:
        """'2 dl ris' in steps with no ris ingredient must fail."""
        bad = {
            "title": "Wrap med kyckling",
            "ingredients": [
                {"name": "tortilla", "amount": "2", "unit": "st"},
                {"name": "kycklingfilé", "amount": "200", "unit": "g"},
                {"name": "yoghurt", "amount": "2", "unit": "msk"},
            ],
            "steps": [
                "Skölj 2 dl ris och koka enligt förpackningen.",
                "Skär 400 g kycklingfilé i bitar. Hacka grönsakerna.",
                "Servera kycklingen med tillbehöret. Klart.",
            ],
            "nutrition": {"kcal": 500, "protein_g": 40, "fat_g": 15, "carbs_g": 30},
        }
        ok, reason = reng.validate_recipe(bad, title="Wrap med kyckling")
        self.assertFalse(ok)
        self.assertTrue(
            reason.startswith("uncovered_ingredient:")
            or reason.startswith("ungrounded_step_food:"),
            msg=reason,
        )
        self.assertTrue("ris" in reason or "tortilla" in reason or "yoghurt" in reason)

    def test_rejects_uncovered_ingredient(self) -> None:
        bad = {
            "title": "Wrap med kyckling",
            "ingredients": [
                {"name": "tortilla", "amount": "2", "unit": "st"},
                {"name": "kycklingfilé", "amount": "200", "unit": "g"},
                {"name": "yoghurt", "amount": "2", "unit": "msk"},
            ],
            "steps": [
                "Värm 2 tortilla i torr panna 20 sek per sida.",
                "Skär 200 g kycklingfilé i strimlor. Stek 5 min.",
                "Rulla ihop wrapen. Servera direkt.",
            ],
            "nutrition": {"kcal": 480, "protein_g": 38, "fat_g": 14, "carbs_g": 42},
        }
        ok, reason = reng.validate_recipe(bad, title="Wrap med kyckling")
        self.assertFalse(ok)
        self.assertEqual(reason, "uncovered_ingredient:yoghurt")

    def test_generic_protein_template_rejected_for_wrap_hints(self) -> None:
        """Fail-closed: protein+ris prose must not pass as a wrap recipe."""
        tmpl = reng._template_from_hints(
            "Något med kyckling",
            meal_type="middag",
            hints=["tortilla", "kycklingfilé", "yoghurt", "sallad"],
            active_minutes=15,
        )
        # Either dish-aware wrap steps (ok) or None — never ris-without-ingredient
        if tmpl is not None:
            blob = " ".join(tmpl["steps"]).lower()
            self.assertNotIn("2 dl ris", blob)
            self.assertTrue(
                reng.recipe_is_valid(reng._finalize_recipe(tmpl, source="template"))
            )


class RecipeEngineMaterializeTests(unittest.TestCase):
    def test_havregrynsgröt_has_real_ingredients_and_steps(self) -> None:
        recipe = reng.materialize_recipe(
            "Havregrynsgröt med banan",
            meal_type="frukost",
            allow_llm=False,
        )
        self.assertEqual(recipe.get("recipe_source"), "catalog")
        self.assertGreaterEqual(len(recipe.get("ingredients") or []), 3)
        self.assertGreaterEqual(len(recipe.get("steps") or []), 3)
        blob = " ".join(recipe["ingredients"]).lower()
        self.assertIn("havregryn", blob)
        self.assertNotIn("havregrynsgröt med banan", blob)
        steps = " ".join(recipe["steps"]).lower()
        self.assertNotIn("gör i ordning", steps)
        self.assertNotIn("ta fram det du behöver", steps)
        nut = recipe.get("nutrition") or {}
        self.assertGreater(int(nut.get("kcal") or 0), 0)
        self.assertEqual(nut.get("label"), "ca-värden")

    def test_kycklingwok_has_kyckling(self) -> None:
        recipe = shopping.build_recipe("Kycklingwok med ris")
        ings = " ".join(str(x).lower() for x in recipe.get("ingredients") or [])
        self.assertIn("kyckling", ings)
        steps = " ".join(str(s).lower() for s in recipe.get("steps") or [])
        self.assertIn("kyckling", steps)

    def test_sallad_med_tonfisk_catalog_recipe(self) -> None:
        recipe = reng.materialize_recipe(
            "Sallad med tonfisk",
            ["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"],
            meal_type="lunch",
            allow_llm=False,
        )
        self.assertTrue(reng.recipe_is_valid(recipe, "Sallad med tonfisk"))
        blob = " ".join(str(x).lower() for x in recipe.get("ingredients") or [])
        self.assertIn("tonfisk", blob)
        self.assertNotIn("torsk", blob)
        steps = " ".join(str(s).lower() for s in recipe.get("steps") or [])
        self.assertIn("tonfisk", steps)

    def test_wrap_catalog_names_tortilla_and_yoghurt(self) -> None:
        recipe = reng.materialize_recipe(
            "Wrap med kyckling",
            meal_type="lunch",
            allow_llm=False,
        )
        self.assertEqual(recipe.get("recipe_source"), "catalog")
        self.assertTrue(reng.recipe_is_valid(recipe, "Wrap med kyckling"))
        steps = " ".join(recipe["steps"]).lower()
        self.assertIn("tortilla", steps)
        self.assertIn("yoghurt", steps)
        self.assertNotIn("2 dl ris", steps)
        ings = " ".join(str(x).lower() for x in recipe["ingredients"])
        self.assertIn("tortilla", ings)
        self.assertIn("yoghurt", ings)

    def test_catalog_entries_all_grounded(self) -> None:
        fails: list[tuple[str, str]] = []
        for key, raw in reng._CATALOG.items():
            finalized = reng._finalize_recipe(dict(raw), source="catalog")
            ok, reason = reng.validate_recipe(finalized, title=raw.get("title", key))
            if not ok:
                fails.append((key, reason))
        self.assertEqual(fails, [])

    def test_ensure_valid_recipe_regenerates_stub(self) -> None:
        stub = {
            "title": "Havregrynsgröt med banan",
            "ingredients": ["Havregrynsgröt med banan"],
            "steps": ["Ta fram det du behöver.", "Gör i ordning och ät."],
        }
        healed = reng.ensure_valid_recipe(
            stub,
            "Havregrynsgröt med banan",
            meal_type="frukost",
            grok_api_key="",
        )
        self.assertTrue(reng.recipe_is_valid(healed, "Havregrynsgröt med banan"))
        self.assertGreaterEqual(len(healed.get("ingredients") or []), 3)


if __name__ == "__main__":
    unittest.main()
