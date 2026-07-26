# -*- coding: utf-8 -*-
"""Durable HTML/API sessions survive process restart (fresh store instance)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
from api.session_store import COOKIE_MAX_AGE, SessionStore


class SessionPersistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "sessions.db")
        db.init_db(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_restart_survival(self) -> None:
        store_a = SessionStore(path=self.path)
        sess = store_a.create(language="sv")
        sid = sess.sid
        sess.email = "peter@example.com"
        sess.guest_mode = False
        sess.access_token = "tok-access"
        sess.refresh_token = "tok-refresh"
        sess.current = {"suggestion": "Seinfeld", "domain": "movie"}
        sess.movie_mode = "trendar"
        store_a.save(sess)

        # Simulate process restart: brand-new store, same SQLite backend
        store_b = SessionStore(path=self.path)
        restored = store_b.get(sid)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.sid, sid)
        self.assertEqual(restored.user_id, sess.user_id)
        self.assertEqual(restored.email, "peter@example.com")
        self.assertFalse(restored.guest_mode)
        self.assertEqual(restored.access_token, "tok-access")
        self.assertEqual(restored.current.get("suggestion"), "Seinfeld")
        self.assertEqual(restored.movie_mode, "trendar")

    def test_expired_sessions_are_dropped(self) -> None:
        store = SessionStore(path=self.path)
        sess = store.create(language="sv")
        sid = sess.sid
        # Force expiry in the past
        db.api_session_upsert(
            sid,
            sess.to_payload(),
            max_age_sec=-10,
            path=self.path,
        )
        self.assertIsNone(store.get(sid))

    def test_delete_removes_row(self) -> None:
        store = SessionStore(path=self.path)
        sess = store.create()
        sid = sess.sid
        store.delete(sid)
        self.assertIsNone(SessionStore(path=self.path).get(sid))

    def test_cookie_max_age_is_thirty_days(self) -> None:
        self.assertEqual(COOKIE_MAX_AGE, 60 * 60 * 24 * 30)


if __name__ == "__main__":
    unittest.main()
