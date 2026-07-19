# -*- coding: utf-8 -*-
"""
Data access for OneChoice.

- SQLite locally / in unit tests (default)
- Supabase when configured + auth tokens are set via set_auth()
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DB_PATH = Path(__file__).resolve().parent / "onechoice.db"
# Streamlit Cloud mounts the repo read-only under /mount/src — use /tmp there
if Path("/mount/src").exists():
    DB_PATH = Path("/tmp/onechoice.db")

DOMAINS = ("food", "clothes", "movie", "workout", "weekend")
DECISION_STATUSES = ("shown", "rejected", "accepted", "locked")

# Auth context for Supabase RLS (access_token, refresh_token)
_AUTH: tuple[str, str] | None = None


def set_auth(access_token: str | None, refresh_token: str | None = None) -> None:
    global _AUTH
    if access_token and refresh_token:
        _AUTH = (access_token, refresh_token)
    else:
        _AUTH = None


def clear_auth() -> None:
    set_auth(None, None)


def _use_supabase(path: Path | str | None = None) -> bool:
    if path is not None:
        return False  # explicit sqlite path → tests / local file
    if _AUTH is None:
        return False
    try:
        import supabase_client as sb

        return sb.is_configured()
    except Exception:
        return False


def _tokens() -> tuple[str, str]:
    assert _AUTH is not None
    return _AUTH


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _connect(path: Path | str | None = None) -> sqlite3.Connection:
    db = Path(path) if path else DB_PATH
    conn = sqlite3.connect(str(db), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | str | None = None) -> None:
    with get_conn(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'sv',
                is_pro INTEGER NOT NULL DEFAULT 0,
                budget TEXT,
                dietary_json TEXT NOT NULL DEFAULT '[]',
                location TEXT,
                wardrobe_json TEXT NOT NULL DEFAULT '[]',
                profile_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                question TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                justification TEXT NOT NULL,
                execution_type TEXT,
                execution_label TEXT,
                execution_url TEXT,
                status TEXT NOT NULL,
                reroll_index INTEGER NOT NULL DEFAULT 0,
                context_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_decisions_user_domain
                ON decisions(user_id, domain, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_decisions_user_status
                ON decisions(user_id, status, created_at DESC);

            CREATE TABLE IF NOT EXISTS preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                domain TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                score REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, domain, key, value),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_preferences_user_domain
                ON preferences(user_id, domain);
            """
        )
        # Migrate older DBs missing profile_json
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "profile_json" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN profile_json TEXT NOT NULL DEFAULT '{}'"
            )


