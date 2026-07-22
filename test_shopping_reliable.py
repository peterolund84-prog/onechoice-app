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
        db._SHOPPING_FORCE_SQLITE = False

    def tearDown(self) -> None:
        db._SHOPPING_FORCE_SQLITE = False
        self.tmp.cleanup()

    def test_handla_does_not_auto_merge(self) -> None:
        """Handla & laga opens execute — Skapa lista is what fills Lista."""
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
        orig_accept = pipeline.try_accept_decision

        def accept_local(did, route_log_id=None, db_path=None):  # noqa: ANN001
            return pipeline.accept_decision(did, db_path=self.db_path)

        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(pipeline, "try_accept_decision", side_effect=accept_local):
                with mock.patch.object(app_mod, "_load_shopping_items", return_value=[]):
                    app_mod._flush_db_accept()

        self.assertIsNone(ss.get("shopping_merged_for"))
        items = db.list_shopping_items(uid, path=self.db_path)
        self.assertEqual(len(items), 0)

    def test_skapa_lista_merges_selected(self) -> None:
        uid = self.user["id"]
        to_buy = {
            "kött & fisk": ["kycklingfilé", "bacon"],
            "frukt & grönt": ["gul lök"],
        }
        import app as app_mod

        ss = _Session(
            user_id=uid,
            shopping_list_cache=None,
            shopping_merged_for=None,
            shopping_list_error=None,
            shopping_checks={"1:0": True, "1:1": False, "1:2": True},
        )
        shop = {"to_buy": to_buy, "store": ""}
        orig_merge = db.merge_shopping_from_decision

        def merge_local(user_id, did, selected, path=None):  # noqa: ANN001
            return orig_merge(user_id, did, selected, path=self.db_path)

        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(
                app_mod.db, "merge_shopping_from_decision", side_effect=merge_local
            ):
                with mock.patch.object(app_mod, "_load_shopping_items", return_value=[]):
                    selected = app_mod._selected_to_buy_from_checks(shop, 1)
                    n = app_mod._merge_to_buy_into_list(selected, 1)

        self.assertEqual(n, 2)
        names = {r["name"] for r in db.list_shopping_items(uid, path=self.db_path)}
        self.assertEqual(names, {"kycklingfilé", "gul lök"})

    def test_missing_supabase_table_falls_back_to_sqlite(self) -> None:
        uid = self.user["id"]

        class _Boom(Exception):
            pass

        def boom(*_a, **_k):  # noqa: ANN001
            raise _Boom(
                '{"message":"Could not find the table \'public.shopping_items\' '
                'in the schema cache","code":"PGRST205"}'
            )

        with mock.patch.object(db, "_use_supabase", return_value=True):
            with mock.patch.object(db, "_tokens", return_value=("a", "r")):
                with mock.patch(
                    "supabase_store.list_shopping_items", side_effect=boom
                ):
                    rows = db.list_shopping_items(uid, path=self.db_path)
        self.assertEqual(rows, [])
        self.assertTrue(db._SHOPPING_FORCE_SQLITE)

        db.merge_shopping_from_decision(
            uid,
            None,
            {"frukt & grönt": ["banan"]},
            path=self.db_path,
        )
        names = {r["name"] for r in db.list_shopping_items(uid, path=self.db_path)}
        self.assertEqual(names, {"banan"})

    def test_nav_uses_buttons_not_href(self) -> None:
        import inspect

        import app as app_mod

        src = inspect.getsource(app_mod.nav)
        self.assertIn("st.button", src)
        self.assertIn('key=f"nav_', src)
        self.assertNotIn("href=", src)
        lang = inspect.getsource(app_mod.lang_bar)
        self.assertIn("st.pills", lang)
        self.assertNotIn("href=", lang)

    def test_ensure_shopping_user_creates_guest(self) -> None:
        import app as app_mod

        ss = _Session(
            user_id=None,
            guest_mode=False,
            access_token=None,
            language="sv",
        )
        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(app_mod.db, "init_db"):
                with mock.patch.object(app_mod.db, "clear_auth"):
                    with mock.patch.object(app_mod.db, "_ensure_sqlite_user"):
                        uid = app_mod._ensure_shopping_user()
        self.assertTrue(uid)
        self.assertEqual(ss["user_id"], uid)
        self.assertTrue(ss["guest_mode"])

    def test_merge_retries_via_sqlite_fallback(self) -> None:
        uid = self.user["id"]
        to_buy = {"frukt & grönt": ["tomat"]}
        import app as app_mod

        ss = _Session(
            user_id=uid,
            guest_mode=True,
            access_token=None,
            language="sv",
            shopping_list_cache=None,
            shopping_merged_for=None,
            shopping_list_error=None,
        )
        calls = {"n": 0}
        orig = db.merge_shopping_from_decision

        def flaky(user_id, did, selected, path=None):  # noqa: ANN001
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(
                    "Could not find the table 'public.shopping_items' in the schema cache PGRST205"
                )
            return orig(user_id, did, selected, path=self.db_path)

        with mock.patch.object(app_mod, "st", SimpleNamespace(session_state=ss)):
            with mock.patch.object(
                app_mod.db, "merge_shopping_from_decision", side_effect=flaky
            ):
                with mock.patch.object(app_mod, "_load_shopping_items", return_value=[]):
                    n = app_mod._merge_to_buy_into_list(to_buy, 42)
        self.assertEqual(n, 1)
        self.assertTrue(db._SHOPPING_FORCE_SQLITE)
        self.assertEqual(ss["shopping_merged_for"], 42)


