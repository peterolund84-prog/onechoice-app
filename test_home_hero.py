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
        self.assertIn('class="oc-cta"', body.replace(" ", ""))
        self.assertIn("oc-domain-grid", body)
        self.assertIn("oc-domain-card", body)
        for needle in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(needle, body, f"missing domain card {needle}")
        self.assertIn("Fota kylen", body)
        self.assertNotIn("Vad finns i kylen?", body)
        # Valid inline SVG icons — no broken glyph placeholders
        self.assertGreaterEqual(body.count('xmlns="http://www.w3.org/2000/svg"'), 6)
        self.assertNotIn("▯", body)
        self.assertEqual(body.count('class="oc-header"'), 1)
        self.assertNotIn("oc-topbar", body)

    def test_hero_decide_runs_food_decision(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-cta", body)
        at.query_params["domain"] = "food"
        at.query_params["auto"] = "1"
        at.run()
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

    def test_all_six_domain_cards_navigate(self) -> None:
        from streamlit.testing.v1 import AppTest

        cases = [
            ("food", "result"),
            ("clothes", "clothes_occasion"),
            ("movie", "result"),
            ("workout", "result"),
            ("weekend", "result"),
        ]
        for domain, expected_page in cases:
            with self.subTest(domain=domain):
                at = AppTest.from_file("app.py", default_timeout=60)
                at.run()
                at.query_params["domain"] = domain
                at.run()
                self.assertFalse(at.exception)
                self.assertEqual(at.session_state["page"], expected_page)

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.query_params["fridge"] = "1"
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "fridge")

    def test_home_has_free_text_placeholder_not_label(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        placeholders = [
            str(getattr(inp, "placeholder", "") or "")
            for inp in getattr(at, "text_input", [])
        ]
        self.assertTrue(
            any("Eller skriv" in p for p in placeholders),
            placeholders,
        )
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("home_free_input", body.lower())
        self.assertNotIn("Vad behöver du bestämma?", body)
        labels = [str(getattr(inp, "label", "") or "") for inp in getattr(at, "text_input", [])]
        self.assertFalse(any("home_free_input" in lab.lower() for lab in labels), labels)
        self.assertFalse(any("Vad behöver du bestämma?" in lab for lab in labels), labels)

    def test_free_text_form_submits_question(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        self.assertTrue(at.text_input, "home free-text input missing")
        at.text_input[0].set_value("Vad ska jag laga till middag?").run()
        submits = getattr(at, "form_submit_button", None) or []
        if not submits:
            for b in at.button:
                if b.label and "Bestäm" in b.label:
                    b.click().run()
                    break
            else:
                self.fail("free-text submit control not found")
        else:
            submits[0].click().run()
        self.assertFalse(at.exception)
        self.assertIn(
            at.session_state["page"],
            ("result", "ambiguous", "clothes_occasion"),
        )


    def test_home_centerline_css_rules(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        css = " ".join(str(m.value or "") for m in at.markdown)
        for needle in (
            "left: 50%",
            "translateX(-50%)",
            "text-align: center",
            "oc-hero-title",
            "oc-cta",
            "margin: 0 0 28px",
            "oc-section-label",
            "oc-header-wordmark",
        ):
            self.assertIn(needle, css, needle)

    def test_home_domain_card_labels_fit_compact_row(self) -> None:
        import app as app_mod

        labels = [
            app_mod.I18N["sv"]["domains"][d]
            for d in ("food", "clothes", "movie", "workout", "weekend")
        ]
        labels.append(app_mod.I18N["sv"]["home_fridge_card"])
        # ~170px card @ 390px viewport — keep labels short (no font shrink)
        for label in labels:
            self.assertLessEqual(len(label), 12, label)


if __name__ == "__main__":
    unittest.main()
