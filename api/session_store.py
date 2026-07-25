# -*- coding: utf-8 -*-
"""Server-side session keyed by HttpOnly cookie (replaces st.session_state)."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
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


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, Session] = {}

    def create(self, *, language: str = "sv") -> Session:
        import db

        sid = secrets.token_urlsafe(24)
        uid = str(uuid.uuid4())
        db.init_db()
        db.clear_auth()
        db.ensure_user(uid, language=language)
        sess = Session(sid=sid, user_id=uid, guest_mode=True, language=language)
        with self._lock:
            self._sessions[sid] = sess
        return sess

    def get(self, sid: str | None) -> Session | None:
        if not sid:
            return None
        with self._lock:
            sess = self._sessions.get(sid)
            if sess:
                sess.touch()
            return sess

    def save(self, sess: Session) -> None:
        sess.touch()
        with self._lock:
            self._sessions[sess.sid] = sess

    def delete(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)


STORE = SessionStore()
