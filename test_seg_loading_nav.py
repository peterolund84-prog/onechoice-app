# -*- coding: utf-8 -*-
"""Meal segment full labels, time-based decide skeleton, nav opacity."""

from __future__ import annotations

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest import mock


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
        self.assertIn(".st-key-meal_seg", src)
        self.assertIn(".oc-seg", src)
        self.assertIn("flex: 1 1 0 !important", src)
        self.assertIn("height: 32px", src)  # segment button
        self.assertIn("height: 40px", src)  # track
        self.assertIn("padding: 4px", src)
        self.assertIn("font-size: 13px", src)
        self.assertIn("letter-spacing: 0", src)
        self.assertIn("white-space: nowrap", src)
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
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn(".st-key-decide_slot", src)
        self.assertIn(
            ".oc-skel-card {\n    width: 100% !important;",
            src.replace("{{", "{").replace("}}", "}"),
        )


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

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn("body:has(.oc-skel-card) .oc-decision:not(.oc-skel-card)", src)
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

    def test_pending_nav_wipe_runtime(self) -> None:
        """General click→wipe so old pages never sit dimmed under the next run."""
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn("html.oc-pending", src)
        self.assertIn("html.oc-pending body::before", src)
        self.assertIn("#oc-nav-wipe", src)
        self.assertIn("inject_app_runtime", src)
        self.assertIn("data-test-script-state", src)
        self.assertIn("unsafe_allow_javascript", src)
        # Skeleton must not leak onto Hem
        self.assertIn("body:has(.st-key-home_hero) .oc-skel-card", src)
        self.assertIn("body:has(.st-key-home_hero) .st-key-decide_slot", src)
        # Wipe lifts only when home is gone
        self.assertIn(":not(:has(.st-key-home_hero))", src)
        html = app_mod._oc_pending_nav_runtime_html()
        self.assertIn("oc-pending", html)
        self.assertIn("oc-nav-wipe", html)
        self.assertIn("__ocDisarmTimer", html)
        self.assertIn("__ocPendingClick", html)
        self.assertIn("__ocPendingScrollCancel", html)
        self.assertIn("hasHome", html)
        self.assertIn("isRunning", html)
        self.assertIn("rerunRequested", html)
        # Click only — pointerdown blanks the page when scrolling over buttons
        self.assertIn('addEventListener("click"', html)
        self.assertNotIn('addEventListener("pointerdown"', html)
        self.assertIn("touchmove", html)
        # Must target the app document (st.html), not assume iframe→parent
        self.assertIn('[data-testid="stApp"]', html)

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
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn("rgba(250, 250, 247, 0.92)", src)
        self.assertIn("blur(20px)", src)
        self.assertIn("z-index: 10000", src)
        # Must not wipe nav bar background back to transparent
        # (children may be transparent; the bar itself must keep glass)
        nav_block = src.split("/* Glass nav MUST win")[1].split(".st-key-oc_nav_bar [class*")[0]
        self.assertIn("rgba(250, 250, 247, 0.92)", nav_block)
        # The bar rule itself is NOT background: transparent
        bar_only = nav_block.split(".st-key-oc_nav_bar [data-testid")[0]
        self.assertNotIn("background: transparent", bar_only)


if __name__ == "__main__":
    unittest.main()
