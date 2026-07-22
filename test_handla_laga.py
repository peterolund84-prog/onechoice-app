# -*- coding: utf-8 -*-
"""Tests for Handla & laga accept → execute flow."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import pipeline
import shopping


class HandlaLagaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "test.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_food_label_is_handla_laga(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={"meal_type": "middag"},
        )
        self.assertTrue(r.ok)
        if r.execution_type == "recipe":
            self.assertEqual(r.execution_label, "Handla & laga")

    def test_accept_requires_decision_id(self) -> None:
        with self.assertRaises(ValueError):
            pipeline.accept_decision(None, db_path=self.db_path)

    def test_accept_rejects_bad_id_type(self) -> None:
        with self.assertRaises(ValueError):
            pipeline.accept_decision(object(), db_path=self.db_path)  # type: ignore[arg-type]

    def test_accept_locks_decision_in_db(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
        )
        self.assertIsNotNone(r.decision_id)
        out = pipeline.accept_decision(r.decision_id, db_path=self.db_path)
        self.assertEqual(out["status"], "accepted")
        rows = db.list_decisions(self.user["id"], path=self.db_path)
        row = next(x for x in rows if x["id"] == r.decision_id)
        self.assertEqual(row["status"], "accepted")

    def test_recipe_attached_with_swedish_steps(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={"meal_type": "middag"},
        )
        ctx = r.context or {}
        shop = ctx.get("shopping") or {}
        recipe = ctx.get("recipe") or shop.get("recipe")
        self.assertTrue(recipe)
        self.assertTrue(recipe.get("ingredients"))
        self.assertTrue(recipe.get("steps"))
        blob = " ".join(recipe["steps"]).lower()
        self.assertTrue(
            any(u in blob for u in ("dl", "msk", "tsk", "g ", "min")),
            blob,
        )

    def test_build_recipe_kycklingwok(self) -> None:
        recipe = shopping.build_recipe("Kycklingwok med ris")
        self.assertIn("kycklingfilé", " ".join(recipe["ingredients"]).lower())
        self.assertGreaterEqual(len(recipe["steps"]), 3)

    def test_recipe_gets_protein_when_meta_omitted_it(self) -> None:
        """Regression: protein added to to_buy must also land in recipe ingredients."""
        shop = shopping.build_shopping(
            "Kryddig kycklinggryta",
            meta={"ingredients": ["gul lök", "ris", "curry", "olja", "salt"]},
        )
        self.assertIsNotNone(shop)
        assert shop is not None
        ings = " ".join(shop["ingredients"]).lower()
        self.assertIn("kyckling", ings)
        recipe = shop["recipe"]
        self.assertIn("kyckling", " ".join(recipe["ingredients"]).lower())
        self.assertTrue(any("kyckling" in s.lower() for s in recipe["steps"]))

    def test_accept_and_open_execute_state_machine(self) -> None:
        """Simulate session transitions without Streamlit UI."""
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
        )
        cur = r.to_dict()
        did = int(cur["decision_id"])
        pipeline.accept_decision(did, db_path=self.db_path)
        cur["locked"] = True
        cur["accepted"] = True
        self.assertTrue(cur["accepted"])
        self.assertTrue(cur["locked"])
        again = pipeline.accept_decision(did, db_path=self.db_path)
        self.assertEqual(again["status"], "accepted")


class AppErrorBoundaryImportTests(unittest.TestCase):
    def test_app_defines_execute_and_error_helpers(self) -> None:
        import app as app_mod

        self.assertTrue(callable(app_mod.page_execute))
        self.assertTrue(callable(app_mod.accept_and_open_execute))
        self.assertTrue(callable(app_mod.render_error_boundary))
        self.assertIn("Handla & laga", app_mod.I18N["sv"]["handla_laga"])
        self.assertIn("Något gick fel", app_mod.I18N["sv"]["error_friendly"])

    def test_streamlit_rerun_not_treated_as_app_error(self) -> None:
        import app as app_mod
        from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
        from streamlit.runtime.scriptrunner import RerunData

        self.assertTrue(app_mod._is_streamlit_control_flow(RerunException(RerunData())))
        self.assertFalse(app_mod._is_streamlit_control_flow(ValueError("x")))


class HandlaLagaUiTests(unittest.TestCase):
    def test_handla_opens_execute_even_if_share_explodes(self) -> None:
        """Regression: share must never turn Handla & laga into the error boundary."""
        import app as app_mod
        from streamlit.testing.v1 import AppTest

        def boom(*_a, **_k):  # noqa: ANN001
            raise RuntimeError("share intentionally broken")

        orig = app_mod.render_share_for_decision
        app_mod.render_share_for_decision = boom  # type: ignore[assignment]
        try:
            at = AppTest.from_file("app.py", default_timeout=60)
            at.run()
            at.session_state["food_meal_type"] = "middag"
            at.query_params["domain"] = "food"
            at.run()
            for b in at.button:
                if (b.label or "") == "Välj":
                    b.click().run()
                    hit = True
                    break
            self.assertTrue(hit)
            self.assertFalse(at.exception)
            self.assertFalse(bool(at.session_state["ui_error"]))
            self.assertEqual(at.session_state["page"], "execute")
            self.assertTrue(at.session_state["accepted"])
            body = " ".join(str(m.value or "") for m in at.markdown)
            self.assertNotIn("Något gick fel", body)
            labels = [b.label or "" for b in at.button]
            self.assertTrue(any("Tillbaka" in lab or "Back" in lab for lab in labels), labels)
        finally:
            app_mod.render_share_for_decision = orig  # type: ignore[assignment]

    def test_handla_survives_string_context(self) -> None:
        """Cloud/Supabase can leave context as a JSON string — must not crash execute."""
        import json

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        cur = dict(at.session_state["current"] or {})
        cur["context"] = json.dumps(cur.get("context") or {}, ensure_ascii=False)
        at.session_state["current"] = cur
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertFalse(bool(at.session_state["ui_error"]))
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(at.exception)

    def test_lock_card_survives_string_context(self) -> None:
        """After accept, lock card must not crash when context is a JSON string."""
        import json

        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self.assertTrue(at.session_state["accepted"])
        # Back to lock card on result
        for b in at.button:
            if b.label and ("Tillbaka" in b.label or "Back" in b.label):
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "result")
        # Simulate Cloud leaving context as a string, then return to lock card
        cur = dict(at.session_state["current"] or {})
        ctx = cur.get("context")
        if not isinstance(ctx, dict):
            ctx = _as_dict_safe(ctx)
        cur["context"] = json.dumps(ctx, ensure_ascii=False)
        at.session_state["current"] = cur
        at.session_state["accepted"] = True
        at.session_state["page"] = "result"
        at.run(timeout=60)
        last = None
        try:
            last = at.session_state["_last_ui_error"]
        except Exception:
            last = None
        self.assertFalse(bool(at.session_state["ui_error"]), last)
        self.assertEqual(at.session_state["page"], "result")
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Handla" in lab for lab in labels), labels)
        # Handla again from lock card
        for b in at.button:
            if b.label and "Handla" in b.label:
                b.click().run()
                break
        try:
            last = at.session_state["_last_ui_error"]
        except Exception:
            last = None
        self.assertFalse(bool(at.session_state["ui_error"]), last)
        self.assertEqual(at.session_state["page"], "execute")


def _as_dict_safe(value):  # noqa: ANN001
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


if __name__ == "__main__":
    unittest.main()
