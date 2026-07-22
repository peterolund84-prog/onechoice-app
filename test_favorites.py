# -*- coding: utf-8 -*-
"""Mina favoriter — toggle, list, Laga ikväll, ranking interplay."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import food_local_packs as flp
import pipeline


class FavoritesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "fav.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)
        self.uid = self.user["id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_food_decision(self, title: str = "Kycklingwok med ris") -> dict:
        return db.create_decision(
            user_id=self.uid,
            domain="food",
            question="Vad ska jag äta?",
            suggestion=title,
            justification="Test",
            status="accepted",
            context={
                "meal_type": "middag",
                "recipe": {"active_minutes": 20, "steps": ["Stek"], "ingredients": ["kyckling"]},
            },
            execution_type="checklist",
            execution_label="Laga",
            path=self.db_path,
        )

    def test_favorite_toggle_persists(self) -> None:
        row = self._make_food_decision()
        rid = int(row["id"])
        self.assertFalse(bool(row.get("favorite")))
        updated = db.set_decision_favorite(rid, True, path=self.db_path)
        self.assertTrue(bool(updated.get("favorite")))
        listed = db.list_decisions(self.uid, favorite=True, path=self.db_path)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["suggestion"], row["suggestion"])
        cleared = db.set_decision_favorite(rid, False, path=self.db_path)
        self.assertFalse(bool(cleared.get("favorite")))
        self.assertEqual(
            db.list_decisions(self.uid, favorite=True, path=self.db_path), []
        )

    def test_list_favorite_suggestions(self) -> None:
        a = self._make_food_decision("Pasta pesto")
        b = self._make_food_decision("Tacos med kryddig färs")
        db.set_decision_favorite(int(a["id"]), True, path=self.db_path)
        db.set_decision_favorite(int(b["id"]), True, path=self.db_path)
        titles = db.list_favorite_suggestions(self.uid, domain="food", path=self.db_path)
        self.assertEqual(set(titles), {"Pasta pesto", "Tacos med kryddig färs"})

    def test_cook_tonight_creates_accepted_decision(self) -> None:
        src = self._make_food_decision("Ugnsbakad lax med potatis")
        db.set_decision_favorite(int(src["id"]), True, path=self.db_path)
        ctx = dict(src.get("context") or {})
        ctx["from_favorite"] = True
        new = db.create_decision(
            user_id=self.uid,
            domain="food",
            question="Laga ikväll",
            suggestion=src["suggestion"],
            justification=src["justification"],
            status="accepted",
            context=ctx,
            execution_type=src.get("execution_type"),
            execution_label=src.get("execution_label"),
            path=self.db_path,
        )
        self.assertEqual(new["status"], "accepted")
        self.assertEqual(new["suggestion"], src["suggestion"])
        self.assertTrue((new.get("context") or {}).get("from_favorite"))
        # Source remains the favorited row
        favs = db.list_decisions(self.uid, favorite=True, path=self.db_path)
        self.assertEqual(len(favs), 1)
        self.assertEqual(int(favs[0]["id"]), int(src["id"]))

    def test_favorited_dish_excluded_in_repeat_window(self) -> None:
        pack = flp.dinner_pack("sv")
        fav = pack[0]["suggestion"]
        ranked = pipeline._rank_candidates(
            pack,
            preferences=[],
            recent=[fav],
            explore=False,
            favorite_suggestions=[fav],
        )
        self.assertTrue(ranked)
        self.assertNotEqual(str(ranked[0]["suggestion"]).lower(), fav.lower())


class FavoritesAppTest(unittest.TestCase):
    def test_history_has_favorites_segment(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("db._use_supabase", return_value=False):
                    at = AppTest.from_file("app.py", default_timeout=120)
                    at.run()
                    at.session_state["access_token"] = "fav-at"
                    at.session_state["refresh_token"] = "fav-rt"
                    at.session_state["user_id"] = "uid-fav"
                    at.session_state["guest_mode"] = False
                    at.session_state["page"] = "history"
                    at.session_state["_auth_cookie_checked"] = True
                    at.run()
        self.assertFalse(at.exception)
        # Segment pills expose Favoriter / Historik labels
        labels = []
        for p in getattr(at, "pills", []) or []:
            opts = getattr(p, "options", None) or []
            labels.extend([str(o) for o in opts])
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertTrue(
            ("Favoriter" in labels) or ("Favoriter" in body) or any(
                "Favoriter" in str(getattr(b, "label", "") or "") for b in at.button
            ),
            f"labels={labels} body_snip={body[:200]}",
        )


if __name__ == "__main__":
    unittest.main()
