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
