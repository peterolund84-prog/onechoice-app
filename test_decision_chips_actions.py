# -*- coding: utf-8 -*-
"""Decision view: meal segmented control, outlined reroll, no page Hem links."""

from __future__ import annotations

import unittest
from unittest import mock


class DecisionChipsActionsTests(unittest.TestCase):
    def test_meal_seg_css_is_one_row_segmented(self) -> None:
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn(".st-key-meal_seg", src)
        self.assertIn("height: 36px", src)
        self.assertIn("font-size: 12px", src)
        self.assertIn("#4F46E5", src)
        # No Måltid section label in renderer
        self.assertNotIn('html.escape("Måltid"', src)
        self.assertIn('key="meal_seg"', src)
        # Buttons — never st.pills (label-leak class)
        self.assertNotIn('key="meal_pills"', src)
        self.assertNotIn('key="meal_seg_choice"', src)
        self.assertIn('key=f"meal_seg_{meal_key}"', src)
        self.assertNotIn("st.pills(", src.split("def render_meal_type_chips")[1].split("def render_movie")[0])
        # Full labels — never abbreviated chip text
        import food_domain as fd

        self.assertEqual(fd.meal_label("kvallsmal", "sv"), "Kvällsmål")

    def test_result_secondary_outlined_button_css(self) -> None:
        import app as app_mod

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn(".st-key-result_secondary_btn", src)
        self.assertIn("height: 48px", src)
        self.assertIn('key="reroll_btn"', src)
        self.assertNotIn('key="reroll_link"', src)
        self.assertNotIn('key="back_home"', src)

    def test_no_page_level_hem_buttons(self) -> None:
        import app as app_mod
        import re

        src = open(app_mod.__file__, encoding="utf-8").read()
        banned_keys = (
            "back_home",
            "back_home_locked",
            "fridge_home_cap",
            "fridge_home_conf",
            "occasion_home",
            "lista_go_home",
            "wo_exec_home",
            "privacy_home",
            "soft_home",
        )
        for key in banned_keys:
            self.assertNotIn(f'key="{key}"', src, key)
        self.assertIsNone(re.search(r'st\.button\(\s*t\("home"\)', src))

    def test_food_result_meal_seg_and_actions(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=False):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                at = AppTest.from_file("app.py", default_timeout=90)
                at.run()
                at.session_state["_auth_cookie_checked"] = True
                at.session_state["_oc_cookie_component_ready"] = True
                at.session_state["page"] = "result"
                at.session_state["guest_mode"] = True
                at.session_state["user_id"] = "uid-meal-seg"
                at.session_state["food_meal_type"] = "middag"
                at.session_state["accepted"] = False
                at.session_state["current"] = {
                    "ok": True,
                    "domain": "food",
                    "suggestion": "Kycklingwok med ris",
                    "justification": "Test",
                    "accepted": False,
                    "locked": False,
                    "reroll_index": 0,
                    "context": {"meal_type": "middag", "dish_category": "wok"},
                    "execution_type": "checklist",
                    "execution_label": "Laga",
                }
                at.run()
        self.assertFalse(at.exception)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("Måltid", body)
        self.assertNotIn("meal_pills", body)
        keys = {getattr(b, "key", None) for b in at.button}
        for mk in ("frukost", "lunch", "middag", "kvallsmal"):
            self.assertIn(f"meal_seg_{mk}", keys)
        labels = [str(getattr(b, "label", "") or "") for b in at.button]
        for needle in ("Frukost", "Lunch", "Middag", "Kvällsmål"):
            self.assertIn(needle, labels)
        self.assertIn("food_go_for_it", keys)
        self.assertIn("reroll_btn", keys)
        self.assertNotIn("back_home", keys)
        page_hem = [
            b
            for b in at.button
            if (getattr(b, "label", "") or "") == "Hem"
            and not str(getattr(b, "key", "") or "").startswith("nav_")
        ]
        self.assertEqual(page_hem, [], labels)


if __name__ == "__main__":
    unittest.main()
