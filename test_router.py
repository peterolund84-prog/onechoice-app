# -*- coding: utf-8 -*-
"""Tests for free-text router + query logging."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import pipeline
import router


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "test.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_in_domain_food_variants(self) -> None:
        for q in ("vad ska jag käka?", "middagstips?", "hungrig, hjälp"):
            r = router.route_question(q, language="sv")
            self.assertEqual(r.route, "IN_DOMAIN", q)
            self.assertEqual(r.domain, "food", q)

    def test_high_stakes_by_consequence(self) -> None:
        r = router.route_question(
            "ska jag äta lunch med chefen innan jag säger upp mig?",
            language="sv",
        )
        self.assertEqual(r.route, "HIGH_STAKES")
        self.assertIsNone(r.normalized_question)

    def test_near_domain_gift(self) -> None:
        r = router.route_question("vad ska jag ge farsan i julklapp", language="sv")
        self.assertEqual(r.route, "NEAR_DOMAIN")
        self.assertEqual(r.category_guess, "presenter")
        self.assertTrue(r.normalized_question)
        self.assertNotIn("farsan", (r.normalized_question or "").lower())

    def test_ambiguous(self) -> None:
        r = router.route_question("hjälp mig", language="sv")
        self.assertEqual(r.route, "AMBIGUOUS")

    def test_not_a_decision(self) -> None:
        r = router.route_question("vad är huvudstaden i frankrike?", language="sv")
        self.assertEqual(r.route, "NOT_A_DECISION")

    def test_max_input_enforced(self) -> None:
        long_q = "a" * 250
        r = router.route_question(long_q, language="sv")
        self.assertLessEqual(len(r.raw_text), router.MAX_INPUT_CHARS)

    def test_handle_free_text_in_domain_logs(self) -> None:
        result = pipeline.handle_free_text(
            self.user["id"],
            "vad ska jag äta till lunch?",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.domain, "food")
        self.assertEqual(result.route, "IN_DOMAIN")
        self.assertIsNotNone(result.route_log_id)
        with db.get_conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM routed_queries WHERE id = ?",
                (result.route_log_id,),
            ).fetchone()
        self.assertEqual(row["route"], "IN_DOMAIN")
        self.assertEqual(row["decision_shown"], 1)
        self.assertTrue(row["raw_text"])

    def test_high_stakes_privacy_log(self) -> None:
        result = pipeline.handle_free_text(
            self.user["id"],
            "ska jag säga upp mig?",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(result.refused)
        self.assertIn("vardagsbesluten", result.refusal_message or "")
        with db.get_conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM routed_queries WHERE id = ?",
                (result.route_log_id,),
            ).fetchone()
        self.assertEqual(row["route"], "HIGH_STAKES")
        self.assertIsNone(row["raw_text"])
        self.assertIsNone(row["category_guess"])
        self.assertIsNone(row["normalized_question"])
        self.assertIsNone(row["domain"])

    def test_near_domain_skips_feasibility(self) -> None:
        result = pipeline.handle_free_text(
            self.user["id"],
            "vilken väggfärg ska jag välja?",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.domain, "other")
        self.assertEqual(result.route, "NEAR_DOMAIN")
        self.assertTrue((result.context or {}).get("skip_feasibility"))

    def test_ambiguous_needs_pick(self) -> None:
        result = pipeline.handle_free_text(
            self.user["id"],
            "vet inte",
            language="sv",
            db_path=self.db_path,
        )
        self.assertTrue(result.needs_domain_pick)
        self.assertFalse(result.ok)

    def test_not_a_decision_message(self) -> None:
        result = pipeline.handle_free_text(
            self.user["id"],
            "förklara hur bitcoin fungerar",
            language="sv",
            db_path=self.db_path,
        )
        self.assertEqual(result.route, "NOT_A_DECISION")
        self.assertIn("beslut", result.ui_message or "")

    def test_accept_updates_routed_query(self) -> None:
        result = pipeline.handle_free_text(
            self.user["id"],
            "vad ska jag äta?",
            language="sv",
            db_path=self.db_path,
        )
        pipeline.accept_decision(
            result.decision_id,
            db_path=self.db_path,
            route_log_id=result.route_log_id,
        )
        with db.get_conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT accepted FROM routed_queries WHERE id = ?",
                (result.route_log_id,),
            ).fetchone()
        self.assertEqual(row["accepted"], 1)

    def test_near_domain_demand_view(self) -> None:
        pipeline.handle_free_text(
            self.user["id"],
            "julklapp till förälder",
            language="sv",
            db_path=self.db_path,
        )
        rows = db.near_domain_demand(path=self.db_path)
        self.assertTrue(any(r.get("category_guess") == "presenter" for r in rows))

    def test_purge_raw_text_helper(self) -> None:
        # Insert old row manually
        with db.get_conn(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO routed_queries
                (user_id, created_at, raw_text, route, domain, confidence,
                 category_guess, normalized_question, decision_shown, accepted)
                VALUES (?, datetime('now', '-100 days'), 'secret', 'IN_DOMAIN',
                        'food', 0.9, 'food', 'matfråga', 1, NULL)
                """,
                (self.user["id"],),
            )
        n = db.purge_expired_raw_text(days=90, path=self.db_path)
        self.assertGreaterEqual(n, 1)
        with db.get_conn(self.db_path) as conn:
            row = conn.execute(
                "SELECT raw_text, normalized_question FROM routed_queries "
                "WHERE normalized_question = 'matfråga'"
            ).fetchone()
        self.assertIsNone(row["raw_text"])
        self.assertEqual(row["normalized_question"], "matfråga")


if __name__ == "__main__":
    unittest.main()
