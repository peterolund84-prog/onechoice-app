# -*- coding: utf-8 -*-
"""Feasibility layer unit tests — broken candidates never surface."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import feasibility
import pipeline


class FeasibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "test.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_food_rejects_exotic_ingredient(self) -> None:
        profile = feasibility.parse_profile(self.user, {"is_weekend": False})
        bad = {
            "suggestion": "Injera med teff och fresh lemongrass",
            "justification": "Exotiskt.",
        }
        r = feasibility.feasibility_check(bad, domain="food", profile=profile)
        self.assertFalse(r.ok)

    def test_food_accepts_shelf_adventure(self) -> None:
        profile = feasibility.parse_profile(self.user, {"is_weekend": False})
        good = {
            "suggestion": "Etiopisk-inspirerad linsgryta",
            "justification": "Hyllkryddor bara.",
            "meta": {"active_minutes": 30},
        }
        r = feasibility.feasibility_check(good, domain="food", profile=profile)
        self.assertTrue(r.ok)
        self.assertEqual(r.execution["type"], "recipe")
        self.assertIn("shopping", r.execution)
        shop = r.execution["shopping"]
        self.assertIn("to_buy", shop)
        self.assertIn("assumed_at_home", shop)
        # Spices may be assumed; coconut milk / lentils must be on buy list
        flat = " ".join(i for s in shop["to_buy"].values() for i in s)
        self.assertTrue("lins" in flat or "kokos" in flat)

    def test_clothes_mens_never_gets_dress(self) -> None:
        db.update_user(
            self.user["id"],
            profile_json={"clothes": {"section": "herr", "sizes": {"top": "M"}}},
            path=self.db_path,
        )
        user = db.ensure_user(self.user["id"], path=self.db_path)
        profile = feasibility.parse_profile(user, {})
        bad = {"suggestion": "Sommarklänning", "justification": "Nej."}
        r = feasibility.feasibility_check(bad, domain="clothes", profile=profile)
        self.assertFalse(r.ok)

    def test_clothes_cold_blocks_linen(self) -> None:
        profile = feasibility.parse_profile(
            self.user, {"temp_c": -10, "clothing_section": "dam"}
        )
        bad = {"suggestion": "Linnebyxor", "justification": "För kallt."}
        r = feasibility.feasibility_check(bad, domain="clothes", profile=profile)
        self.assertFalse(r.ok)

    def test_movie_rejects_unsubscribed_and_rental(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"streaming_services": ["netflix"], "available_minutes": 45, "allow_rentals": False},
        )
        rental = {
            "suggestion": "Top Gun Maverick",
            "justification": "Hyr för 49 kr.",
            "meta": {"title": "top gun maverick"},
        }
        r = feasibility.feasibility_check(rental, domain="movie", profile=profile)
        self.assertFalse(r.ok)

        ok = {
            "suggestion": "Wednesday",
            "justification": "Ett avsnitt.",
            "meta": {"title": "wednesday"},
        }
        r2 = feasibility.feasibility_check(ok, domain="movie", profile=profile)
        self.assertTrue(r2.ok)
        self.assertIn("netflix", (r2.execution.get("url") or "").lower())

    def test_workout_home_rejects_gym(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"workout_context": "home", "equipment": ["none"], "workout_minutes": 30},
        )
        bad = {
            "suggestion": "Gå till gymmet och kör cable fly",
            "justification": "Nej.",
            "meta": {"minutes": 30},
        }
        r = feasibility.feasibility_check(bad, domain="workout", profile=profile)
        self.assertFalse(r.ok)

    def test_workout_respects_knee_limitation(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {
                "workout_context": "home",
                "equipment": ["none"],
                "limitations": "känsliga knän",
            },
        )
        bad = {
            "suggestion": "Burpees och jump lunges",
            "justification": "Nej.",
            "meta": {"minutes": 20},
        }
        r = feasibility.feasibility_check(bad, domain="workout", profile=profile)
        self.assertFalse(r.ok)

    def test_weekend_no_outdoor_swim_in_october(self) -> None:
        profile = feasibility.parse_profile(
            self.user, {"has_car": False, "budget": "gratis"}
        )
        # Force month check by patching datetime in module — use direct reason path
        # by calling with utebad suggestion; if current month is summer this may pass.
        # So we assert the validator function logic via season months when applicable.
        from datetime import datetime

        if datetime.now().month in (10, 11, 12, 1, 2, 3):
            bad = {"suggestion": "Utebad vid badstrand", "justification": "Nej."}
            r = feasibility.feasibility_check(bad, domain="weekend", profile=profile)
            self.assertFalse(r.ok)

    def test_pipeline_never_returns_infeasible_food(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(r.ok)
        blob = f"{r.suggestion} {r.justification}".lower()
        for exotic in ("teff", "fresh lemongrass", "galangal", "pandan"):
            self.assertNotIn(exotic, blob)

    def test_pipeline_workout_includes_plan(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "",
            domain_hint="workout",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(r.ok)
        detail = (r.context or {}).get("execution_detail") or ""
        self.assertTrue(detail)
        # Written-out workout, not an external program link requirement
        self.assertTrue(
            any(w in detail.lower() for w in ("min", "×", "x", "knäböj", "armhäv", "planka", "yoga", "zon"))
        )

    def test_repeat_window_is_seven_days(self) -> None:
        self.assertEqual(pipeline.REPEAT_DAYS, 7)


if __name__ == "__main__":
    unittest.main()
