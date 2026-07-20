# -*- coding: utf-8 -*-
"""Reliable shopping + pills nav regressions."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import db
import pipeline


class _Session(dict):
    def __getattr__(self, name: str):  # noqa: ANN001
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value) -> None:  # noqa: ANN001
        self[name] = value


class ReliableShoppingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "shop.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_handla_auto_merges_shopping(self) -> None:
        """Handla & laga must fill Lista without a separate Skapa lista click."""
        uid = self.user["id"]
        r = pipeline.decide(
            uid,
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={"meal_type": "middag"},
        )
        self.assertTrue(r.ok)
        cur = r.to_dict()
        shop = (cur.get("context") or {}).get("shopping") or {}
        self.assertTrue(shop.get("to_buy"))

        import app as app_mod

        ss = _Session(
            user_id=uid,
            current=cur,
            decision_id=cur.get("decision_id"),
            pending_db_accept=True,
            guest_mode=True,
            shopping_list_cache=None,
            shopping_merged_for=None,
            shopping_list_error=None,
            route_log_id=None,
        )
        orig_merge = db.merge_shopping_from_decision
        orig_accept = pipeline.try_accept_decision

        def merge_local(user_id, did, to_buy, path=None):  # noqa: ANN001
            return orig_merge(user_id, did, to_buy, path=self.db_path)

        def accept_local(did, route_log_id=None, db_path=None):  # noqa: ANN001
            return pipeline.accept_decision(did, db_path=self.db_path)

        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(app_mod.db, "merge_shopping_from_decision", side_effect=merge_local):
                with mock.patch.object(pipeline, "try_accept_decision", side_effect=accept_local):
                    with mock.patch.object(app_mod, "_load_shopping_items", return_value=[]):
                        app_mod._flush_db_accept()

        self.assertEqual(ss["shopping_merged_for"], cur.get("decision_id"))
        items = db.list_shopping_items(uid, path=self.db_path)
        self.assertGreaterEqual(len(items), 2)

    def test_nav_uses_pills_not_href(self) -> None:
        import inspect

        import app as app_mod

        src = inspect.getsource(app_mod.nav)
        self.assertIn("st.pills", src)
        self.assertNotIn("href=", src)
        self.assertNotIn("nav_btn_", src)
        lang = inspect.getsource(app_mod.lang_bar)
        self.assertIn("st.pills", lang)
        self.assertNotIn("href=", lang)


class ReliableShoppingUiTests(unittest.TestCase):
    def test_handla_fills_list_and_nav_pills(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        uid = at.session_state["user_id"]
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if b.label and "Handla" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(bool(at.session_state["ui_error"]))
        # Auto-merge on Handla
        self.assertIsNotNone(at.session_state["shopping_merged_for"])
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Öppna listan" in lab for lab in labels), labels)
        # No fragile Skapa lista required
        self.assertFalse(any("Skapa lista" in lab for lab in labels), labels)

        for b in at.button:
            if b.label and "Öppna listan" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "lista")
        cache = at.session_state["shopping_list_cache"]
        self.assertIsInstance(cache, list)
        self.assertGreaterEqual(len(cache), 1)
        self.assertEqual(at.session_state["user_id"], uid)

        # Nav pills present
        self.assertTrue(len(at.pills) >= 1)


if __name__ == "__main__":
    unittest.main()
