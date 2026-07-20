# -*- coding: utf-8 -*-
"""Shopping list completeness — protein never assumed at home."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import feasibility
import pipeline
import shopping
import shopping_compat


class ShoppingTests(unittest.TestCase):
    def test_shopping_from_recipe_structured(self) -> None:
        recipe = {
            "title": "Sallad med tonfisk",
            "ingredients_structured": [
                {"name": "tonfisk", "category": "to_buy"},
                {"name": "sallad", "category": "to_buy"},
                {"name": "olja", "category": "assumed_home"},
                {"name": "salt", "category": "assumed_home"},
            ],
            "steps": ["a", "b", "c"],
        }
        shop = shopping.shopping_from_recipe(recipe, suggestion="Sallad med tonfisk")
        self.assertIsNotNone(shop)
        assert shop is not None
        flat = " ".join(
            shopping._strip_hint(i)
            for section in shop["to_buy"].values()
            for i in section
        ).lower()
        self.assertIn("tonfisk", flat)
        self.assertIn("sallad", flat)
        self.assertIn("olja", " ".join(shop["assumed_at_home"]))

    def test_build_meal_bundle_recipe_and_shop(self) -> None:
        recipe, shop = shopping.build_meal_bundle(
            "Sallad med tonfisk",
            meta={
                "meal_type": "lunch",
                "ingredients": ["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"],
            },
            meal_type="lunch",
            include_shopping=True,
        )
        self.assertIsNotNone(recipe)
        self.assertIsNotNone(shop)
        assert recipe is not None
        self.assertGreaterEqual(len(recipe.get("steps") or []), 3)
        assert shop is not None
        self.assertTrue(shop.get("to_buy"))

    def test_shopping_compat_fallback_without_build_meal_bundle(self) -> None:
        saved = getattr(shopping, "build_meal_bundle", None)
        try:
            if hasattr(shopping, "build_meal_bundle"):
                delattr(shopping, "build_meal_bundle")
            recipe, shop = shopping_compat.resolve_meal_bundle(
                "Sallad med tonfisk",
                meta={
                    "meal_type": "lunch",
                    "ingredients": ["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"],
                },
                meal_type="lunch",
                include_shopping=True,
            )
            self.assertIsNotNone(recipe)
            self.assertIsNotNone(shop)
            assert recipe is not None
            self.assertGreaterEqual(len(recipe.get("steps") or []), 3)
            assert shop is not None
            self.assertTrue(shop.get("to_buy"))
        finally:
            if saved is not None:
                shopping.build_meal_bundle = saved  # type: ignore[attr-defined]

    def test_kycklingwok_puts_chicken_on_to_buy(self) -> None:
        payload = shopping.build_shopping("Kycklingwok med ris")
        self.assertIsNotNone(payload)
        assert payload is not None
        flat = [
            shopping._strip_hint(i)
            for section in payload["to_buy"].values()
            for i in section
        ]
        self.assertTrue(any("kyckling" in x for x in flat))
        assumed = " ".join(payload["assumed_at_home"])
        self.assertNotIn("kyckling", assumed)
        # Fresh paprika must not be treated as dried spice staple
        self.assertTrue(any("paprika" in x for x in flat))
        self.assertFalse(any("paprika" in a for a in payload["assumed_at_home"]))
        self.assertTrue(shopping.shopping_valid(payload, "Kycklingwok med ris"))

    def test_assumed_only_true_staples(self) -> None:
        payload = shopping.build_shopping("Kycklingwok med ris")
        assert payload is not None
        for item in payload["assumed_at_home"]:
            self.assertTrue(
                shopping._is_staple(item),
                f"{item} should not be assumed at home",
            )
        for banned in ("ris", "sojasås", "kyckling", "lök", "broccoli"):
            self.assertFalse(
                any(banned in a for a in payload["assumed_at_home"]),
                f"{banned} must be on buy list, not assumed",
            )

    def test_every_ingredient_in_exactly_one_list(self) -> None:
        payload = shopping.build_shopping("Klassisk burgare hemma")
        assert payload is not None
        buy = {
            shopping._strip_hint(i)
            for section in payload["to_buy"].values()
            for i in section
        }
        assumed = {shopping._norm_item(a) for a in payload["assumed_at_home"]}
        self.assertFalse(buy & assumed)
        for ing in payload["ingredients"]:
            n = shopping._norm_item(ing)
            self.assertTrue(
                n in buy or n in assumed or shopping._strip_hint(ing) in buy,
                f"missing from both lists: {ing}",
            )

    def test_feasibility_attaches_structured_shopping(self) -> None:
        profile = feasibility.parse_profile(
            {"id": "u", "profile_json": {}}, {"is_weekend": False}
        )
        cand = {
            "suggestion": "Kycklingwok med ris",
            "justification": "Vardagsfavorit.",
            "meta": {"active_minutes": 25},
        }
        r = feasibility.feasibility_check(cand, domain="food", profile=profile)
        self.assertTrue(r.ok)
        self.assertIn("shopping", r.execution)
        shop = r.execution["shopping"]
        flat = " ".join(
            i for section in shop["to_buy"].values() for i in section
        )
        self.assertIn("kyckling", flat)

    def test_pipeline_food_context_has_chicken_on_list(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        try:
            path = str(Path(tmp.name) / "t.db")
            db.init_db(path)
            user = db.ensure_user(language="sv", path=path)
            # Force the chicken dish by seeding recent with everything else
            recent_blockers = [
                "Krämig tomatsås-pasta",
                "Etiopisk-inspirerad linsgryta",
                "Proteinomelett med grönt",
                "Klassisk burgare hemma",
                "Proteinomelett med frukt",
            ]
            for s in recent_blockers:
                db.create_decision(
                    user_id=user["id"],
                    domain="food",
                    question="Vad ska jag äta?",
                    suggestion=s,
                    justification="x",
                    status="accepted",
                    path=path,
                )
            # Still may get chicken or morning omelette — assert whatever food
            # result has shopping with protein when dish names protein.
            r = pipeline.decide(
                user["id"],
                "Vad ska jag äta?",
                domain_hint="food",
                language="sv",
                db_path=path,
                context_extra={"meal_type": "middag"},
            )
            self.assertTrue(r.ok)
            shop = (r.context or {}).get("shopping")
            self.assertIsInstance(shop, dict)
            assert isinstance(shop, dict)
            sug = (r.suggestion or "").lower()
            if "kyckling" in sug:
                flat = " ".join(
                    i for section in (shop.get("to_buy") or {}).values() for i in section
                )
                self.assertIn("kyckling", flat)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
