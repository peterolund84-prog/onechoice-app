# -*- coding: utf-8 -*-
"""Home hero — time-aware headline inference and redesigned layout."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo


class HomeHeroTests(unittest.TestCase):
    def test_infer_breakfast_headline_sv(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 21, 8, 30, tzinfo=ZoneInfo("Europe/Stockholm"))
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertEqual(inferred["headline"], "Frukost?")
        self.assertEqual(inferred["domain"], "food")
        self.assertEqual(inferred["meal_type"], "frukost")

    def test_infer_dinner_headline_sv(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 21, 14, 35, tzinfo=ZoneInfo("Europe/Stockholm"))
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertEqual(inferred["headline"], "Middag?")
        self.assertEqual(inferred["meal_type"], "middag")

    def test_infer_evening_headline_en(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 21, 21, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        inferred = app_mod.infer_home_hero(now, language="en")
        self.assertEqual(inferred["headline"], "Evening snack?")
        self.assertEqual(inferred["meal_type"], "kvallsmal")

    def test_weekend_shows_alternate(self) -> None:
        import app as app_mod

        now = datetime(2026, 7, 18, 14, 0, tzinfo=ZoneInfo("Europe/Stockholm"))  # Saturday
        inferred = app_mod.infer_home_hero(now, language="sv")
        self.assertTrue(inferred["weekend_alternate"])
        self.assertEqual(inferred["weekend_headline"], "Helg?")

    def test_home_hero_and_domain_cards_render(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        self.assertFalse(at.exception)
        body = " ".join(str(m.value or "") for m in at.markdown)
        css = body  # css is in first markdown block
        self.assertIn("oc-hero", body)
        self.assertIn("oc-hero-orb", body)
        self.assertIn("oc-domain-grid", body)
        self.assertIn("oc-domain-card", body)
        for needle in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(needle, body, f"missing domain card {needle}")
        self.assertIn("kylen", body.lower())

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
