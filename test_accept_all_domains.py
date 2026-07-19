# -*- coding: utf-8 -*-
"""Accept flow must work for ALL domains — never crash the Streamlit UI."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import pipeline


class AcceptAllDomainsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_try_accept_never_raises(self) -> None:
        self.assertIsNone(pipeline.try_accept_decision(None, db_path=self.db_path))
        self.assertIsNone(pipeline.try_accept_decision(999999, db_path=self.db_path))

    def test_accept_all_five_domains(self) -> None:
        for domain in ("food", "clothes", "movie", "workout", "weekend"):
            extra = {"occasion": "fest", "intent": "wear"} if domain == "clothes" else None
            r = pipeline.decide(
                self.user["id"],
                "",
                domain_hint=domain,
                language="sv",
                db_path=self.db_path,
                context_extra=extra,
            )
            self.assertTrue(r.ok, domain)
            self.assertIsNotNone(r.decision_id, domain)
            self.assertTrue(r.execution_label, domain)
            out = pipeline.try_accept_decision(r.decision_id, db_path=self.db_path)
            self.assertIsNotNone(out, domain)
            self.assertEqual(out["status"], "accepted", domain)

    def test_supabase_failure_falls_back_to_sqlite(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "",
            domain_hint="workout",
            language="sv",
            db_path=self.db_path,
        )
        # With an explicit sqlite path, accept must succeed even if supabase is "on"
        with mock.patch.object(db, "_use_supabase", return_value=False):
            out = pipeline.try_accept_decision(r.decision_id, db_path=self.db_path)
        self.assertIsNotNone(out)
        self.assertEqual(out["status"], "accepted")

        # Hard failure is swallowed by try_accept (never raises to UI)
        with mock.patch.object(
            pipeline, "accept_decision", side_effect=TypeError("boom")
        ):
            self.assertIsNone(pipeline.try_accept_decision(1, db_path=self.db_path))

    def test_safe_toast_without_toast_attr(self) -> None:
        import app as app_mod

        class NoToast:
            def caption(self, *a, **k):
                return None

            def __getattr__(self, name):
                raise AttributeError(name)

        with mock.patch.object(app_mod, "st", NoToast()):
            # Must not raise
            app_mod.safe_toast("Sparat — bra val.")


class ClothesOccasionTests(unittest.TestCase):
    def test_fest_justification_mentions_occasion(self) -> None:
        import clothes_domain as cd

        out = cd.outfit_for_occasion("fest", section="herr", language="sv")
        self.assertIn("fest", out["justification"].lower())
        self.assertIn("skjorta", out["suggestion"].lower())

    def test_barnkalas_practical(self) -> None:
        import clothes_domain as cd

        out = cd.outfit_for_occasion("barnkalas", section="båda", language="sv")
        blob = f"{out['suggestion']} {out['justification']}".lower()
        self.assertTrue(any(w in blob for w in ("bekväm", "fläck", "jeans")))

    def test_pipeline_uses_occasion(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        r = pipeline.decide(
            user["id"],
            "Vad ska jag ha på mig?",
            domain_hint="clothes",
            language="sv",
            db_path=path,
            context_extra={"occasion": "fest", "intent": "wear"},
        )
        self.assertTrue(r.ok)
        self.assertIn("fest", (r.justification or "").lower())
        tmp.cleanup()

    def test_profile_ensure(self) -> None:
        import clothes_domain as cd

        p = cd.ensure_clothes_profile({})
        self.assertEqual(p["clothes"]["section"], "båda")
        self.assertIn("top", p["clothes"]["sizes"])


class AppAcceptUiTests(unittest.TestCase):
    def test_app_test_accept_workout_and_clothes(self) -> None:
        from streamlit.testing.v1 import AppTest

        for domain, needle in (
            ("workout", "Starta"),
            ("clothes", "Bygg"),
            ("food", "Handla"),
        ):
            at = AppTest.from_file("app.py", default_timeout=45)
            at.run()
            self.assertFalse(at.exception)
            uid = at.session_state["user_id"]
            extra = {"occasion": "jobb", "intent": "wear"} if domain == "clothes" else None
            r = pipeline.decide(
                str(uid), "", domain_hint=domain, language="sv", context_extra=extra
            )
            at.session_state["current"] = r.to_dict()
            at.session_state["decision_id"] = r.decision_id
            at.session_state["accepted"] = False
            at.session_state["page"] = "result"
            at.session_state["clothes_occasion"] = "jobb" if domain == "clothes" else None
            at.session_state["ui_error"] = None
            at.run()
            self.assertFalse(at.exception, domain)
            labels = [b.label for b in at.button]
            self.assertTrue(any(needle in (lab or "") for lab in labels), labels)
            for b in at.button:
                if needle in (b.label or ""):
                    b.click().run()
                    break
            self.assertFalse(at.exception, domain)
            self.assertTrue(at.session_state["accepted"], domain)
            err = any("Något gick fel" in (m.value or "") for m in at.markdown)
            self.assertFalse(err, domain)


if __name__ == "__main__":
    unittest.main()
