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


if __name__ == "__main__":
    unittest.main()
