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
        # Missing row soft-succeeds (Cloud hybrid) — must not raise
        out = pipeline.try_accept_decision(999999, db_path=self.db_path)
        self.assertIsNotNone(out)
        self.assertEqual(out["status"], "accepted")

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

    def test_record_feedback_soft_succeeds_when_sqlite_missing(self) -> None:
        """Supabase accept fail → sqlite miss must not raise (Cloud hybrid)."""
        out = db.record_feedback(999999001, accepted=True, path=self.db_path)
        self.assertEqual(out["status"], "accepted")
        self.assertEqual(out["id"], 999999001)
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
        with mock.patch("pipeline.random.random", return_value=0.0):
            r = pipeline.decide(
                user["id"],
                "Vad ska jag ha på mig?",
                domain_hint="clothes",
                language="sv",
                db_path=path,
                context_extra={"occasion": "fest", "intent": "wear"},
            )
        self.assertTrue(r.ok)
        blob = f"{r.suggestion} {r.justification}".lower()
        self.assertTrue(
            "fest" in blob or "skjorta" in blob or "klänning" in blob,
            blob,
        )
        self.assertEqual((r.context or {}).get("occasion"), "fest")
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
            ("food", "Välj"),
        ):
            at = AppTest.from_file("app.py", default_timeout=45)
            at.run()
            self.assertFalse(at.exception)
            uid = at.session_state["user_id"]
            extra = {"occasion": "jobb", "intent": "wear"} if domain == "clothes" else None
            if domain == "food":
                at.session_state["food_meal_type"] = "middag"
            r = pipeline.decide(
                str(uid),
                "",
                domain_hint=domain,
                language="sv",
                context_extra=(
                    {"meal_type": "middag"}
                    if domain == "food"
                    else extra
                ),
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
            self.assertFalse(bool(at.session_state["ui_error"]), domain)
            if domain == "workout":
                self.assertEqual(at.session_state["page"], "execute", domain)
            err = any("Något gick fel" in (m.value or "") for m in at.markdown)
            self.assertFalse(err, domain)

    def test_meal_type_pills_visible_on_food_result(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=45)
        at.run()
        # Full path: home → Mat
        at.query_params["domain"] = "food"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        self.assertFalse(at.exception)
        keys = {getattr(b, "key", None) for b in at.button}
        for mk in ("frukost", "lunch", "middag", "kvallsmal"):
            self.assertIn(f"meal_seg_{mk}", keys, keys)
        labels = [b.label or "" for b in at.button]
        for needle in ("Frukost", "Lunch", "Middag", "Kvällsmål"):
            self.assertIn(needle, labels)
        self.assertNotIn("meal_pills", " ".join(str(m.value or "") for m in at.markdown))
        lunch = next(b for b in at.button if getattr(b, "key", None) == "meal_seg_lunch")
        lunch.click().run()
        self.assertFalse(at.exception)
        self.assertFalse(bool(at.session_state["ui_error"]))
        self.assertEqual(at.session_state["food_meal_type"], "lunch")
        cur = at.session_state["current"] or {}
        self.assertEqual((cur.get("context") or {}).get("meal_type"), "lunch")
        # Accept must work after meal switch (Välj — or lunch-out map link)
        labels = [b.label or "" for b in at.button]
        if any("karta" in L.lower() or "map" in L.lower() for L in labels):
            self.assertEqual((cur.get("context") or {}).get("meal_type"), "lunch")
            self.assertFalse(bool(at.session_state["ui_error"]))
            return
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertTrue(at.session_state["accepted"])
        self.assertFalse(bool(at.session_state["ui_error"]))
        self.assertEqual(at.session_state["page"], "execute")

    def test_css_chip_rules_override_ghost_secondary(self) -> None:
        """Regression: grid chips are ghost borders, not underlined secondary links."""
        import app as app_mod
        from unittest import mock

        captured: list[str] = []

        class FakeSt:
            def markdown(self, body, **kwargs):
                captured.append(str(body))

            def __getattr__(self, name):
                return lambda *a, **k: None

        with mock.patch.object(app_mod, "st", FakeSt()):
            app_mod.inject_css()
        css = "\n".join(captured)
        self.assertIn("stHorizontalBlock", css)
        self.assertIn("stButtonGroup", css)
        self.assertIn(
            'div[data-testid="stHorizontalBlock"] div.stButton > button',
            css,
        )
        # Ghost chips: transparent fill + border (not Streamlit underline secondary)
        self.assertIn("background: transparent !important", css)
        self.assertIn("border-radius: 999px !important", css)
        self.assertIn("a.oc-chip", css)

    def test_clothes_occasion_buttons_visible(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=45)
        at.run()
        at.session_state["page"] = "clothes_occasion"
        at.session_state["pending_clothes_question"] = "Vad ska jag ha på mig?"
        at.session_state["ui_error"] = None
        at.run()
        self.assertFalse(at.exception)
        labels = [b.label or "" for b in at.button]
        for needle in ("Jobb", "Vardag", "Fest"):
            self.assertTrue(
                any(needle in lab for lab in labels),
                f"missing occasion button {needle}: {labels}",
            )

    def test_e2e_workout_starta_from_home(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        # Home domain chips are HTML links (?domain=), not Streamlit buttons
        at.query_params["domain"] = "workout"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        self.assertFalse(at.exception)
        hit = False
        for b in at.button:
            if "Starta" in (b.label or ""):
                b.click().run()
                hit = True
                break
        self.assertTrue(hit)
        self.assertFalse(at.exception)
        self.assertTrue(at.session_state["accepted"])
        self.assertFalse(bool(at.session_state["ui_error"]))
        self.assertEqual(at.session_state["page"], "execute")
        err = any("Något gick fel" in (m.value or "") for m in at.markdown)
        self.assertFalse(err)
        # Overview — Kör button, not dead-end lock card
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any(lab == "Kör" for lab in labels), labels)

    def test_e2e_clothes_occasion_from_home(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        # Home domain chips are HTML links (?domain=), not Streamlit buttons
        at.query_params["domain"] = "clothes"
        at.run()
        self.assertEqual(at.session_state["page"], "clothes_occasion")
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Fest" in L for L in labels), labels)
        for b in at.button:
            if "Fest" in (b.label or ""):
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "result")
        for b in at.button:
            if "Bygg" in (b.label or ""):
                b.click().run()
                break
        self.assertTrue(at.session_state["accepted"])
        self.assertFalse(bool(at.session_state["ui_error"]))

    def test_home_domain_buttons_visible(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=45)
        at.run()
        self.assertFalse(at.exception)
        body = " ".join(str(m.value or "") for m in at.markdown)
        labels = [b.label or "" for b in at.button]
        for needle in ("Mat", "Kläder", "Träning"):
            self.assertIn(needle, labels, f"missing domain button {needle}")
        for needle in ("Mat", "Kläder", "Träning"):
            self.assertNotIn(f'href="?domain={needle.lower()}"', body)
        self.assertNotIn('href="?domain=', body)


if __name__ == "__main__":
    unittest.main()
