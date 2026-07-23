# -*- coding: utf-8 -*-
"""Home premium-minimal design — structure intact, styling tokens present."""

from __future__ import annotations

import unittest


class HomeDesignTests(unittest.TestCase):
    def test_css_tokens_and_fonts(self) -> None:
        import app as app_mod

        self.assertEqual(app_mod.BG, "#FAFAF7")
        self.assertEqual(app_mod.INK, "#1A1A1A")
        self.assertEqual(app_mod.MUTED, "#6B6B66")
        self.assertEqual(app_mod.BORDER, "#E5E5E0")
        self.assertEqual(app_mod.ACCENT, "#3B3BC4")

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        dyn = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("--oc-bg", dyn)
        self.assertIn("--oc-accent", dyn)
        self.assertIn("family=Sora", css)
        self.assertIn("family=Inter", css)
        self.assertIn("oc-hero", css)
        self.assertIn("oc-orb-breathe", css)
        self.assertIn("st-key-home_domain_", css)
        self.assertIn("flex-direction: row", css)
        self.assertIn("min-height: 52px", css)
        self.assertIn("width: 100%", css)
        self.assertIn("clamp(40px, 11vw, 56px)", css)
        self.assertIn("oc-hero-sub", css)
        self.assertIn("translateX(-50%)", css)
        self.assertIn("translateY(-42%)", css)
        self.assertIn("st-key-home_domains", css)
        self.assertIn("st-key-home_free_disclose", css)
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
        # Lang bar CSS kept (toggle can re-enable); atmosphere gradient present
        self.assertIn("st-key-oc_lang_bar", css)
        self.assertIn("st-key-oc_nav_bar", css)
        self.assertIn("linear-gradient(180deg, #F6F5F1", css)
        self.assertIn("rgba(255, 255, 255, 0.42)", css)
        self.assertFalse(app_mod.SHOW_LANG_TOGGLE)

    def test_home_structure_and_no_char_counter_early(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Bestäm åt mig" in lab for lab in labels), labels)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Fota kylen", labels)
        self.assertNotIn("Vad finns i kylen?", body)
        caps = [str(c.value or "") for c in at.caption]
        self.assertFalse(any("/" in c and c[:1].isdigit() for c in caps), caps)
        self.assertIn("oc-hero-title", body)
        self.assertNotIn("<h1", body.lower())
        self.assertIn("oc-section-label", body)
        self.assertEqual(body.count('class="oc-header"'), 1)
        self.assertNotIn("oc-topbar", body)
        for need in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(need, labels, labels)
        self.assertIn("Eller välj själv", body)
        self.assertIn("Något annat?", " ".join(labels))
        self.assertEqual(len(list(getattr(at, "text_input", []) or [])), 0)
        # Expanded placeholder is Swedish product-premise copy (not English chrome)
        import app as app_mod

        self.assertEqual(
            app_mod.I18N["sv"]["home_free_placeholder"],
            "Vad ska du bestämma?",
        )
        self.assertEqual(
            app_mod.I18N["en"]["home_free_placeholder"],
            "What do you need to decide?",
        )
        # Swedish-first: SV/EN control hidden (i18n kept, toggle off)
        self.assertNotIn(">SV<", body)
        self.assertNotIn(">EN<", body)
        self.assertNotIn('key="oc_lang_bar"', body)
        self.assertEqual(at.session_state["language"], "sv")
        self.assertIn("oc-hero-sub", body)
        self.assertIn("Ett tryck — jag tar beslutet.", body)
        self.assertNotIn("build ", body.lower())
        self.assertNotIn("home_free_input", body.lower())
        self.assertNotIn("Vad behöver du bestämma?", body)
        for c in caps:
            self.assertNotIn("build ", str(c).lower())
        self.assertIn('class="oc-header-wordmark', body.replace(" ", ""))
        css = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-tagline", css)


if __name__ == "__main__":
    unittest.main()
