# -*- coding: utf-8 -*-
"""Home hero — time-aware headline inference and redesigned layout."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Stockholm")


class HomeHeroTests(unittest.TestCase):
    def test_infer_breakfast_headline_sv(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 21, 8, 30, tzinfo=TZ)
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertEqual(inferred["headline"], "Frukost?")
        self.assertEqual(inferred["domain"], "food")
        self.assertEqual(inferred["meal_type"], "frukost")

    def test_infer_dinner_headline_sv(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 21, 14, 35, tzinfo=TZ)
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertEqual(inferred["headline"], "Middag?")
        self.assertEqual(inferred["meal_type"], "middag")

    def test_infer_dinner_at_1448_stockholm(self) -> None:
        """Regression: UTC servers must not show Lunch at 14:48 local."""
        import app as app_mod

        now = datetime(2026, 7, 21, 14, 48, tzinfo=TZ)
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertEqual(inferred["headline"], "Middag?")
        self.assertEqual(inferred["meal_type"], "middag")

    def test_meal_boundary_times(self) -> None:
        import app as app_mod
        import food_domain as fd

        cases = [
            (datetime(2026, 7, 21, 5, 0, tzinfo=TZ), "frukost", "Frukost?"),
            (datetime(2026, 7, 21, 10, 0, tzinfo=TZ), "lunch", "Lunch?"),
            (datetime(2026, 7, 21, 13, 30, tzinfo=TZ), "middag", "Middag?"),
            (datetime(2026, 7, 21, 20, 0, tzinfo=TZ), "kvallsmal", "Kvällsmål?"),
            (datetime(2026, 7, 21, 23, 59, tzinfo=TZ), "kvallsmal", "Kvällsmål?"),
        ]
        for now, meal_key, headline in cases:
            with self.subTest(now=now.isoformat()):
                self.assertEqual(fd.default_meal_type(now=now), meal_key)
                inferred = app_mod.infer_home_hero(now, language="sv")
                self.assertEqual(inferred["headline"], headline)
                self.assertEqual(inferred["meal_type"], meal_key)

    def test_infer_works_without_food_domain_local_now(self) -> None:
        import app as app_mod
        import food_domain as fd

        now = datetime(2026, 7, 21, 14, 48, tzinfo=TZ)
        saved = getattr(fd, "local_now", None)
        if hasattr(fd, "local_now"):
            delattr(fd, "local_now")
        try:
            inferred = app_mod.infer_home_hero(now, language="sv")
            self.assertEqual(inferred["headline"], "Middag?")
        finally:
            if saved is not None:
                fd.local_now = saved  # type: ignore[attr-defined]

    def test_infer_evening_headline_en(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 21, 21, 0, tzinfo=TZ)
        inferred = app_mod.infer_home_hero(now, language="en")
        self.assertEqual(inferred["headline"], "Evening snack?")
        self.assertEqual(inferred["meal_type"], "kvallsmal")

    def test_weekend_shows_alternate(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 18, 14, 0, tzinfo=TZ)  # Saturday
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertTrue(inferred["weekend_alternate"])
        self.assertEqual(inferred["weekend_headline"], "Helg?")

    def test_home_hero_and_domain_cards_render(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        self.assertFalse(at.exception)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-hero", body)
        self.assertIn("oc-hero-orb", body)
        self.assertIn("oc-domain-grid", body)
        self.assertIn("oc-domain-card", body)
        for needle in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(needle, body, f"missing domain card {needle}")
        self.assertIn("kylen", body.lower())
        # Valid inline SVG icons — no broken glyph placeholders
        self.assertGreaterEqual(body.count('xmlns="http://www.w3.org/2000/svg"'), 6)
        self.assertNotIn("▯", body)

    def test_hero_decide_runs_food_decision(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        for b in at.button:
            if b.label and "Bestäm åt mig" in b.label:
                b.click().run()
                break
        else:
            self.fail("home hero decide button not found")
        self.assertFalse(at.exception)
        self.assertIn(
            at.session_state["page"],
            ("result", "clothes_occasion", "ambiguous"),
        )

    def test_domain_card_query_navigates(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.query_params["domain"] = "workout"
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "result")


if __name__ == "__main__":
    unittest.main()
