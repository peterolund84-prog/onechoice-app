# -*- coding: utf-8 -*-
"""Execute view — quiet checklist, amounts, per-portion nutrition."""

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


class ExecuteChecklistUi(unittest.TestCase):
    def test_toggle_row_via_query_param(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if b.label and "Handla" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        did = at.session_state["decision_id"] or (
            (at.session_state["current"] or {}).get("decision_id")
        )
        ckey = f"{did}:0"
        checks = dict(at.session_state["shopping_checks"] or {})
        before = bool(checks.get(ckey, True))
        at.query_params["shop_check"] = "0"
        at.run()
        after = bool((at.session_state["shopping_checks"] or {}).get(ckey, True))
        self.assertNotEqual(before, after)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-shop-row", body)
        # Only sticky CTA should be an indigo primary among execute buttons
        primaries = [
            b.label
            for b in at.button
            if b.label and "Lägg till" in b.label
        ]
        self.assertEqual(len(primaries), 1)


if __name__ == "__main__":
    unittest.main()
