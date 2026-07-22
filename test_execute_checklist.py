# -*- coding: utf-8 -*-
"""Execute view — quiet checklist, amounts, per-portion nutrition, stay-on-page."""

from __future__ import annotations

import unittest


class ExecuteChecklistHelpers(unittest.TestCase):
    def test_amount_map_from_structured_and_lines(self) -> None:
        import app as app_mod

        recipe = {
            "ingredients_structured": [
                {"name": "röda linser", "amount": "2", "unit": "dl"},
                {"name": "gul lök", "amount": "1", "unit": "st"},
            ],
            "ingredient_lines": ["2 msk curry", "olja"],
        }
        amap = app_mod._recipe_amount_map(recipe)
        self.assertEqual(amap.get("röda linser"), "2 dl")
        self.assertEqual(amap.get("gul lök"), "1 st")
        self.assertEqual(amap.get("curry"), "2 msk")

    def test_split_skip_hint(self) -> None:
        import app as app_mod

        name, hinted = app_mod._split_shop_item_label("ris — hoppa över om du har")
        self.assertEqual(name, "ris")
        self.assertTrue(hinted)

    def test_pot_total_nutrition_divided(self) -> None:
        import shopping

        healed = shopping.ensure_recipe_nutrition(
            {
                "title": "Linsgryta",
                "ingredients": ["linser", "lök", "ris"],
                "steps": ["Koka."],
                "portioner": 4,
                "kcal_per_portion": 1700,
                "protein_g_per_portion": 60,
                "nutrition": {"kcal": 1700, "protein_g": 60, "servings": 4},
            },
            suggestion="Linsgryta",
        )
        self.assertLess(healed["kcal_per_portion"], 900)
        self.assertEqual(healed["portioner"], 4)
        line = shopping.format_nutrition_line(
            healed.get("nutrition"), language="sv", recipe=healed
        )
        self.assertIn("per portion", line)
        self.assertRegex(line, r"Ca\s+\d+\s*kcal per portion")

    def test_selected_defaults_unchecked(self) -> None:
        import app as app_mod
        from types import SimpleNamespace
        from unittest import mock

        shop = {"to_buy": {"skafferi": ["ris", "linser", "curry"]}}
        ss = {"shopping_checks": {}, "language": "sv"}
        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            self.assertEqual(app_mod._count_checked_shop_items(shop, 1), 0)
            app_mod._set_all_shop_checks(shop, 1, checked=True)
            self.assertEqual(app_mod._count_checked_shop_items(shop, 1), 3)
            app_mod._toggle_shop_check(1, 0)
            self.assertEqual(app_mod._count_checked_shop_items(shop, 1), 2)


class ExecuteChecklistUi(unittest.TestCase):
    def _open_execute(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        return at

    def test_toggle_checkboxes_stay_on_execute(self) -> None:
        at = self._open_execute()
        page_before = at.session_state["page"]
        suggestion = (at.session_state["current"] or {}).get("suggestion")
        boxes = list(at.checkbox)
        self.assertGreaterEqual(len(boxes), 3, [getattr(c, "label", None) for c in boxes])
        # All start unchecked
        self.assertFalse(any(bool(c.value) for c in boxes[:3]))

        boxes[0].check().run()
        self.assertEqual(at.session_state["page"], page_before)
        self.assertEqual((at.session_state["current"] or {}).get("suggestion"), suggestion)
        boxes = list(at.checkbox)
        boxes[1].check().run()
        self.assertEqual(at.session_state["page"], "execute")
        boxes = list(at.checkbox)
        boxes[2].check().run()
        self.assertEqual(at.session_state["page"], "execute")
        checked = sum(1 for c in at.checkbox if bool(c.value))
        self.assertEqual(checked, 3)

        # Untoggle one
        boxes = list(at.checkbox)
        boxes[1].uncheck().run()
        self.assertEqual(at.session_state["page"], "execute")
        checked = sum(1 for c in at.checkbox if bool(c.value))
        self.assertEqual(checked, 2)

        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Lägg till i handlingslista (2)" in lab for lab in labels), labels)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-shop-pick-marker", body)
        self.assertNotIn('href="?shop_check=', body)

    def test_add_to_list_merges_exactly_checked(self) -> None:
        at = self._open_execute()
        boxes = list(at.checkbox)
        self.assertGreaterEqual(len(boxes), 2)
        boxes[0].check().run()
        boxes = list(at.checkbox)
        boxes[1].check().run()
        self.assertEqual(at.session_state["page"], "execute")

        for b in at.button:
            if b.label and "Lägg till i handlingslista (2)" in b.label:
                b.click().run()
                break
        else:
            self.fail([b.label for b in at.button])

        self.assertEqual(at.session_state["page"], "execute")
        cache = at.session_state["shopping_list_cache"]
        self.assertIsInstance(cache, list)
        self.assertEqual(len(cache), 2)
        self.assertTrue(all(not r.get("checked") for r in cache))


if __name__ == "__main__":
    unittest.main()
