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
        # Hide prior cards only while decide_slot hosts the skeleton — never
        # via broad body:has(.oc-skel-card) (orphaned st.html blanked images).
        self.assertIn('st-key-decide_slot"] .oc-skel-card', css)
        self.assertIn('st-key-decide_slot"] [data-oc-deciding]', css)
        self.assertNotIn(
            "body:has(.oc-skel-card):not(:has(.oc-result))",
            css,
        )
        # Result/execute hard-override keeps dish image visible
        self.assertIn(
            ".block-container:has(.oc-result) .oc-food-img",
            css,
        )
        self.assertIn("data-oc-deciding", src)
        self.assertIn("_decide_skel_painted", src)
        self.assertIn("oc-app-css-head", src)
        self.assertIn("read_css(BUILD_ID)", src)

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
        # May mention oc-app-css-head only to REMOVE leftover head CSS — never re-inject
        self.assertNotIn('id="oc-app-css-head"', src)
        self.assertIn("oc-app-css-head", src)  # cleanup script
        self.assertIn("read_css(BUILD_ID)", src)
        # Ghost wipe hacks removed after perf pass
        self.assertNotIn("inject_app_runtime", src)
        self.assertNotIn("_oc_pending_nav_runtime_html", src)
        css = _styles()
        self.assertNotIn("html.oc-pending", css)
        self.assertNotIn("#oc-nav-wipe", css)
        self.assertIn(
            "body:not(:has(.oc-result)) .st-key-result_primary_btn",
            css,
        )
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
        nav_block = css.split("/* Bottom nav — frosted glass bar")[1].split(
            "[class*=\"st-key-nav_\"] div.stButton > button::before"
        )[0]
        self.assertIn("rgba(250, 250, 247, 0.92)", nav_block)
        # The bar rule itself is NOT background: transparent
        bar_only = nav_block.split(".st-key-oc_nav_bar [data-testid")[0]
        self.assertNotIn("background: transparent", bar_only)

    def test_nav_buttons_remain_tappable_when_secondary(self) -> None:
        """iOS drops taps on background:transparent — secondary tabs must stay hittable."""
        css = _styles()
        self.assertIn("cursor: pointer !important", css)
        self.assertIn("touch-action: manipulation !important", css)
        # Must not force fully transparent fills on nav secondaries
        self.assertIn("rgba(250, 250, 247, 0.01)", css)
        self.assertIn(
            ".st-key-oc_nav_bar {",
            css,
        )
        # Footer must claim pointer-events even if a ghost overlay exists
        bar = css.split(".st-key-oc_nav_bar {")[1].split(
            "[class*=\"st-key-nav_\"] div.stButton > button::before"
        )[0]
        self.assertIn("pointer-events: auto !important", bar)
        # Compact footer: hard 64px + safe-area, 44px pills, 4px icon/label gap
        self.assertIn("height: calc(64px + env(safe-area-inset-bottom))", bar)
        self.assertIn("padding: 8px 0.4rem calc(8px + env(safe-area-inset-bottom))", bar)
        self.assertIn("min-height: 44px !important", bar)
        self.assertIn("gap: 4px !important", bar)
        # Content clears nav + 16px
        self.assertIn("calc(80px + env(safe-area-inset-bottom))", css)
        self.assertNotIn("calc(88px + env(safe-area-inset-bottom))", css)
        # Dead legacy nav generations must stay gone
        self.assertNotIn(".oc-nav-btns-marker", css)
        self.assertNotIn(".st-key-oc_nav_pills", css)
        self.assertNotIn(".oc-nav {", css)

    def test_input_instructions_chrome_hidden(self) -> None:
        """English Streamlit 'Press Enter… · 0/200' must never paint over placeholders."""
        css = _styles()
        self.assertIn('[data-testid="InputInstructions"]', css)
        self.assertRegex(
            css,
            r'\[data-testid="InputInstructions"\][\s\S]{0,800}?display:\s*none\s*!important',
        )
        import router as rt
        import app as app_mod

        self.assertEqual(rt.MAX_INPUT_CHARS, 200)
        src = open(app_mod.__file__, encoding="utf-8").read()
        # Kill chrome at the source — not only via CSS
        self.assertIn("enter_to_submit=False", src)
        # Widget must not pass max_chars (that paints 0/200); Python still enforces
        self.assertNotIn(
            "key=\"home_free_input\",\n                        placeholder=t(\"home_free_placeholder\"),\n                        max_chars=",
            src,
        )
        self.assertIn("len(question) > rt.MAX_INPUT_CHARS", src)


if __name__ == "__main__":
    unittest.main()
