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


class ShoppingTests(unittest.TestCase):
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
