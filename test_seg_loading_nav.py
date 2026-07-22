# -*- coding: utf-8 -*-
"""Meal segment full labels, time-based decide skeleton, nav opacity."""

from __future__ import annotations

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

_STYLES = Path(__file__).resolve().parent / "styles.css"


def _styles() -> str:
    return _STYLES.read_text(encoding="utf-8")


class MealSegFullLabelTests(unittest.TestCase):
    def test_labels_are_full_words(self) -> None:
        import food_domain as fd

        self.assertEqual(fd.meal_label("frukost", "sv"), "Frukost")
        self.assertEqual(fd.meal_label("lunch", "sv"), "Lunch")
        self.assertEqual(fd.meal_label("middag", "sv"), "Middag")
        self.assertEqual(fd.meal_label("kvallsmal", "sv"), "Kvällsmål")
        self.assertEqual(fd.meal_label("kvallsmal", "en"), "Evening snack")

    def test_meal_seg_css_equal_grid_segments(self) -> None:
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        css = _styles()
        self.assertIn(".st-key-meal_seg", css)
        self.assertIn(".oc-seg", css)
        self.assertIn("flex: 1 1 0 !important", css)
        self.assertIn("height: 32px", css)  # segment button
        self.assertIn("height: 40px", css)  # track
        self.assertIn("padding: 4px", css)
        self.assertIn("font-size: 13px", css)
        self.assertIn("letter-spacing: 0", css)
        self.assertIn("white-space: nowrap", css)
        self.assertIn('key=f"meal_seg_{meal_key}"', src)
        self.assertIn("st.columns([1, 1, 1, 1]", src)
        self.assertNotIn('key="meal_pills"', src)


class DecideSlotTests(unittest.TestCase):
    def test_run_decision_queues_full_width_slot(self) -> None:
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn('page = "deciding"', src)
        self.assertIn("def page_deciding", src)
        self.assertIn('key="decide_slot"', src)
        self.assertIn("_queue_decide_in_slot", src)
        self.assertIn('"_decide_in_slot"', src)
        # Skeleton must not be painted from inside home columns
        self.assertIn('"deciding": page_deciding', src)

    def test_decide_slot_css_is_full_width(self) -> None:
        css = _styles()
        self.assertIn(".st-key-decide_slot", css)
        self.assertIn(".oc-skel-card {\n    width: 100% !important;", css)


