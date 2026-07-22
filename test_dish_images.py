# -*- coding: utf-8 -*-
"""Deterministic dish image resolver + decide skeleton CSS."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock


class DishImageResolverTests(unittest.TestCase):
    def test_carbonara_is_cream_pasta_not_tomato(self) -> None:
        import dish_images as dimg

        path = dimg.resolve_dish_image("Spaghetti carbonara")
        self.assertIsNotNone(path)
        self.assertEqual(Path(path).name, "pasta_gradde.jpg")
        self.assertTrue(Path(path).is_file())
        # Must not be the tomato penne photo
        self.assertNotEqual(Path(path).name, "pasta.jpg")

    def test_tacos_and_unknown(self) -> None:
        import dish_images as dimg

        path = dimg.resolve_dish_image("Tacos med kryddig färs")
        self.assertEqual(Path(path).name, "tacos.jpg")
        self.assertIsNone(dimg.resolve_dish_image("Xylophone nebula special"))
        self.assertIsNone(dimg.resolve_dish_image("Lunch nära dig"))

    def test_pesto_and_meatballs(self) -> None:
        import dish_images as dimg

        self.assertEqual(
            Path(dimg.resolve_dish_image("Pasta pesto")).name, "pasta_pesto.jpg"
        )
        self.assertEqual(
            Path(dimg.resolve_dish_image("Köttbullar med gräddsås")).name,
            "kottbullar.jpg",
        )

    def test_category_hint_only_when_no_keyword(self) -> None:
        import dish_images as dimg

        # Keyword wins over wrong hint
        self.assertEqual(
            Path(dimg.resolve_dish_image("Spaghetti carbonara", "pasta")).name,
            "pasta_gradde.jpg",
        )
        # No keyword → hint file if it exists
        path = dimg.resolve_dish_image("Hemmagjord vardagsrätt", "wok")
        self.assertEqual(Path(path).name, "wok.jpg")

    def test_local_packs_all_resolve(self) -> None:
        import dish_images as dimg

        dimg.assert_local_packs_resolve()

    def test_no_generic_jpg(self) -> None:
        base = Path(__file__).resolve().parent / "assets" / "dishes"
        self.assertFalse((base / "generic.jpg").is_file())

    def test_mappings_point_to_existing_files(self) -> None:
        import dish_images as dimg

        missing = []
        for cue, fname in dimg.KEYWORD_FILES.items():
            if not (dimg.DISHES_DIR / fname).is_file():
                missing.append(f"{cue}->{fname}")
        for cue, fname in dimg.CATEGORY_FILES.items():
            if not (dimg.DISHES_DIR / fname).is_file():
                missing.append(f"cat:{cue}->{fname}")
        self.assertEqual(missing, [])


class DecideSkeletonTests(unittest.TestCase):
    def test_skeleton_css_and_helpers(self) -> None:
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn("oc-skel-shimmer", src)
        self.assertIn("oc-skel-status", src)
        self.assertIn("oc-card-arrive", src)
        self.assertIn("_render_decide_skeleton", src)
        self.assertIn("_await_decide_with_skeleton", src)
        self.assertIn("_decide_status_line", src)
        self.assertIn("DECIDE_TIMEOUT_S = 20.0", src)
        self.assertIn("DECIDE_SKELETON_DELAY_S = 0.4", src)
        # Quiet single line — no cycling copy about history/time/weather
        self.assertNotIn("oc-status-cycle", src)
        self.assertNotIn('"decide_status_1": "Kollar', src)
        self.assertNotIn("Checking what you ate last", src)
        self.assertNotIn("Matching time and weather", src)
        self.assertNotIn("Putting the recipe together", src)
        self.assertIn('"deciding": "Bestämmer…"', src)
        self.assertEqual(app_mod._decide_status_line(), "Bestämmer…")

    def test_habit_meals_also_use_time_based_skeleton(self) -> None:
        import app as app_mod

        # Path-based skip removed — every domain uses the 400ms await helper.
        self.assertTrue(hasattr(app_mod, "_await_decide_with_skeleton"))
        self.assertFalse(hasattr(app_mod, "_decide_uses_skeleton"))
        self.assertEqual(app_mod.DECIDE_SKELETON_DELAY_S, 0.4)

    def test_meal_seg_font_full_labels(self) -> None:
        import app as app_mod
        import food_domain as fd

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn("font-size: 13px", src)
        self.assertIn("letter-spacing: 0", src)
        self.assertEqual(fd.meal_label("kvallsmal", "sv"), "Kvällsmål")
        labels = [fd.meal_label(k, "sv") for k in fd.MEAL_ORDER]
        self.assertEqual(labels, ["Frukost", "Lunch", "Middag", "Kvällsmål"])

    def test_food_card_uses_resolver_not_generic(self) -> None:
        import app as app_mod

        html = app_mod._render_food_card_html(
            language="sv",
            suggestion="Spaghetti carbonara",
            justification="Test",
            ctx={"dish_category": "pasta", "meal_type": "middag"},
        )
        self.assertIn("oc-food-img", html)
        self.assertIn("data:image/jpeg;base64,", html)
        self.assertNotIn("oc-food-img-ph", html)

        html2 = app_mod._render_food_card_html(
            language="sv",
            suggestion="Xylophone nebula special",
            justification="Test",
            ctx={},
        )
        self.assertIn("oc-food-img-ph", html2)
        self.assertIn("oc-food-ph-circle", html2)


if __name__ == "__main__":
    unittest.main()
