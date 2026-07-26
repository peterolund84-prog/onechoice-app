# -*- coding: utf-8 -*-
"""Server-side session keyed by HttpOnly cookie (replaces st.session_state).

Durable backend: SQLite ``api_sessions`` table (sid PK, session JSON,
updated_at, expires_at). Survives process restarts. Rows past
COOKIE_MAX_AGE are purged on read/write.
"""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


COOKIE_NAME = "oc_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


@dataclass
class Session:
    sid: str
    user_id: str
    guest_mode: bool = True
    language: str = "sv"
    email: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    current: dict[str, Any] | None = None
    decision_id: int | None = None
    accepted: bool = False
    reroll_index: int = 0
    last_question: str = ""
    last_domain_hint: str | None = None
    route_log_id: int | None = None
    force_route_domain: str | None = None
    food_meal_type: str | None = None
    clothes_occasion: str | None = None
    movie_format: str | None = None
    movie_mood: str | None = None
    movie_mode: str | None = "mood"
    force_chooser: bool = False
    updated_at: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()

    def public(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "guest_mode": self.guest_mode,
            "language": self.language,
            "email": self.email,
            "authenticated": bool(self.access_token) and not self.guest_mode,
            "accepted": self.accepted,
            "reroll_index": self.reroll_index,
            "decision_id": self.decision_id,
            "last_domain_hint": self.last_domain_hint,
            "force_chooser": self.force_chooser,
        }

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> Session:
        known = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in (data or {}).items() if k in known}
        if "sid" not in kwargs or "user_id" not in kwargs:
            raise ValueError("session payload missing sid/user_id")
        return cls(**kwargs)


class SessionStore:
    """Durable session store — SQLite-backed, same get/create/save/delete API."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._lock = threading.Lock()
        self._path = path
        self._purge_counter = 0

    def create(self, *, language: str = "sv") -> Session:
        import db

        sid = secrets.token_urlsafe(24)
        uid = str(uuid.uuid4())
        db.init_db(self._path)
        db.clear_auth()
        db.ensure_user(uid, language=language, path=self._path)
        sess = Session(sid=sid, user_id=uid, guest_mode=True, language=language)
        self.save(sess)
        return sess

    def get(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        import db

        with self._lock:
            raw = db.api_session_get(sid, path=self._path)
            if not raw:
                return None
            try:
                sess = Session.from_payload(raw)
            except Exception:
                db.api_session_delete(sid, path=self._path)
                return None
            sess.touch()
            # Refresh expiry window on access
            db.api_session_upsert(
                sess.sid,
                sess.to_payload(),
                max_age_sec=COOKIE_MAX_AGE,
                path=self._path,
            )
            return sess

    def save(self, sess: Session) -> None:
        import db

        sess.touch()
        with self._lock:
            db.api_session_upsert(
                sess.sid,
                sess.to_payload(),
                max_age_sec=COOKIE_MAX_AGE,
                path=self._path,
            )
            self._purge_counter += 1
            if self._purge_counter % 25 == 0:
                db.api_session_purge_expired(path=self._path)

    def delete(self, sid: str) -> None:
        import db

        with self._lock:
            db.api_session_delete(sid, path=self._path)


STORE = SessionStore()
