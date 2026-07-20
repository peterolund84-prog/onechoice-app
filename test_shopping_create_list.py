# -*- coding: utf-8 -*-
"""Skapa lista / merge helpers — keep merge + history reopen coverage."""

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


class CreateListMergeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "shop.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_merge_selected_subset(self) -> None:
        uid = self.user["id"]
        selected = {
            "kött & fisk": ["kycklingfilé"],
            "frukt & grönt": ["gul lök"],
        }
        db.merge_shopping_from_decision(uid, 9, selected, path=self.db_path)
        names = {r["name"] for r in db.list_shopping_items(uid, path=self.db_path)}
        self.assertEqual(names, {"kycklingfilé", "gul lök"})

    def test_accept_persists_rebuilt_shopping_via_context(self) -> None:
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
        ctx = dict(cur.get("context") or {})
        rebuilt = ctx.get("shopping")
        self.assertTrue(rebuilt and rebuilt.get("to_buy"))
        ctx.pop("shopping", None)
        cur["context"] = ctx

        import app as app_mod

        ss = _Session()
        ss["user_id"] = uid
        ss["current"] = cur
        ss["decision_id"] = cur.get("decision_id")
        ss["shopping_list_cache"] = None
        ss["shopping_merged_for"] = None
        ss["shopping_list_error"] = None
        orig_merge = db.merge_shopping_from_decision
        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(
                app_mod.db,
                "merge_shopping_from_decision",
                side_effect=lambda user_id, did, to_buy, path=None: orig_merge(
                    user_id, did, to_buy, path=self.db_path
                ),
            ):
                with mock.patch.object(app_mod, "_load_shopping_items", return_value=[]):
                    app_mod._store_shopping_on_current(rebuilt)
                    stored = ss["current"]["context"].get("shopping")
                    self.assertTrue(stored and stored.get("to_buy"))
                    app_mod._merge_accepted_shopping(ss["current"])
                    self.assertEqual(ss["shopping_merged_for"], cur.get("decision_id"))

        items = db.list_shopping_items(uid, path=self.db_path)
        self.assertGreaterEqual(len(items), 2)

    def test_restore_decision_opens_execute_for_accepted_food(self) -> None:
        uid = self.user["id"]
        r = pipeline.decide(
            uid,
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={"meal_type": "middag"},
        )
        pipeline.accept_decision(r.decision_id, db_path=self.db_path)
        row = next(
            x for x in db.list_decisions(uid, path=self.db_path) if x["id"] == r.decision_id
        )
        import app as app_mod

        ss = _Session(workout_phase="overview")
        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            app_mod._restore_decision_from_row(row)
            self.assertTrue(ss["accepted"])
            self.assertEqual(ss["page"], "execute")
            self.assertEqual(ss["current"]["suggestion"], r.suggestion)

    def test_i18n_has_open_list(self) -> None:
        import app as app_mod

        self.assertEqual(app_mod.I18N["sv"]["list_go"], "Öppna listan")
        self.assertIn("Handla", app_mod.I18N["sv"]["list_empty"])


if __name__ == "__main__":
    unittest.main()
