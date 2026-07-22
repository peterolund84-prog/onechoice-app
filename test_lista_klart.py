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
        # Fresh list for this user
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

    def test_check_moves_to_klart_uncheck_restores_badge(self) -> None:
        at = self._boot_lista(
            seed=[
                ("spenat", "frukt & grönt"),
                ("mjölk", "mejeri"),
                ("pasta", "skafferi"),
            ]
        )
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Inköpslista", body)
        self.assertNotIn("Klart (", body)
        self.assertTrue(
            ("frukt & grönt" in body.lower()) or ("frukt &amp; grönt" in body.lower()),
            "expected aisle header in body",
        )

        cache = self._cache(at)
        self.assertEqual(sum(1 for r in cache if not bool(r["checked"])), 3)

        nav_lista = next(b for b in at.button if getattr(b, "key", None) == "nav_lista")
        self.assertIn("· 3", nav_lista.label or "")

        boxes = list(at.checkbox)
        self.assertEqual(len(boxes), 3)
        first_label = boxes[0].label
        boxes[0].check().run()
        self.assertFalse(at.exception)

        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Klart (1)", body)
        cache = self._cache(at)
        checked = [r for r in cache if bool(r["checked"])]
        unchecked = [r for r in cache if not bool(r["checked"])]
        self.assertEqual(len(checked), 1)
        self.assertEqual(len(unchecked), 2)
        self.assertEqual(str(checked[0]["name"]), first_label)
        checked_cat = str(checked[0].get("category") or "")
        if not any(str(r.get("category") or "") == checked_cat for r in unchecked):
            # Header hidden when category has zero unchecked items
            self.assertNotIn(html.escape(checked_cat), body)
            self.assertNotIn(checked_cat, body)

        nav_lista = next(b for b in at.button if getattr(b, "key", None) == "nav_lista")
        self.assertIn("· 2", nav_lista.label or "")

        done_box = next(c for c in at.checkbox if c.label == first_label)
        self.assertTrue(bool(done_box.value))
        done_box.uncheck().run()
        self.assertFalse(at.exception)

        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("Klart (", body)
        cache = self._cache(at)
        self.assertEqual(sum(1 for r in cache if bool(r["checked"])), 0)
        self.assertEqual(sum(1 for r in cache if not bool(r["checked"])), 3)
        restored = next(c for c in at.checkbox if c.label == first_label)
        self.assertFalse(bool(restored.value))

        nav_lista = next(b for b in at.button if getattr(b, "key", None) == "nav_lista")
        self.assertIn("· 3", nav_lista.label or "")

    def test_add_input_label_collapsed_and_title_utility_size(self) -> None:
        at = self._boot_lista()
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("st-key-lista_page_title", body)
        self.assertIn("font-size: 24px", body)
        self.assertIn("st-key-lista_add_row", body)
        add = next(i for i in at.text_input if getattr(i, "key", None) == "shop_add_input")
        self.assertEqual(add.label, " ")
        self.assertTrue(str(add.placeholder).startswith("Lägg till vara"))


if __name__ == "__main__":
    unittest.main()
