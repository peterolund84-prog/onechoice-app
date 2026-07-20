# -*- coding: utf-8 -*-
"""Food meal-type: inferred, confirmable, drives generation."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import db
import food_domain as fd
import pipeline


class MealTypeInferTests(unittest.TestCase):
    def test_time_windows(self) -> None:
        self.assertEqual(fd.default_meal_type(7, 0), "frukost")
        self.assertEqual(fd.default_meal_type(10, 0), "lunch")
        self.assertEqual(fd.default_meal_type(13, 29), "lunch")
        self.assertEqual(fd.default_meal_type(13, 30), "middag")
        self.assertEqual(fd.default_meal_type(18, 0), "middag")
        self.assertEqual(fd.default_meal_type(20, 0), "kvallsmal")
        self.assertEqual(fd.default_meal_type(2, 0), "kvallsmal")

    def test_breakfast_no_shopping(self) -> None:
        self.assertFalse(fd.show_shopping("frukost"))
        self.assertFalse(fd.show_shopping("kvallsmal"))
        self.assertTrue(fd.show_shopping("middag"))
        self.assertEqual(fd.max_minutes("frukost"), 10)

    def test_breakfast_decision_has_no_shop_list(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        r = pipeline.decide(
            user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=path,
            context_extra={"meal_type": "frukost"},
        )
        self.assertTrue(r.ok)
        self.assertEqual((r.context or {}).get("meal_type"), "frukost")
        self.assertFalse((r.context or {}).get("shopping"))
        self.assertNotEqual(r.execution_label, "Handla & laga")
        # Stored in decision log
        rows = db.list_decisions(user["id"], path=path)
        row = next(x for x in rows if x["id"] == r.decision_id)
        self.assertEqual((row.get("context") or {}).get("meal_type"), "frukost")
        tmp.cleanup()

    def test_dinner_still_has_shopping(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        r = pipeline.decide(
            user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=path,
            context_extra={"meal_type": "middag"},
        )
        self.assertTrue(r.ok)
        self.assertEqual((r.context or {}).get("meal_type"), "middag")
        self.assertTrue((r.context or {}).get("shopping"))
        tmp.cleanup()

    def test_repetition_is_per_meal_type(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        # Accept porridge as breakfast
        b = pipeline.decide(
            user["id"],
            "frukost",
            domain_hint="food",
            language="sv",
            db_path=path,
            context_extra={"meal_type": "frukost"},
        )
        pipeline.accept_decision(b.decision_id, db_path=path)
        # Same suggestion must NOT appear in dinner recent guard
        recent_dinner = db.recent_suggestions(
            user["id"], "food", days=7, meal_type="middag", path=path
        )
        self.assertNotIn(b.suggestion, recent_dinner)
        recent_bfast = db.recent_suggestions(
            user["id"], "food", days=7, meal_type="frukost", path=path
        )
        self.assertIn(b.suggestion, recent_bfast)
        tmp.cleanup()

    def test_evening_is_simple(self) -> None:
        cands = fd.meal_candidates("kvallsmal", "sv")
        self.assertTrue(cands)
        self.assertTrue(all((c.get("meta") or {}).get("no_cook") or (c.get("meta") or {}).get("active_minutes", 99) <= 5 for c in cands))

    def test_kvallsmal_sandwich_has_recipe_no_shopping(self) -> None:
        """Ät nu must open a recipe view — ingredients + steps (+ nutrition JSON)."""
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        r = pipeline.decide(
            user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=path,
            context_extra={"meal_type": "kvallsmal"},
        )
        self.assertTrue(r.ok)
        self.assertEqual((r.context or {}).get("meal_type"), "kvallsmal")
        self.assertFalse((r.context or {}).get("shopping"))
        recipe = (r.context or {}).get("recipe") or {}
        self.assertTrue(isinstance(recipe, dict) and recipe.get("ingredients"), recipe)
        self.assertTrue(recipe.get("steps"), recipe)
        self.assertIn("nutrition", recipe)
        # Prefer the canned sandwich when ranking allows — if not, still require recipe
        title = (r.suggestion or "").lower()
        if "smörgås" in title or "ost" in title:
            ings = " ".join(str(x).lower() for x in recipe.get("ingredients") or [])
            self.assertTrue("bröd" in ings or "ost" in ings, recipe)
            steps = " ".join(str(s).lower() for s in recipe.get("steps") or [])
            self.assertTrue("bröd" in steps or "ost" in steps, recipe["steps"])
        self.assertEqual(r.execution_label, "Ät nu")
        tmp.cleanup()

    def test_app_at_nu_opens_real_recipe_no_execute_nutrition_toggle(self) -> None:
        """UI proof: Mat + kvällsmål → Ät nu → real ingredients; nutrition only via profile."""
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        home_body = " ".join(str(m.value or "") for m in at.markdown).lower()
        home_caps = " ".join(str(c.value or "") for c in at.caption).lower()
        self.assertNotIn("build ", home_caps)
        self.assertNotIn("kvallsmal-recipe", home_body + home_caps)
        self.assertIn("onechoice", home_body)
        self.assertIn("oc-tag-dot", home_body)
        self.assertNotIn("<em>one</em>", home_body)

        at.session_state["food_meal_type"] = "kvallsmal"
        at.query_params["domain"] = "food"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        hit = False
        for b in at.button:
            if b.label and "Ät nu" in b.label:
                b.click().run()
                hit = True
                break
        self.assertTrue(hit)
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(bool(at.session_state["ui_error"]))
        body = " ".join(str(m.value or "") for m in at.markdown).lower()
        self.assertIn("recept", body)
        self.assertIn("gör så här", body)
        self.assertNotIn("oc-nut-banner", " ".join(str(m.value or "") for m in at.markdown))
        # No execute-screen nutrition toggle — profile only
        toggle_labels = [t.label or "" for t in at.toggle]
        self.assertFalse(
            any("ca-värden" in lab.lower() or "närings" in lab.lower() for lab in toggle_labels),
            toggle_labels,
        )
        self.assertNotIn("ta fram det du behöver", body)
        self.assertNotIn("gör i ordning och ät", body)
        # Real recipe: at least 2 ingredient lines with amounts/units
        self.assertTrue(
            any(u in body for u in ("dl", "msk", "tsk", "skivor", " g ")),
            body[:600],
        )

    def test_execute_heals_json_string_recipe(self) -> None:
        """Cloud may store context.recipe as a JSON string — execute must still paint."""
        import json

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "kvallsmal"
        at.query_params["domain"] = "food"
        at.run()
        cur = dict(at.session_state["current"] or {})
        ctx = cur.get("context") or {}
        if isinstance(ctx, str):
            ctx = json.loads(ctx)
        ctx = dict(ctx)
        # Simulate Cloud stringifying nested recipe
        ctx["recipe"] = json.dumps(ctx.get("recipe") or {}, ensure_ascii=False)
        ctx["shopping"] = None
        cur["context"] = ctx
        at.session_state["current"] = cur
        at.session_state["accepted"] = True
        at.session_state["page"] = "execute"
        at.run()
        self.assertEqual(at.session_state["page"], "execute")
        body = " ".join(str(m.value or "") for m in at.markdown).lower()
        self.assertIn("recept", body)
        self.assertTrue("bröd" in body or "ost" in body, body[:800])


if __name__ == "__main__":
    unittest.main()
