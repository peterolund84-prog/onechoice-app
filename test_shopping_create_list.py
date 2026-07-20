# -*- coding: utf-8 -*-
"""Skapa lista — checkboxes + merge + history reopen."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import db
import pipeline


class _Session(dict):
    """dict that also supports attribute access like st.session_state."""

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
        to_buy = {
            "kött & fisk": ["kycklingfilé"],
            "frukt & grönt": ["gul lök", "tomat"],
            "skafferi": ["pasta"],
        }
        selected = {
            "kött & fisk": ["kycklingfilé"],
            "frukt & grönt": ["gul lök"],
        }
        db.merge_shopping_from_decision(uid, 9, selected, path=self.db_path)
        names = {r["name"] for r in db.list_shopping_items(uid, path=self.db_path)}
        self.assertEqual(names, {"kycklingfilé", "gul lök"})
        self.assertNotIn("pasta", names)
        self.assertNotIn("tomat", names)
        # Full to_buy still available for a later merge
        db.merge_shopping_from_decision(uid, 9, to_buy, path=self.db_path)
        names2 = {r["name"] for r in db.list_shopping_items(uid, path=self.db_path)}
        self.assertIn("pasta", names2)
        self.assertIn("tomat", names2)

    def test_accept_persists_rebuilt_shopping_via_context(self) -> None:
        """Regression: empty context.shopping must not block merge after rebuild."""
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
        # Simulate Cloud dropping shopping from context while execute rebuilds it
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
        orig_merge = db.merge_shopping_from_decision
        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(
                app_mod.db,
                "merge_shopping_from_decision",
                side_effect=lambda user_id, did, to_buy, path=None: orig_merge(
                    user_id, did, to_buy, path=self.db_path
                ),
            ):
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
        self.assertEqual(row["status"], "accepted")

        import app as app_mod

        ss = _Session(workout_phase="overview")
        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            app_mod._restore_decision_from_row(row)
            self.assertTrue(ss["accepted"])
            self.assertEqual(ss["page"], "execute")
            self.assertEqual(ss["current"]["suggestion"], r.suggestion)

    def test_i18n_has_skapa_lista(self) -> None:
        import app as app_mod

        self.assertEqual(app_mod.I18N["sv"]["list_create"], "Skapa lista")
        self.assertIn("Bocka", app_mod.I18N["sv"]["list_create_hint"])


class CreateListUiTests(unittest.TestCase):
    def test_execute_shows_skapa_lista(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if b.label and "Handla" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(bool(at.session_state["ui_error"]))
        labels = [b.label or "" for b in at.button]
        self.assertTrue(
            any("Skapa lista" in lab for lab in labels),
            labels,
        )
        self.assertTrue(
            any("Öppna listan" in lab for lab in labels),
            labels,
        )
        # Toggle buttons present for shopping items (✓ when checked)
        self.assertTrue(
            any((b.label or "").startswith("✓ ") for b in at.button),
            [b.label for b in at.button],
        )

    def test_skapa_lista_fills_persistent_list(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if b.label and "Handla" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        # Uncheck first ingredient toggle (✓ …)
        toggled = False
        for b in at.button:
            lab = b.label or ""
            if lab.startswith("✓ "):
                b.click().run()
                toggled = True
                break
        self.assertTrue(toggled)
        # After toggle, at least one item should be unchecked (no ✓)
        checks = at.session_state["shopping_checks"]
        self.assertTrue(isinstance(checks, dict) and any(v is False for v in checks.values()))
        created = False
        for b in at.button:
            if b.label and "Skapa lista" in b.label:
                b.click().run()
                created = True
                break
        self.assertTrue(created)
        self.assertIsNotNone(at.session_state["shopping_merged_for"])
        # Open list tab
        at.session_state["page"] = "lista"
        at.run()
        self.assertEqual(at.session_state["page"], "lista")
        cache = at.session_state["shopping_list_cache"]
        # Cache may be list of items or reloaded on page
        if isinstance(cache, list):
            self.assertGreaterEqual(len(cache), 1)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("Listan är tom", body)


if __name__ == "__main__":
    unittest.main()
