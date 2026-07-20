# -*- coding: utf-8 -*-
"""Share copy, public snapshots, and landing attribution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import share_domain as sd


class ShareCopyTests(unittest.TestCase):
    def test_food_frames_app_as_decider(self) -> None:
        msg = sd.share_message(
            domain="food", suggestion="Kycklingwok med ris", language="sv"
        )
        self.assertIn("OneChoice har bestämt", msg)
        self.assertIn("Kycklingwok med ris", msg)
        self.assertTrue(msg.startswith("🍽"))

    def test_workout_frames_app_as_decider(self) -> None:
        msg = sd.share_message(
            domain="workout", suggestion="30 min helkroppsstyrka", language="sv"
        )
        self.assertIn("Dagens pass enligt OneChoice", msg)
        self.assertIn("30 min helkroppsstyrka", msg)
        self.assertTrue(msg.startswith("💪"))

    def test_clothes_movie_weekend_same_pattern(self) -> None:
        for domain, emoji in (
            ("clothes", "👕"),
            ("movie", "🎬"),
            ("weekend", "🌿"),
        ):
            msg = sd.share_message(domain=domain, suggestion="X", language="sv")
            self.assertIn("OneChoice har bestämt", msg)
            self.assertTrue(msg.startswith(emoji))

    def test_share_url_has_ref_and_decision_id(self) -> None:
        path = sd.share_path(token="abc123", decision_id=42)
        self.assertIn("share=abc123", path)
        self.assertIn("ref=share", path)
        self.assertIn("decision_id=42", path)


class PublicShareDbTests(unittest.TestCase):
    def test_ensure_and_open_logs_attribution(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        decision = db.create_decision(
            user_id=user["id"],
            domain="food",
            question="Vad äter vi?",
            suggestion="Tacos",
            justification="Snabb vardag",
            status="accepted",
            context={
                "shopping": {"store": "", "to_buy": {"Kött": ["köttfärs"]}},
                "recipe": {"active_minutes": 20, "steps": ["Stek"]},
            },
            path=path,
        )
        share = db.ensure_public_share(
            {
                "decision_id": decision["id"],
                "domain": "food",
                "suggestion": "Tacos",
                "justification": "Snabb vardag",
                "context": decision.get("context") or {},
            },
            language="sv",
            path=path,
        )
        self.assertTrue(share["token"])
        loaded = db.get_public_share(share["token"], path=path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["payload"]["suggestion"], "Tacos")
        self.assertIn("shopping", loaded["payload"]["context"])

        db.log_share_open(
            share["token"], decision_id=decision["id"], ref="share", path=path
        )
        self.assertEqual(db.count_share_opens(share["token"], path=path), 1)
        again = db.ensure_public_share(
            {
                "decision_id": decision["id"],
                "domain": "food",
                "suggestion": "Tacos",
                "justification": "Snabb vardag",
                "context": {},
            },
            language="sv",
            path=path,
        )
        self.assertEqual(again["token"], share["token"])
        tmp.cleanup()


class ShareLandingUiTests(unittest.TestCase):
    def test_shared_page_renders_cta(self) -> None:
        from streamlit.testing.v1 import AppTest

        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "share.db")
        db.init_db(path)
        # Patch default DB so AppTest guest mode hits our temp file
        orig = db.DB_PATH
        db.DB_PATH = Path(path)
        try:
            share = db.ensure_public_share(
                {
                    "decision_id": 7,
                    "domain": "workout",
                    "suggestion": "30 min helkroppsstyrka",
                    "justification": "Ett pass, klart.",
                    "execution_type": "workout",
                    "context": {
                        "workout": {
                            "title": "Helkropp",
                            "blocks": [
                                {
                                    "name": "Squats",
                                    "type": "reps",
                                    "sets": 3,
                                    "reps": 10,
                                    "rest_seconds": 30,
                                }
                            ],
                        },
                        "execution_detail": "30 min · 1 block",
                    },
                },
                language="sv",
                path=path,
            )
            at = AppTest.from_file("app.py", default_timeout=45)
            at.query_params["share"] = share["token"]
            at.query_params["ref"] = "share"
            at.query_params["decision_id"] = "7"
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["page"], "shared")
            body = " ".join(str(m.value or "") for m in at.markdown)
            self.assertIn("30 min helkroppsstyrka", body)
            labels = [b.label or "" for b in at.button]
            self.assertTrue(
                any("OneChoice" in lab for lab in labels),
                labels,
            )
            self.assertGreaterEqual(db.count_share_opens(share["token"], path=path), 1)
        finally:
            db.DB_PATH = orig
            tmp.cleanup()

    def test_lock_card_exposes_share_after_accept(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.query_params["domain"] = "workout"
        at.run()
        for b in at.button:
            if "Starta" in (b.label or ""):
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        # Back to locked result
        for b in at.button:
            if (b.label or "") in ("Tillbaka", "Back"):
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "result")
        self.assertTrue(at.session_state["accepted"])
        cur = at.session_state["current"] or {}
        did = cur.get("decision_id") or at.session_state["decision_id"]
        self.assertIsNotNone(did)
        # Building a share snapshot must succeed for the locked decision
        share = db.ensure_public_share(dict(cur), language="sv")
        self.assertTrue(share.get("token"))
        self.assertIn("ref=share", sd.share_path(token=share["token"], decision_id=did))


if __name__ == "__main__":
    unittest.main()
