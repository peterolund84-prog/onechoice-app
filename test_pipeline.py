# -*- coding: utf-8 -*-
"""Unit tests for OneChoice db + decision pipeline."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import pipeline


class OneChoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "test.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_schema_and_user(self) -> None:
        u = db.ensure_user(self.user["id"], path=self.db_path)
        self.assertEqual(u["id"], self.user["id"])
        self.assertEqual(u["language"], "sv")

    def test_refuse_high_stakes(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Ska jag säga upp mig från jobbet?",
            db_path=self.db_path,
        )
        self.assertTrue(r.refused)
        self.assertFalse(r.ok)
        self.assertIn("everyday decisions", r.refusal_message or "")

    def test_one_decision_food(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta till lunch?",
            db_path=self.db_path,
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.domain, "food")
        self.assertTrue(r.suggestion)
        self.assertTrue(r.justification)
        self.assertIsNotNone(r.decision_id)
        self.assertFalse(r.locked)
        # Never returns a list — single suggestion string
        self.assertIsInstance(r.suggestion, str)
        self.assertNotIn("\n-", r.suggestion)

    def test_domain_hint_buttons(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "",
            domain_hint="workout",
            db_path=self.db_path,
        )
        self.assertTrue(r.ok)
        self.assertEqual(r.domain, "workout")

    def test_reroll_negative_signal_and_lock(self) -> None:
        first = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            db_path=self.db_path,
        )
        self.assertEqual(first.reroll_index, 0)
        second = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            reroll=True,
            reroll_index=1,
            previous_decision_id=first.decision_id,
            db_path=self.db_path,
        )
        self.assertTrue(second.ok)
        # previous marked rejected
        rows = db.list_decisions(self.user["id"], path=self.db_path)
        prev = next(x for x in rows if x["id"] == first.decision_id)
        self.assertEqual(prev["status"], "rejected")

        locked = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            reroll=True,
            reroll_index=3,
            previous_decision_id=second.decision_id,
            db_path=self.db_path,
        )
        self.assertTrue(locked.locked)
        self.assertEqual(locked.reroll_index, 3)

    def test_accept_updates_preferences(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag ha på mig?",
            domain_hint="clothes",
            db_path=self.db_path,
        )
        pipeline.accept_decision(r.decision_id, db_path=self.db_path)
        prefs = db.get_preferences(self.user["id"], "clothes", path=self.db_path)
        self.assertTrue(any(p["score"] > 0 for p in prefs))

    def test_execution_attached(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(r.execution_type in ("recipe", "map"))
        self.assertTrue(r.execution_url)

    def test_swedish_output_not_mixed(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(r.ok)
        # Suggestion + justification should be Swedish phrasing (no English sentence starters)
        eng_markers = (
            "watch a ", "a warm ", "classic burger", "creamy tomato", "dark jeans",
            "you haven’t", "you haven't", "perfect for lunch", "order it",
        )
        blob = f"{r.suggestion} {r.justification}".lower()
        for m in eng_markers:
            self.assertNotIn(m, blob, f"found English marker {m!r} in {blob!r}")
        # Swedish justification should contain Swedish characters or common words
        self.assertTrue(
            any(w in r.justification.lower() for w in ("och", "på", "att", "en", "det", "du", "för", "utan", "med")),
            r.justification,
        )

    def test_english_output_when_en(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "What should I eat?",
            language="en",
            domain_hint="food",
            db_path=self.db_path,
        )
        self.assertTrue(r.ok)
        # Should not be Swedish justification
        self.assertNotRegex(r.justification.lower(), r"\b(mättande|krångel|klart på)\b")



if __name__ == "__main__":
    unittest.main()
