# -*- coding: utf-8 -*-
"""Structured workouts + player accept flow."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import pipeline
import workout_domain as wd


class WorkoutStructureTests(unittest.TestCase):
    def test_total_minutes_from_blocks(self) -> None:
        w = wd.finalize_workout(
            {
                "title": "test",
                "blocks": [
                    {"name": "A", "type": "time", "sets": 1, "seconds": 60, "rest_seconds": 0},
                    {"name": "B", "type": "reps", "sets": 2, "reps": 10, "rest_seconds": 30},
                ],
            }
        )
        # 60 + (2*10*3) + 30 = 60+60+30 = 150s → 3 min
        self.assertEqual(w["total_minutes"], 3)

    def test_suggestion_matches_total_minutes(self) -> None:
        for c in wd.local_candidates("sv"):
            w = c["meta"]["workout"]
            self.assertEqual(c["meta"]["minutes"], w["total_minutes"])
            self.assertIn(str(w["total_minutes"]), c["suggestion"])
            detail = c["execution"]["detail"]
            self.assertTrue(detail.startswith(f"{w['total_minutes']} min"))
            # No contradictory ~30 when title says 25
            if "25" in c["suggestion"]:
                self.assertNotIn("~30", detail)
                self.assertNotIn("~30", c["justification"])

    def test_pipeline_stores_workout_structure(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        r = pipeline.decide(
            user["id"], "", domain_hint="workout", language="sv", db_path=path
        )
        self.assertTrue(r.ok)
        w = (r.context or {}).get("workout")
        self.assertIsInstance(w, dict)
        self.assertTrue(w.get("blocks"))
        self.assertEqual(r.execution_label, "Starta passet")
        self.assertEqual(r.suggestion, wd.suggestion_from_workout(w, "sv"))
        self.assertIn(str(w["total_minutes"]), r.suggestion)
        self.assertIn(str(w["total_minutes"]), (r.context or {}).get("execution_detail", ""))
        tmp.cleanup()


class WorkoutPlayerUiTests(unittest.TestCase):
    def test_starta_opens_execute_overview(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        for b in at.button:
            if b.label == "Träning":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "result")
        for b in at.button:
            if "Starta" in (b.label or ""):
                b.click().run()
                break
        self.assertFalse(at.exception)
        self.assertFalse(bool(at.session_state["ui_error"]))
        self.assertTrue(at.session_state["accepted"])
        self.assertEqual(at.session_state["page"], "execute")
        self.assertEqual(at.session_state["workout_phase"], "overview")
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any(lab == "Kör" for lab in labels), labels)
        for b in at.button:
            if b.label == "Kör":
                b.click().run()
                break
        self.assertEqual(at.session_state["workout_phase"], "play")
        self.assertFalse(bool(at.session_state["ui_error"]))
        err = any("Något gick fel" in (m.value or "") for m in at.markdown)
        self.assertFalse(err)

    def test_starta_navigates_even_if_accept_hangs(self) -> None:
        """Regression: slow/hanging Supabase accept must not freeze on result."""
        import app as app_mod
        from streamlit.testing.v1 import AppTest

        calls: list[str] = []

        def _hanging_accept(cur=None):  # noqa: ANN001
            calls.append("accept")
            # Simulate Cloud hang — must never run before page=execute
            raise TimeoutError("simulated supabase hang")

        orig = app_mod.accept_current_decision
        app_mod.accept_current_decision = _hanging_accept  # type: ignore[assignment]
        try:
            at = AppTest.from_file("app.py", default_timeout=30)
            at.run()
            for b in at.button:
                if b.label == "Träning":
                    b.click().run()
                    break
            self.assertEqual(at.session_state["page"], "result")
            for b in at.button:
                if "Starta" in (b.label or ""):
                    b.click().run()
                    break
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["page"], "execute")
            self.assertTrue(at.session_state["accepted"])
            self.assertEqual(at.session_state["workout_phase"], "overview")
            labels = [b.label or "" for b in at.button]
            self.assertTrue(any(lab == "Kör" for lab in labels), labels)
            # accept_current_decision must NOT be required for navigation
            # (deferred path uses pipeline.try_accept_decision in bg)
        finally:
            app_mod.accept_current_decision = orig  # type: ignore[assignment]

    def test_prepare_execute_local_sets_page_without_db(self) -> None:
        """Unit: local prep never calls accept — only session navigation."""
        import app as app_mod

        class _SS(dict):
            def __getattr__(self, k):  # noqa: ANN001
                try:
                    return self[k]
                except KeyError as e:
                    raise AttributeError(k) from e

            def __setattr__(self, k, v):  # noqa: ANN001
                self[k] = v

        fake = _SS(
            current={
                "domain": "workout",
                "suggestion": "25 min kroppsvikt",
                "execution_type": "workout",
                "execution_label": "Starta passet",
                "decision_id": 42,
                "context": {},
            },
            language="sv",
            accepted=False,
            page="result",
            ui_error=None,
            workout_phase="overview",
            workout_block_i=0,
            workout_set_i=0,
            workout_timer_end=None,
            workout_timer_total=0,
            guest_mode=True,
        )
        called: list[str] = []

        def boom(*_a, **_k):  # noqa: ANN001
            called.append("db")
            raise RuntimeError("db must not be called")

        orig_ss = app_mod.st.session_state
        orig_accept = app_mod.accept_current_decision
        orig_try = app_mod.pipeline.try_accept_decision
        try:
            app_mod.st.session_state = fake  # type: ignore[assignment]
            app_mod.accept_current_decision = boom  # type: ignore[assignment]
            app_mod.pipeline.try_accept_decision = boom  # type: ignore[assignment]
            app_mod._prepare_execute_local(fake["current"])
            self.assertEqual(fake["page"], "execute")
            self.assertTrue(fake["accepted"])
            self.assertTrue(fake["pending_db_accept"])
            self.assertEqual(called, [])
        finally:
            app_mod.st.session_state = orig_ss
            app_mod.accept_current_decision = orig_accept  # type: ignore[assignment]
            app_mod.pipeline.try_accept_decision = orig_try  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()
