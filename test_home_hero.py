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
        self.assertIn("oc-hero-sub", body)
        self.assertIn('<divclass="oc-hero-title"', body.replace(" ", "").lower())
        self.assertNotIn("<h1", body.lower())
        self.assertIn("oc-section-label", body)
        labels = [b.label or "" for b in at.button]
        for needle in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(needle, labels, f"missing domain button {needle}")
        self.assertIn("Fota kylen", labels)
        self.assertIn("Bestäm åt mig", labels)
        self.assertNotIn("Vad finns i kylen?", body)
        # Domain card icons live in styles.css data-URIs
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        self.assertIn("st-key-home_domain_", css)
        self.assertGreaterEqual(css.count("data:image/svg+xml"), 6)
        # Lucide motifs (muted) — soup / coat-hanger / clapperboard / palm / fridge
        self.assertIn("%236B6B66", css)  # muted stroke
        self.assertIn("M12%2021a9%209%200%200%200%209-9H3", css)  # soup bowl
        self.assertIn("M5%206a4%204%200%200%201%204-4h6", css)  # refrigerator
        self.assertNotIn("▯", body)
        self.assertEqual(body.count('class="oc-header"'), 1)
        self.assertNotIn("oc-topbar", body)
        self.assertNotIn('href="?domain=', body)

    def test_hero_decide_runs_food_decision(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        hero = next(b for b in at.button if b.label == "Bestäm åt mig")
        hero.click().run()
        self.assertFalse(at.exception)
        self.assertIn(
            at.session_state["page"],
            ("result", "clothes_occasion", "ambiguous"),
        )

    def test_domain_card_button_navigates(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        workout = next(b for b in at.button if b.label == "Träning")
        workout.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "result")

    def test_all_six_domain_cards_navigate(self) -> None:
        from streamlit.testing.v1 import AppTest

        cases = [
            ("Mat", "result"),
            ("Kläder", "clothes_occasion"),
            ("Film", "result"),
            ("Träning", "result"),
            ("Helg", "result"),
        ]
        for label, expected_page in cases:
            with self.subTest(label=label):
                at = AppTest.from_file("app.py", default_timeout=60)
                at.run()
                btn = next(b for b in at.button if b.label == label)
                btn.click().run()
                self.assertFalse(at.exception)
                self.assertEqual(at.session_state["page"], expected_page)

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        fridge = next(b for b in at.button if b.label == "Fota kylen")
        fridge.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "fridge")

    def test_home_free_text_disclosed_by_default(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        labels = [b.label or "" for b in at.button]
        disclose = next(
            b for b in at.button if getattr(b, "key", None) == "home_free_disclose_btn"
        )
        self.assertEqual(disclose.label, "Något annat?")
        self.assertIn("Något annat?", labels)
        # Collapsed: no free-text input in the tree
        self.assertEqual(len(list(getattr(at, "text_input", []) or [])), 0)
        self.assertFalse(any(lab == "Bestäm" for lab in labels), labels)

    def test_home_has_free_text_placeholder_not_label(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        disclose = next(
            b for b in at.button if getattr(b, "key", None) == "home_free_disclose_btn"
        )
        disclose.click().run()
        placeholders = [
            str(getattr(inp, "placeholder", "") or "")
            for inp in getattr(at, "text_input", [])
        ]
        self.assertTrue(
            any("Vad ska du bestämma?" in p for p in placeholders),
            placeholders,
        )
        self.assertFalse(
            any("Skriv ditt beslut" in p for p in placeholders),
            placeholders,
        )
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("home_free_input", body.lower())
        self.assertNotIn("Vad behöver du bestämma?", body)
        labels = [str(getattr(inp, "label", "") or "") for inp in getattr(at, "text_input", [])]
        self.assertFalse(any("home_free_input" in lab.lower() for lab in labels), labels)
        self.assertFalse(any("Vad behöver du bestämma?" in lab for lab in labels), labels)

    def test_free_text_disclose_toggles_and_submits(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        self.assertEqual(len(list(at.text_input)), 0)
        disclose = next(
            b for b in at.button if getattr(b, "key", None) == "home_free_disclose_btn"
        )
        disclose.click().run()
        self.assertTrue(bool(at.session_state["home_free_open"]))
        self.assertTrue(at.text_input, "expanded free-text input missing")
        submit_btns = [b for b in at.button if b.label == "Bestäm åt mig"]
        self.assertTrue(submit_btns, [b.label for b in at.button])
        # Hero CTA and free-text submit share the same label
        decide_labels = [b.label for b in at.button if b.label == "Bestäm åt mig"]
        self.assertGreaterEqual(len(decide_labels), 2, decide_labels)
        at.text_input[0].set_value("Vad ska jag laga till middag?").run()
        submit_btns[0].click().run()
        self.assertFalse(at.exception)
        self.assertIn(
            at.session_state["page"],
            ("result", "ambiguous", "clothes_occasion"),
        )

    def test_free_text_form_submit_button_click(self) -> None:
        """Button path (not only Enter) routes the question after disclose."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        next(
            b for b in at.button if getattr(b, "key", None) == "home_free_disclose_btn"
        ).click().run()
        at.text_input[0].set_value("Film ikväll").run()
        submit = next(b for b in at.button if b.label == "Bestäm åt mig")
        submit.click().run()
        self.assertFalse(at.exception)
        self.assertIn(at.session_state["page"], ("result", "ambiguous", "clothes_occasion"))

    def test_free_text_disclose_collapses_on_second_tap(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        disclose = next(
            b for b in at.button if getattr(b, "key", None) == "home_free_disclose_btn"
        )
        disclose.click().run()
        self.assertGreater(len(list(at.text_input)), 0)
        disclose = next(
            b for b in at.button if getattr(b, "key", None) == "home_free_disclose_btn"
        )
        disclose.click().run()
        try:
            open_flag = bool(at.session_state["home_free_open"])
        except Exception:
            open_flag = False
        self.assertFalse(open_flag)
        self.assertEqual(len(list(at.text_input)), 0)


    def test_home_centerline_css_rules(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        body = " ".join(str(m.value or "") for m in at.markdown)
        for needle in (
            "left: 50%",
            "translateX(-50%)",
            "text-align: center",
            "oc-hero-title",
            "oc-hero-sub",
            "oc-cta",
            "st-key-home_hero div.stButton",
            "margin: 0 0 28px",
            "margin: 0 0 48px",
            "st-key-home_domain_",
            "margin: 4px 0 20px",
            "min-height: 48px",
            "border-radius: 999px",
            "oc-section-label",
            "oc-header-wordmark",
            "st-key-home_free_disclose",
            "linear-gradient(180deg, #F7F4EC",
        ):
            self.assertIn(needle, css, needle)
        # Stacked free-text CTA — no side-by-side column layout
        self.assertNotIn("min-width: 72%", css)
        self.assertIn('role="heading"', body)

    def test_domain_cards_use_session_safe_buttons(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn('class="oc-domain-card"', body)
        self.assertNotIn('href="?domain=', body)
        labels = [b.label or "" for b in at.button]
        domain_labels = [
            "Mat",
            "Kläder",
            "Film",
            "Träning",
            "Helg",
            "Fota kylen",
        ]
        for lab in domain_labels:
            self.assertIn(lab, labels, labels)

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
