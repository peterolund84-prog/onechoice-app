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
        css = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("--oc-bg", css)
        self.assertIn("--oc-accent", css)
        self.assertIn("family=Sora", css)
        self.assertIn("family=Inter", css)
        self.assertIn("oc-hero", css)
        self.assertIn("oc-orb-breathe", css)
        self.assertIn("oc-domain-grid", css)
        self.assertIn("var(--oc-accent)", css)
        self.assertNotIn("5A8BFF", css)
        self.assertNotIn("F4F6F8", css)
        self.assertIn("oc-shop-pick-marker", css)
        self.assertIn("oc-shop-tog-marker", css)
        # Fixed frosted chrome — header + lang/nav overlays
        self.assertIn("oc-header", css)
        self.assertIn("translateX(-50%)", css)
        self.assertIn("position: fixed", css)
        self.assertIn("padding: 76px", css)
        self.assertIn("backdrop-filter", css)
        self.assertIn("st-key-home_hero", css)
        self.assertIn("st-key-oc_lang_bar", css)
        self.assertIn("st-key-oc_nav_bar", css)

    def test_home_structure_and_no_char_counter_early(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Bestäm åt mig" in lab for lab in labels), labels)
        self.assertFalse(any("Bestäm" == lab for lab in labels if lab != "Bestäm åt mig"))
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("kylen", body.lower())
        caps = [str(c.value or "") for c in at.caption]
        self.assertFalse(any("/" in c and c[:1].isdigit() for c in caps), caps)
        self.assertIn("oc-hero-title", body)
        self.assertIn("oc-domain-grid", body)
        self.assertEqual(body.count('class="oc-header"'), 1)
        self.assertNotIn("oc-topbar", body)
        for need in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(need, body)
        self.assertIn("SV", body)
        self.assertIn("EN", body)
        self.assertNotIn("build ", body.lower())
        for c in caps:
            self.assertNotIn("build ", str(c).lower())
        self.assertIn('class="oc-header-wordmark', body.replace(" ", ""))
        self.assertNotIn("free_text", body.lower())
        self.assertNotIn("Eller skriv vad du behöver", body)
        css = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-tagline", css)


if __name__ == "__main__":
    unittest.main()
