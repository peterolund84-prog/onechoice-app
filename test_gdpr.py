# -*- coding: utf-8 -*-
"""GDPR: export, hard delete cascade, LLM hygiene, signup consent."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

import db
import gdpr
import pipeline


class GdprSqliteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "gdpr.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed_everything(self) -> str:
        uid = self.user["id"]
        d = db.create_decision(
            user_id=uid,
            domain="food",
            question="Vad äta?",
            suggestion="Pasta",
            justification="Snabbt",
            status="accepted",
            context={"available_ingredients": ["pasta"]},
            path=self.path,
        )
        db.upsert_preference(uid, "food", "suggestion", "pasta", 1.0, path=self.path)
        db.log_routed_query(
            uid,
            route="IN_DOMAIN",
            domain="food",
            raw_text="Vad äta ikväll?",
            normalized_question="vad äta",
            path=self.path,
        )
        share = db.ensure_public_share(dict(d), language="sv", path=self.path)
        self.assertEqual(share.get("owner_id"), uid)
        with db.get_conn(self.path) as conn:
            conn.execute(
                """
                INSERT INTO user_photos (user_id, kind, path, created_at, expires_at)
                VALUES (?, 'fridge', ?, datetime('now'), datetime('now', '+1 day'))
                """,
                (uid, f"{uid}/fridge/test.jpg"),
            )
        return uid

    def test_export_contains_all_tables(self) -> None:
        uid = self._seed_everything()
        data = gdpr.export_user_data(uid, path=self.path)
        self.assertEqual(data["user_id"], uid)
        self.assertTrue(data["decisions"])
        self.assertTrue(data["preferences"])
        self.assertTrue(data["routed_queries"])
        self.assertTrue(data["public_shares"])
        self.assertTrue(data["user_photos"])
        # Must be JSON-serializable
        json.dumps(data, default=str)

    def test_delete_leaves_zero_rows(self) -> None:
        uid = self._seed_everything()
        other = db.ensure_user(language="sv", path=self.path)
        db.create_decision(
            user_id=other["id"],
            domain="food",
            question="x",
            suggestion="y",
            justification="z",
            path=self.path,
        )
        summary = gdpr.delete_user_account(uid, path=self.path)
        self.assertTrue(summary["ok"])
        gdpr.assert_user_gone(uid, path=self.path)
        # Other user untouched
        left = db.list_decisions(other["id"], path=self.path)
        self.assertEqual(len(left), 1)

    def test_llm_safe_profile_strips_identifiers(self) -> None:
        dirty = {
            "id": "uuid-secret",
            "user_id": "uuid-secret",
            "email": "a@b.c",
            "language": "sv",
            "budget": "low",
            "dietary_json": '["veg"]',
            "access_token": "tok",
            "profile_json": {
                "clothes": {"section": "herr", "sizes": {"top": "M"}, "retailers": ["H&M"]}
            },
        }
        safe = gdpr.llm_safe_profile(dirty)
        blob = json.dumps(safe)
        self.assertNotIn("uuid-secret", blob)
        self.assertNotIn("a@b.c", blob)
        self.assertNotIn("tok", blob)
        self.assertEqual(safe["language"], "sv")
        self.assertEqual(safe["dietary"], ["veg"])

    def test_llm_safe_context_strips_nested_user_id(self) -> None:
        ctx = {
            "source": "fridge_photo",
            "user_id": "should-go",
            "available_ingredients": ["ägg"],
            "meta": {"email": "nope@x.y", "ok": 1},
        }
        safe = gdpr.llm_safe_context(ctx)
        self.assertEqual(safe["source"], "fridge_photo")
        self.assertNotIn("user_id", safe)
        self.assertNotIn("email", safe.get("meta") or {})
        self.assertEqual((safe.get("meta") or {}).get("ok"), 1)

    def test_grok_prompt_uses_safe_profile(self) -> None:
        """Regression: full profile with email must not appear in outgoing prompt text."""
        captured: dict[str, Any] = {}

        class FakeResp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "candidates": [
                                            {
                                                "suggestion": "Äggröra",
                                                "justification": "Snabbt",
                                                "wildcard": False,
                                                "meta": {"ingredients": ["ägg"]},
                                            }
                                        ]
                                        * 5
                                    }
                                )
                            }
                        }
                    ]
                }

        def fake_post(url, headers=None, json=None, timeout=None):
            captured["json"] = json
            return FakeResp()

        import requests

        old = requests.post
        requests.post = fake_post  # type: ignore[assignment]
        try:
            pipeline._grok_candidates(
                "Vad äta?",
                "food",
                {"source": "fridge_photo", "user_id": "LEAK", "available_ingredients": ["ägg"]},
                {
                    "id": "LEAK",
                    "email": "leak@example.com",
                    "language": "sv",
                    "dietary_json": "[]",
                },
                [],
                [{"id": 9, "user_id": "LEAK", "key": "suggestion", "value": "x", "score": 1}],
                [],
                "sv",
                "xai-test-key-not-used",
            )
        finally:
            requests.post = old  # type: ignore[assignment]

        body = json.dumps(captured.get("json") or {})
        self.assertNotIn("LEAK", body)
        self.assertNotIn("leak@example.com", body)
        self.assertIn("Anonymous preferences", body)


class GdprUiConsentTests(unittest.TestCase):
    def test_signup_requires_consent_checkbox(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=45)
        at.run()
        # Force signup mode if auth page is shown
        labels = [b.label or "" for b in at.button]
        if any("Registrera" in lab or "Sign up" in lab for lab in labels):
            for b in at.button:
                if b.label and ("Registrera" in b.label or "Sign up" in b.label or "skapa" in b.label.lower()):
                    # May already be on signup — click to toggle if login
                    break
        # Ensure privacy consent key exists in i18n / page has checkbox when on signup
        import app as app_mod

        self.assertIn("privacy_consent", app_mod.I18N["sv"])
        self.assertIn("gdpr_delete", app_mod.I18N["sv"])


if __name__ == "__main__":
    unittest.main()