class ReliableShoppingUiTests(unittest.TestCase):
    def test_handla_then_skapa_lista(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        uid = at.session_state["user_id"]
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self.assertFalse(bool(at.session_state["ui_error"]))
        # Must choose items — no auto-merge on Handla
        self.assertIsNone(at.session_state["shopping_merged_for"])
        labels = [b.label or "" for b in at.button]
        self.assertTrue(
            any("Lägg till i listan" in lab for lab in labels),
            labels,
        )
        self.assertFalse(any("Skapa lista" in lab for lab in labels), labels)
        self.assertFalse(any(lab == "Öppna listan" for lab in labels), labels)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("oc-shop-pick-marker", body)
        self.assertIn("Bocka i det du behöver", body)
        self.assertIn("Markera alla", " ".join(labels + [body]))
        # No duplicate ingredient section on execute
        self.assertNotIn("Ingredienser", body)
        self.assertIn("Gör så här", body)
        self.assertIn("per portion", body.lower())
        # Selection starts empty — CTA disabled at (0) or absent count
        self.assertTrue(
            any("Lägg till i listan (0)" in lab for lab in labels)
            or any(getattr(b, "disabled", False) for b in at.button if b.label and "Lägg till" in b.label),
            labels,
        )

        # Mark all then add
        for b in at.button:
            if b.label and "Markera alla" in b.label:
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        labels = [b.label or "" for b in at.button]
        self.assertTrue(
            any("Lägg till i listan" in lab and "(0)" not in lab for lab in labels),
            labels,
        )
        for b in at.button:
            if b.label and "Lägg till i listan" in b.label and "(0)" not in b.label:
                b.click().run()
                break
        # Stay on execute; CTA morphs to confirmation open-list button
        self.assertEqual(at.session_state["page"], "execute")
        self.assertIsNotNone(at.session_state["shopping_merged_for"])
        self.assertFalse(bool(at.session_state["shopping_list_error"]))
        labels2 = [b.label or "" for b in at.button]
        self.assertTrue(
            any("Öppna listan" in lab for lab in labels2),
            labels2,
        )
        cache = at.session_state["shopping_list_cache"]
        self.assertIsInstance(cache, list)
        self.assertGreaterEqual(len(cache), 1)
        self.assertEqual(at.session_state["user_id"], uid)

        # Bottom nav present + glass chrome marker
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any(lab.startswith("Lista") for lab in labels), labels)
        self.assertIn("Hem", labels)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn('data-oc-nav="glass"', body)

    def test_premium_shop_css_tokens(self) -> None:
        import inspect

        import app as app_mod

        src = inspect.getsource(app_mod.inject_css)
        self.assertIn("oc-shop-pick-marker", src)
        self.assertIn("oc-shop-row", src)
        self.assertIn("oc-shop-pick", src)
        self.assertIn("exec_sticky_cta", src)
        self.assertIn("oc-exec-lock", src)


if __name__ == "__main__":
    unittest.main()