def ensure_user(
    user_id: str | None = None,
    *,
    language: str = "sv",
    path: Path | str | None = None,
    email: str | None = None,
) -> dict[str, Any]:
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        uid = user_id or ""
        if not uid:
            raise ValueError("user_id required for Supabase")
        return store.ensure_profile(uid, at, rt, language=language, email=email)

    uid = user_id or str(uuid.uuid4())
    with get_conn(path) as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if row:
            return dict(row)
        conn.execute(
            """
            INSERT INTO users (id, created_at, language)
            VALUES (?, ?, ?)
            """,
            (uid, utc_now(), language),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        return dict(row)


def update_user(user_id: str, **fields: Any) -> dict[str, Any]:
    path = fields.pop("path", None)
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.update_profile(user_id, at, rt, **fields)

    allowed = {
        "language",
        "is_pro",
        "budget",
        "dietary_json",
        "location",
        "wardrobe_json",
        "profile_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return ensure_user(user_id, path=path)

    # Serialize list/dict fields
    for key in ("dietary_json", "wardrobe_json", "profile_json"):
        if key in updates and not isinstance(updates[key], str):
            updates[key] = json.dumps(updates[key], ensure_ascii=False)

    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [user_id]
    with get_conn(path) as conn:
        conn.execute(f"UPDATE users SET {cols} WHERE id = ?", vals)
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else ensure_user(user_id, path=path)


def create_decision(
    *,
    user_id: str,
    domain: str,
    question: str,
    suggestion: str,
    justification: str,
    status: str = "shown",
    reroll_index: int = 0,
    context: dict[str, Any] | None = None,
    execution_type: str | None = None,
    execution_label: str | None = None,
    execution_url: str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    if status not in DECISION_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.create_decision(
            user_id=user_id,
            access_token=at,
            refresh_token=rt,
            domain=domain,
            question=question,
            suggestion=suggestion,
            justification=justification,
            status=status,
            reroll_index=reroll_index,
            context=context,
            execution_type=execution_type,
            execution_label=execution_label,
            execution_url=execution_url,
        )
    ctx = json.dumps(context or {}, ensure_ascii=False)
    with get_conn(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO decisions (
                user_id, domain, question, suggestion, justification,
                execution_type, execution_label, execution_url,
                status, reroll_index, context_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                domain,
                question,
                suggestion,
                justification,
                execution_type,
                execution_label,
                execution_url,
                status,
                reroll_index,
                ctx,
                utc_now(),
            ),
        )
        row = conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _decision_row(row)


def set_decision_status(
    decision_id: int,
    status: str,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    if status not in DECISION_STATUSES:
        raise ValueError(f"invalid status: {status}")
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.set_decision_status(decision_id, status, at, rt)
    with get_conn(path) as conn:
        conn.execute(
            "UPDATE decisions SET status = ? WHERE id = ?",
            (status, decision_id),
        )
        row = conn.execute(
            "SELECT * FROM decisions WHERE id = ?", (decision_id,)
        ).fetchone()
        if not row:
            raise KeyError(f"decision {decision_id} not found")
        return _decision_row(row)


def list_decisions(
    user_id: str,
    *,
    domain: str | None = None,
    status: str | None = None,
    limit: int = 50,
    path: Path | str | None = None,
) -> list[dict[str, Any]]:
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.list_decisions(
            user_id, at, rt, domain=domain, status=status, limit=limit
        )
    sql = "SELECT * FROM decisions WHERE user_id = ?"
    params: list[Any] = [user_id]
    if domain:
        sql += " AND domain = ?"
        params.append(domain)
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with get_conn(path) as conn:
        rows = conn.execute(sql, params).fetchall()
        return [_decision_row(r) for r in rows]


def recent_suggestions(
    user_id: str,
    domain: str,
    *,
    days: int = 14,
    path: Path | str | None = None,
) -> list[str]:
    """Suggestions accepted/locked/shown recently — used as repetition guard."""
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.recent_suggestions(user_id, domain, at, rt, days=days)
    with get_conn(path) as conn:
        rows = conn.execute(
            """
            SELECT suggestion FROM decisions
            WHERE user_id = ? AND domain = ?
              AND status IN ('accepted', 'locked', 'shown', 'rejected')
              AND datetime(created_at) >= datetime('now', ?)
            ORDER BY created_at DESC
            """,
            (user_id, domain, f"-{int(days)} days"),
        ).fetchall()
        return [r["suggestion"] for r in rows]


def upsert_preference(
    user_id: str,
    domain: str,
    key: str,
    value: str,
    delta: float,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.upsert_preference(
            user_id, domain, key, value, delta, at, rt
        )
    now = utc_now()
    with get_conn(path) as conn:
        conn.execute(
            """
            INSERT INTO preferences (user_id, domain, key, value, score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, domain, key, value) DO UPDATE SET
                score = score + excluded.score,
                updated_at = excluded.updated_at
            """,
            (user_id, domain, key, value, delta, now),
        )
        row = conn.execute(
            """
            SELECT * FROM preferences
            WHERE user_id = ? AND domain = ? AND key = ? AND value = ?
            """,
            (user_id, domain, key, value),
        ).fetchone()
        return dict(row)


def get_preferences(
    user_id: str,
    domain: str | None = None,
    *,
    path: Path | str | None = None,
) -> list[dict[str, Any]]:
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.get_preferences(user_id, at, rt, domain=domain)
    sql = "SELECT * FROM preferences WHERE user_id = ?"
    params: list[Any] = [user_id]
    if domain:
        sql += " AND domain = ?"
        params.append(domain)
    sql += " ORDER BY abs(score) DESC, updated_at DESC"
    with get_conn(path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def record_feedback(
    decision_id: int,
    *,
    accepted: bool,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Mark decision accepted/rejected and update preference scores."""
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.record_feedback(
            decision_id, accepted=accepted, access_token=at, refresh_token=rt
        )
    status = "accepted" if accepted else "rejected"
    decision = set_decision_status(decision_id, status, path=path)
    delta = 1.0 if accepted else -1.0
    upsert_preference(
        decision["user_id"],
        decision["domain"],
        "suggestion",
        decision["suggestion"].strip().lower(),
        delta,
        path=path,
    )
    return decision


def _decision_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["context"] = json.loads(d.get("context_json") or "{}")
    except json.JSONDecodeError:
        d["context"] = {}
    return d
