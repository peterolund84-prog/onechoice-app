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
        self.assertIn("oc-chip-row", css)
        # Accent fill only on primary CTA (not soft purple theme)
        self.assertIn("var(--oc-accent)", css)
        self.assertNotIn("5A8BFF", css)
        self.assertNotIn("F4F6F8", css)
        # Premium shopping pick card (execute) stays in design system
        self.assertIn("oc-shop-pick-marker", css)
        self.assertIn("oc-shop-tog-marker", css)
        # Locked chrome: sticky brand header + keyed fixed lang/nav
        self.assertIn("oc-topbar", css)
        self.assertIn("position: sticky", css)
        self.assertIn("st-key-oc_lang_bar", css)
        self.assertIn("st-key-oc_nav_bar", css)
        self.assertIn("st-key-oc_lang_pills", css)
        self.assertIn("st-key-oc_nav_pills", css)

    def test_home_structure_and_no_char_counter_early(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Bestäm åt mig" in lab for lab in labels), labels)
        self.assertTrue(any("kylen" in lab.lower() for lab in labels), labels)
        caps = [str(c.value or "") for c in at.caption]
        self.assertFalse(any("/" in c and c[:1].isdigit() for c in caps), caps)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-chip-row", body)
        for need in ("Mat", "Kläder", "Film", "Träning", "Helg"):
            self.assertIn(need, body)
        self.assertIn("SV", body)
        self.assertIn("EN", body)
        self.assertIn("oc-lang-sep", body)
        # Build id must never surface in consumer UI
        self.assertNotIn("build ", body.lower())
        for c in caps:
            self.assertNotIn("build ", str(c).lower())
        # Wordmark is solid (no two-tone <em>)
        self.assertIn('class="oc-logo">OneChoice</', body.replace(" ", ""))
        self.assertIn("oc-tag-dot", body)
        # Tagline has 48px spacing token in CSS
        css = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("margin: 0 0 48px", css)


if __name__ == "__main__":
    unittest.main()
