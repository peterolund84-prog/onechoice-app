# -*- coding: utf-8 -*-
"""Persistent shopping list — merge, toggle, GDPR cascade."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import gdpr
import pipeline
import shopping_items as si


class PersistentShoppingListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "shop.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _dinner_shop(self, protein: str) -> dict:
        return {
            "store": "ICA",
            "to_buy": {
                "kött & fisk": [protein],
                "frukt & grönt": ["gul lök", "tomat"],
                "skafferi": ["pasta"],
            },
            "assumed_at_home": ["salt", "peppar", "olja"],
        }

    def test_two_decisions_merge_without_duplicates(self) -> None:
        uid = self.user["id"]
        shop1 = self._dinner_shop("kycklingfilé")
        shop2 = {
            "store": "ICA",
            "to_buy": {
                "kött & fisk": ["nötfärs"],
                "frukt & grönt": ["gul lök", "morot"],
                "mejeri": ["grädde"],
            },
            "assumed_at_home": ["salt"],
        }
        db.merge_shopping_from_decision(uid, 1, shop1["to_buy"], path=self.db_path)
        db.merge_shopping_from_decision(uid, 2, shop2["to_buy"], path=self.db_path)

        items = db.list_shopping_items(uid, path=self.db_path)
        names = {r["name"] for r in items}
        self.assertEqual(
            names,
            {"gul lök", "grädde", "kycklingfilé", "morot", "nötfärs", "pasta", "tomat"},
        )
        self.assertEqual(len([r for r in items if r["name"] == "gul lök"]), 1)

        cats = {r["name"]: r["category"] for r in items}
        self.assertEqual(cats["kycklingfilé"], "kött & fisk")
        self.assertEqual(cats["gul lök"], "frukt & grönt")
        self.assertEqual(cats["grädde"], "mejeri")
        self.assertEqual(cats["pasta"], "skafferi")

    def test_toggle_persists_across_reload(self) -> None:
        uid = self.user["id"]
        row = db.upsert_shopping_item(
            uid, "mjölk", "mejeri", path=self.db_path
        )
        self.assertIsNotNone(row)
        iid = int(row["id"])  # type: ignore[index]
        db.toggle_shopping_item(uid, iid, True, path=self.db_path)

        reloaded = db.list_shopping_items(uid, path=self.db_path)
        hit = next(r for r in reloaded if int(r["id"]) == iid)
        self.assertTrue(hit["checked"])
        self.assertTrue(hit.get("checked_at"))

    def test_user_deletion_removes_all_items(self) -> None:
        uid = self.user["id"]
        other = db.ensure_user(language="sv", path=self.db_path)
        db.upsert_shopping_item(uid, "ägg", "mejeri", path=self.db_path)
        db.upsert_shopping_item(other["id"], "bröd", "skafferi", path=self.db_path)

        summary = gdpr.delete_user_account(uid, path=self.db_path)
        self.assertTrue(summary["ok"])
        gdpr.assert_user_gone(uid, path=self.db_path)

        left = db.list_shopping_items(other["id"], path=self.db_path)
        self.assertEqual(len(left), 1)
        self.assertEqual(left[0]["name"], "bröd")

    def test_manual_add_dedupes_open_row(self) -> None:
        uid = self.user["id"]
        db.add_manual_shopping_item(uid, "Gul lök", path=self.db_path)
        db.add_manual_shopping_item(uid, "gul lök", path=self.db_path)
        items = db.list_shopping_items(uid, path=self.db_path)
        self.assertEqual(len(items), 1)

    def test_categorize_keyword_map(self) -> None:
        self.assertEqual(si.categorize_item("mjölk"), "mejeri")
        self.assertEqual(si.categorize_item("kycklingfilé"), "kött & fisk")

    def test_accept_flow_merges_from_pipeline(self) -> None:
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
        ctx = r.context or {}
        shop = ctx.get("shopping") or {}
        to_buy = shop.get("to_buy") or {}
        self.assertTrue(to_buy)
        db.merge_shopping_from_decision(
            uid, r.decision_id, to_buy, path=self.db_path
        )
        pipeline.accept_decision(r.decision_id, db_path=self.db_path)
        items = db.list_shopping_items(uid, path=self.db_path)
        self.assertGreaterEqual(len(items), 2)


if __name__ == "__main__":
    unittest.main()