class TimeBasedSkeletonTests(unittest.TestCase):
    def test_fast_path_skips_skeleton(self) -> None:
        import app as app_mod

        painted: list[bool] = []

        def fake_paint(*, fridge_mode: bool = False) -> None:
            painted.append(True)

        with mock.patch.object(app_mod, "_render_decide_skeleton", side_effect=fake_paint):
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(lambda: "ok")
                result, shown = app_mod._await_decide_with_skeleton(
                    fut, fridge_mode=False, delay_s=0.4, timeout_s=5
                )
        self.assertEqual(result, "ok")
        self.assertFalse(shown)
        self.assertEqual(painted, [])

    def test_slow_path_shows_skeleton_after_delay(self) -> None:
        import app as app_mod

        painted: list[bool] = []

        def fake_paint(*, fridge_mode: bool = False) -> None:
            painted.append(True)

        def slow() -> str:
            time.sleep(0.55)
            return "slow-ok"

        with mock.patch.object(app_mod, "_render_decide_skeleton", side_effect=fake_paint):
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(slow)
                result, shown = app_mod._await_decide_with_skeleton(
                    fut, fridge_mode=False, delay_s=0.2, timeout_s=5
                )
        self.assertEqual(result, "slow-ok")
        self.assertTrue(shown)
        self.assertEqual(painted, [True])

    def test_immediate_paints_skeleton_without_delay(self) -> None:
        """Replacing an on-screen card must not leave it dimmed under the wait."""
        import app as app_mod

        painted: list[bool] = []

        def fake_paint(*, fridge_mode: bool = False) -> None:
            painted.append(True)

        def slow() -> str:
            time.sleep(0.15)
            return "imm-ok"

        with mock.patch.object(app_mod, "_render_decide_skeleton", side_effect=fake_paint):
            with ThreadPoolExecutor(max_workers=1) as pool:
                fut = pool.submit(slow)
                result, shown = app_mod._await_decide_with_skeleton(
                    fut, fridge_mode=False, delay_s=0.4, timeout_s=5, immediate=True
                )
        self.assertEqual(result, "imm-ok")
        self.assertTrue(shown)
        self.assertEqual(painted, [True])

    def test_css_hides_prior_card_under_skeleton(self) -> None:
        import app as app_mod

        css = _styles()
        src = open(app_mod.__file__, encoding="utf-8").read()
        # Hide prior cards under skeleton — but NEVER on result (leftover
        # .oc-skel-card from st.html would blank the dish image otherwise).
        self.assertIn(
            "body:has(.oc-skel-card):not(:has(.oc-result)):not(:has(.oc-exec-lock))",
            css,
        )
        self.assertIn(
            "body:has([data-oc-deciding]):not(:has(.oc-result)):not(:has(.oc-exec-lock))",
            css,
        )
        self.assertIn("data-oc-deciding", src)
        self.assertIn("_decide_skel_painted", src)

    def test_page_deciding_marks_slot_painted(self) -> None:
        """Cold Bestäm åt mig must not remount decide_slot (DuplicateElementKey → ui_error)."""
        import app as app_mod
        import inspect

        src = inspect.getsource(app_mod.page_deciding)
        self.assertIn("_render_decide_skeleton", src)
        self.assertIn('["_decide_skel_painted"] = True', src)
        # Must not leave painted=False after occupying decide_slot
        self.assertNotIn('["_decide_skel_painted"] = False', src)
        self.assertNotIn("_render_decide_evictor", src)

    def test_css_extracted_and_cached(self) -> None:
        """Static CSS in styles.css; file read cached; emit every rerun."""
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertTrue(_STYLES.is_file())
        self.assertIn("def read_css", src)
        self.assertIn("@st.cache_data", src)
        self.assertIn("def _dynamic_css_block", src)
        # Must NOT skip injection on later reruns (unstyled app)
        self.assertNotIn("_oc_css_injected", src)
        self.assertNotIn("oc-app-css-head", src)
        # Ghost wipe hacks removed after perf pass
        self.assertNotIn("inject_app_runtime", src)
        self.assertNotIn("_oc_pending_nav_runtime_html", src)
        css = _styles()
        self.assertNotIn("html.oc-pending", css)
        self.assertNotIn("#oc-nav-wipe", css)
        self.assertNotIn("Hard kill: result/meal CTAs", css)
        self.assertIn("Kollar vad du åt senast", open(app_mod.__file__, encoding="utf-8").read())
        self.assertIn("oc-status-cycle", css)

    def test_run_decision_always_uses_time_based_await(self) -> None:
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn("_await_decide_with_skeleton", src)
        self.assertIn("DECIDE_SKELETON_DELAY_S = 0.4", src)
        self.assertNotIn("def _decide_uses_skeleton", src)
        # No path-based skip of skeleton for habit meals
        self.assertNotIn('meal in ("frukost", "kvallsmal")', src)


class NavBleedTests(unittest.TestCase):
    def test_nav_glass_is_opaque_enough(self) -> None:
        css = _styles()
        self.assertIn("rgba(250, 250, 247, 0.92)", css)
        self.assertIn("blur(20px)", css)
        self.assertIn("z-index: 10000", css)
        # Must not wipe nav bar background back to transparent
        # (children may be transparent; the bar itself must keep glass)
        nav_block = css.split("/* Glass nav MUST win")[1].split(".st-key-oc_nav_bar [class*")[0]
        self.assertIn("rgba(250, 250, 247, 0.92)", nav_block)
        # The bar rule itself is NOT background: transparent
        bar_only = nav_block.split(".st-key-oc_nav_bar [data-testid")[0]
        self.assertNotIn("background: transparent", bar_only)


if __name__ == "__main__":
    unittest.main()
