# -*- coding: utf-8 -*-
"""Home premium mockup design — exact face+hit chrome."""

from __future__ import annotations

import unittest


class HomeDesignTests(unittest.TestCase):
    def test_css_tokens_and_fonts(self) -> None:
        import app as app_mod

        self.assertEqual(app_mod.BG, "#F7F6FC")
        self.assertEqual(app_mod.INK, "#1A1A1A")
        self.assertEqual(app_mod.MUTED, "#6B6B66")
        self.assertEqual(app_mod.BORDER, "#E8E6F0")
        self.assertEqual(app_mod.ACCENT, "#3B3BC4")
        self.assertEqual(app_mod.ACCENT_SOFT, "#6B5CE7")

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        dyn = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("--oc-bg", dyn)
        self.assertIn("--oc-accent", dyn)
        self.assertIn("--oc-cta-grad", dyn)
        self.assertIn("family=Fraunces", css)
        self.assertIn("family=Inter", css)
        self.assertIn("oc-hero", css)
        self.assertIn("oc-orb-breathe", css)
        self.assertIn("oc-domain-face", css)
        self.assertIn("oc-cta-face", css)
        self.assertIn("oc-tip-face", css)
        self.assertIn("oc-domain-sub", css)
        self.assertIn("min-height: 124px", css)
        self.assertIn("border-radius: 24px", css)
        self.assertIn("st-key-home_domains", css)
        self.assertIn("st-key-home_tip_banner", css)
        self.assertIn("st-key-home_free_form", css)
        self.assertIn("var(--oc-accent)", css)
        self.assertNotIn("5A8BFF", css)
        self.assertNotIn("F4F6F8", css)
        self.assertIn("oc-shop-pick-marker", css)
        self.assertIn("oc-shop-tog-marker", css)
        self.assertIn("oc-header", css)
        self.assertIn("position: fixed", css)
        self.assertIn("52px + env(safe-area-inset-top) + 40px", css)
        self.assertIn("backdrop-filter", css)
        self.assertIn("st-key-home_hero", css)
        self.assertIn("st-key-oc_lang_bar", css)
        self.assertIn("st-key-oc_nav_bar", css)
        self.assertIn("linear-gradient(180deg, #F7F6FC", css)
        self.assertIn("oc-logo-spark", css)
        self.assertFalse(app_mod.SHOW_LANG_TOGGLE)

    def test_home_structure_and_no_char_counter_early(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Bestäm åt mig" in lab for lab in labels), labels)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("Vad finns i kylen?", body)
        caps = [str(c.value or "") for c in at.caption]
        self.assertFalse(any("/" in c and c[:1].isdigit() for c in caps), caps)
        self.assertIn("oc-hero-title", body)
        self.assertIn("oc-domain-face", body)
        self.assertIn("oc-cta-face", body)
        self.assertIn("oc-tip-face", body)
        self.assertIn("oc-domain-sub", body)
        self.assertNotIn("<h1", body.lower())
        self.assertIn("oc-section-label", body)
        self.assertEqual(body.count('class="oc-header"'), 1)
        self.assertNotIn("oc-topbar", body)
        for need in ("Mat", "Kläder", "Film", "Träning", "Resor", "Presenter"):
            self.assertTrue(any(need in lab for lab in labels), labels)
            self.assertIn(need, body)
        self.assertIn("Vad vill du bestämma?", body)
        self.assertIn("Frukost, lunch, middag", body)
        self.assertIn("Tipsa oss", body)
        self.assertEqual(len(list(getattr(at, "text_input", []) or [])), 0)
        import app as app_mod

        self.assertEqual(
            app_mod.I18N["sv"]["home_free_placeholder"],
            "Vad ska du bestämma?",
        )
        self.assertNotIn(">SV<", body)
        self.assertNotIn(">EN<", body)
        self.assertEqual(at.session_state["language"], "sv")
        self.assertIn("oc-hero-sub", body)
        self.assertIn("Vad ska vi bestämma idag?", body)
        self.assertIn("Ett tryck. Jag tar beslutet.", body)
        self.assertIn("Jag tar hand om allt", body)
        self.assertNotIn("build ", body.lower())
        self.assertNotIn("Vad behöver du bestämma?", body)
        self.assertIn('class="oc-header-wordmark', body.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
