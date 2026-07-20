# -*- coding: utf-8 -*-
"""Regression: session-safe nav + fast food Mat chip."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import db
import pipeline
import router


class SessionSafeNavTests(unittest.TestCase):
    def test_nav_uses_buttons_not_href(self) -> None:
        import inspect

        import app as app_mod

        src = inspect.getsource(app_mod.nav)
        self.assertIn("st.pills", src)
        self.assertNotIn("href=", src)

    def test_lang_bar_uses_buttons_not_href(self) -> None:
        import inspect

        import app as app_mod

        src = inspect.getsource(app_mod.lang_bar)
        self.assertIn("st.pills", src)
        self.assertNotIn("href=", src)

    def test_nav_survives_lista_tap(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        uid = at.session_state["user_id"]
        self.assertTrue(uid)
        hit = False
        for p in at.pills:
            if getattr(p, "key", None) == "oc_nav_pills":
                p.set_value("lista").run()
                hit = True
                break
        self.assertTrue(hit)
        self.assertEqual(at.session_state["page"], "lista")
        self.assertEqual(at.session_state["user_id"], uid)
        self.assertNotEqual(at.session_state["page"], "auth")


class FastFoodDecideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "fast.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_mat_chip_skips_grok_on_first_decide(self) -> None:
        with mock.patch.object(pipeline, "_grok_candidates") as grok:
            grok.side_effect = AssertionError("Grok must not run on first Mat chip")
            t0 = time.perf_counter()
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag äta?",
                domain_hint="food",
                language="sv",
                db_path=self.db_path,
                grok_api_key="xai-fake-key-for-test-12345",
                context_extra={"meal_type": "middag"},
            )
            elapsed = time.perf_counter() - t0
        self.assertTrue(r.ok)
        self.assertTrue(r.suggestion)
        grok.assert_not_called()
        self.assertLess(elapsed, 2.0, f"local food decide took {elapsed:.2f}s")

    def test_reroll_may_call_grok(self) -> None:
        called = {"n": 0}

        def fake_grok(*_a, **_k):  # noqa: ANN001
            called["n"] += 1
            return [
                {
                    "suggestion": "Kycklingwok med ris",
                    "justification": "Snabb wok.",
                    "wildcard": False,
                    "meta": {"meal_type": "middag", "ingredients": ["kycklingfilé", "ris"]},
                }
            ] * 3

        with mock.patch.object(pipeline, "_grok_candidates", side_effect=fake_grok):
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag äta?",
                domain_hint="food",
                language="sv",
                db_path=self.db_path,
                grok_api_key="xai-fake-key-for-test-12345",
                reroll=True,
                reroll_index=1,
                context_extra={"meal_type": "middag"},
            )
        self.assertTrue(r.ok)
        self.assertEqual(called["n"], 1)

    def test_router_local_first_for_middag(self) -> None:
        with mock.patch.object(router, "_llm_route") as llm:
            llm.side_effect = AssertionError("LLM router must not run")
            r = router.route_question(
                "vad ska jag äta till middag",
                language="sv",
                grok_api_key="xai-fake-key-for-test-12345",
            )
        self.assertEqual(r.route, "IN_DOMAIN")
        self.assertEqual(r.domain, "food")
        self.assertGreaterEqual(r.confidence, 0.85)
        llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
