# -*- coding: utf-8 -*-
"""Lista tab — Klart lifecycle, badge = unchecked, add-row label collapsed."""

from __future__ import annotations

import html
import unittest
from contextlib import ExitStack
from unittest import mock

import db
from streamlit.testing.v1 import AppTest


class ListaKlartLifecycleTests(unittest.TestCase):
    UID = "uid-lista-klart"

    def setUp(self) -> None:
        db.init_db()
        db._SHOPPING_FORCE_SQLITE = True
        db._ensure_sqlite_user(self.UID)
        with db.get_conn() as conn:
            conn.execute("DELETE FROM shopping_items WHERE user_id = ?", (self.UID,))

    def tearDown(self) -> None:
        db._SHOPPING_FORCE_SQLITE = False

    def _boot_lista(self, *, seed: list[tuple[str, str]] | None = None) -> AppTest:
        if seed:
            for name, cat in seed:
                db.upsert_shopping_item(self.UID, name, cat)
        stack = ExitStack()
        stack.enter_context(mock.patch("supabase_client.is_configured", return_value=True))
        stack.enter_context(mock.patch("auth_cookie.read_auth_cookie", return_value={}))
        stack.enter_context(mock.patch("db._use_supabase", return_value=False))
        self.addCleanup(stack.close)
        at = AppTest.from_file("app.py", default_timeout=120)
        at.run()
        at.session_state["access_token"] = "lista-at"
        at.session_state["refresh_token"] = "lista-rt"
        at.session_state["user_id"] = self.UID
        at.session_state["guest_mode"] = False
        at.session_state["page"] = "lista"
        at.session_state["_auth_cookie_checked"] = True
        at.session_state["shopping_list_cache"] = None
        at.run()
        return at

    def _cache(self, at: AppTest) -> list:
        try:
            raw = at.session_state["shopping_list_cache"]
        except KeyError:
            return []
        return list(raw) if isinstance(raw, list) else []

    def _body(self, at: AppTest) -> str:
        return " ".join(str(m.value or "") for m in at.markdown)

    def _nav_lista_label(self, at: AppTest) -> str:
        nav_lista = next(b for b in at.button if getattr(b, "key", None) == "nav_lista")
        return nav_lista.label or ""

    def test_add_row_label_collapsed_and_columns(self) -> None:
        at = self._boot_lista()
        self.assertFalse(at.exception)
        body = self._body(at)
        self.assertIn("st-key-lista_add_row", body)
        add = next(i for i in at.text_input if getattr(i, "key", None) == "shop_add_input")
        self.assertEqual(add.label, "Lägg till...")
        self.assertTrue(str(add.placeholder).startswith("Lägg till"))
        plus = next(
            b
            for b in at.button
            if (b.label or "") in ("＋", "+")
            or getattr(b, "key", None) == "FormSubmitter:shop_add_form-＋"
        )
        self.assertIsNotNone(plus)

    def test_add_item_appears_in_category(self) -> None:
        at = self._boot_lista()
        add = next(i for i in at.text_input if getattr(i, "key", None) == "shop_add_input")
        add.input("spenat").run()
        # Form submit via + button
        plus = next(b for b in at.button if (b.label or "") in ("＋", "+"))
        plus.click().run()
        self.assertFalse(at.exception)

        cache = self._cache(at)
        names = {str(r["name"]) for r in cache}
        self.assertIn("spenat", names)
        hit = next(r for r in cache if r["name"] == "spenat")
        self.assertFalse(bool(hit["checked"]))
        self.assertEqual(hit["category"], "frukt & grönt")

        body = self._body(at)
        self.assertTrue(
            ("frukt & grönt" in body.lower()) or ("frukt &amp; grönt" in body.lower()),
            body,
        )
        self.assertNotIn("Klart (", body)
        self.assertIn("· 1", self._nav_lista_label(at))

    def test_check_moves_to_klart_uncheck_restores_badge(self) -> None:
        at = self._boot_lista(
            seed=[
                ("spenat", "frukt & grönt"),
                ("mjölk", "mejeri"),
                ("pasta", "skafferi"),
            ]
        )
        body = self._body(at)
        self.assertIn("Inköpslista", body)
        self.assertNotIn("Klart (", body)
        self.assertTrue(
            ("frukt & grönt" in body.lower()) or ("frukt &amp; grönt" in body.lower()),
            "expected aisle header in body",
        )

        cache = self._cache(at)
        self.assertEqual(sum(1 for r in cache if not bool(r["checked"])), 3)
        self.assertIn("· 3", self._nav_lista_label(at))

        boxes = list(at.checkbox)
        self.assertEqual(len(boxes), 3)
        first_label = boxes[0].label
        boxes[0].check().run()
        self.assertFalse(at.exception)

        body = self._body(at)
        self.assertIn("Klart (1)", body)
        cache = self._cache(at)
        checked = [r for r in cache if bool(r["checked"])]
        unchecked = [r for r in cache if not bool(r["checked"])]
        self.assertEqual(len(checked), 1)
        self.assertEqual(len(unchecked), 2)
        self.assertEqual(str(checked[0]["name"]), first_label)
        checked_cat = str(checked[0].get("category") or "")
        if not any(str(r.get("category") or "") == checked_cat for r in unchecked):
            self.assertNotIn(html.escape(checked_cat), body)
            self.assertNotIn(checked_cat, body)

        self.assertIn("· 2", self._nav_lista_label(at))

        done_box = next(c for c in at.checkbox if c.label == first_label)
        self.assertTrue(bool(done_box.value))
        done_box.uncheck().run()
        self.assertFalse(at.exception)

        body = self._body(at)
        self.assertNotIn("Klart (", body)
        cache = self._cache(at)
        self.assertEqual(sum(1 for r in cache if bool(r["checked"])), 0)
        self.assertEqual(sum(1 for r in cache if not bool(r["checked"])), 3)
        restored = next(c for c in at.checkbox if c.label == first_label)
        self.assertFalse(bool(restored.value))
        self.assertIn("· 3", self._nav_lista_label(at))

    def test_rensa_klara_deletes_checked(self) -> None:
        at = self._boot_lista(
            seed=[
                ("spenat", "frukt & grönt"),
                ("mjölk", "mejeri"),
            ]
        )
        boxes = list(at.checkbox)
        self.assertEqual(len(boxes), 2)
        first = boxes[0].label
        boxes[0].check().run()
        self.assertFalse(at.exception)
        body = self._body(at)
        self.assertIn("Klart (1)", body)
        self.assertIn("Rensa klara", body)

        clear_btn = next(b for b in at.button if b.label == "Rensa klara")
        clear_btn.click().run()
        self.assertFalse(at.exception)

        body = self._body(at)
        self.assertNotIn("Klart (", body)
        cache = self._cache(at)
        self.assertEqual(sum(1 for r in cache if bool(r["checked"])), 0)
        names = {str(r["name"]) for r in cache}
        self.assertNotIn(first, names)
        self.assertEqual(len(cache), 1)
        self.assertIn("· 1", self._nav_lista_label(at))


if __name__ == "__main__":
    unittest.main()
