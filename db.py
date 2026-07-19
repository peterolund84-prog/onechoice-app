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
NEAR_DOMAIN = "other"  # stored domain for NEAR_DOMAIN router route
DECISION_STATUSES = ("shown", "rejected", "accepted", "locked")
ROUTER_ROUTES = (
    "IN_DOMAIN",
    "NEAR_DOMAIN",
    "HIGH_STAKES",
    "AMBIGUOUS",
    "NOT_A_DECISION",
)

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
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_preferences_user_domain
                ON preferences(user_id, domain);

            CREATE TABLE IF NOT EXISTS routed_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                raw_text TEXT,
                route TEXT NOT NULL,
                domain TEXT,
                confidence REAL,
                category_guess TEXT,
                normalized_question TEXT,
                decision_shown INTEGER NOT NULL DEFAULT 0,
                accepted INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_routed_queries_route
                ON routed_queries(route, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_routed_queries_category
                ON routed_queries(category_guess, created_at DESC);

            CREATE TABLE IF NOT EXISTS public_shares (
                token TEXT PRIMARY KEY,
                decision_id INTEGER,
                domain TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'sv',
                open_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                owner_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_public_shares_decision
                ON public_shares(decision_id);

            CREATE TABLE IF NOT EXISTS share_opens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                decision_id INTEGER,
                ref TEXT,
                opened_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_share_opens_token
                ON share_opens(token, opened_at DESC);
            """
        )
        # Migrate older DBs missing profile_json
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
        if "profile_json" not in cols:
            conn.execute(
                "ALTER TABLE users ADD COLUMN profile_json TEXT NOT NULL DEFAULT '{}'"
            )
        # Ensure routed_queries exists on older DBs (executescript IF NOT EXISTS covers new)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS routed_queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                raw_text TEXT,
                route TEXT NOT NULL,
                domain TEXT,
                confidence REAL,
                category_guess TEXT,
                normalized_question TEXT,
                decision_shown INTEGER NOT NULL DEFAULT 0,
                accepted INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        try:
            conn.execute(
                """
                CREATE VIEW IF NOT EXISTS near_domain_demand AS
                SELECT category_guess,
                       COUNT(*) AS total,
                       COUNT(DISTINCT user_id) AS unique_users,
                       AVG(CASE WHEN accepted = 1 THEN 1.0 ELSE 0.0 END) AS accept_rate
                FROM routed_queries
                WHERE route = 'NEAR_DOMAIN'
                GROUP BY category_guess
                """
            )
        except sqlite3.Error:
            pass
        # Privacy: wipe raw_text older than 90 days (normalized_question kept)
        try:
            conn.execute(
                """
                UPDATE routed_queries
                SET raw_text = NULL
                WHERE raw_text IS NOT NULL
                  AND datetime(created_at) < datetime('now', '-90 days')
                """
            )
        except sqlite3.Error:
            pass
        # Public share tables (migrate older DBs)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS public_shares (
                token TEXT PRIMARY KEY,
                decision_id INTEGER,
                domain TEXT NOT NULL,
                suggestion TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'sv',
                open_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS share_opens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                decision_id INTEGER,
                ref TEXT,
                opened_at TEXT NOT NULL
            )
            """
        )
        # GDPR: owner_id on shares + user_photos metadata (SQLite)
        share_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(public_shares)").fetchall()
        }
        if "owner_id" not in share_cols:
            conn.execute("ALTER TABLE public_shares ADD COLUMN owner_id TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )


def ensure_public_share(
    decision: dict[str, Any],
    *,
    language: str = "sv",
    path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Create (or reuse) a public, denormalized share snapshot for a decision.
    Works in guest SQLite without auth — required for share landing pages.
    """
    import share_domain as sd

    init_db(path)
    did = decision.get("decision_id") or decision.get("id")
    try:
        did_int = int(did) if did is not None else None
    except (TypeError, ValueError):
        did_int = None

    # Reuse existing share for this decision_id when possible
    if did_int is not None:
        with get_conn(path) as conn:
            row = conn.execute(
                "SELECT * FROM public_shares WHERE decision_id = ? ORDER BY created_at DESC LIMIT 1",
                (did_int,),
            ).fetchone()
            if row:
                return _public_share_row(row)

    token = uuid.uuid4().hex
    payload = sd.public_payload_from_decision(decision, language=language)
    payload["decision_id"] = did_int if did_int is not None else did
    blob = json.dumps(payload, ensure_ascii=False, default=str)
    domain = str(decision.get("domain") or payload.get("domain") or "other")
    suggestion = str(decision.get("suggestion") or payload.get("suggestion") or "")
    owner_id = decision.get("user_id") or payload.get("user_id")
    with get_conn(path) as conn:
        conn.execute(
            """
            INSERT INTO public_shares (
                token, decision_id, domain, suggestion, payload_json, language,
                open_count, created_at, owner_id
            ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (
                token,
                did_int,
                domain,
                suggestion,
                blob,
                language,
                utc_now(),
                str(owner_id) if owner_id else None,
            ),
        )
        row = conn.execute(
            "SELECT * FROM public_shares WHERE token = ?", (token,)
        ).fetchone()
        return _public_share_row(row)


def get_public_share(
    token: str, *, path: Path | str | None = None
) -> dict[str, Any] | None:
    if not token:
        return None
    init_db(path)
    with get_conn(path) as conn:
        row = conn.execute(
            "SELECT * FROM public_shares WHERE token = ?", (str(token),)
        ).fetchone()
        return _public_share_row(row) if row else None


def log_share_open(
    token: str,
    *,
    decision_id: int | None = None,
    ref: str | None = "share",
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Attribution: share → visit. Increment open_count + append share_opens row."""
    init_db(path)
    with get_conn(path) as conn:
        conn.execute(
            """
            INSERT INTO share_opens (token, decision_id, ref, opened_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(token), decision_id, ref or "share", utc_now()),
        )
        conn.execute(
            "UPDATE public_shares SET open_count = open_count + 1 WHERE token = ?",
            (str(token),),
        )
        row = conn.execute(
            "SELECT * FROM share_opens WHERE id = last_insert_rowid()"
        ).fetchone()
        return dict(row) if row else {"token": token, "decision_id": decision_id, "ref": ref}


def count_share_opens(token: str, *, path: Path | str | None = None) -> int:
    init_db(path)
    with get_conn(path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM share_opens WHERE token = ?", (str(token),)
        ).fetchone()
        return int(row["n"] if row else 0)


def _public_share_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    try:
        d["payload"] = json.loads(d.get("payload_json") or "{}")
    except json.JSONDecodeError:
        d["payload"] = {}
    return d


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
        try:
            import supabase_store as store

            at, rt = _tokens()
            row = store.create_decision(
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
            if row.get("id") is not None:
                return row
        except Exception:
            # Fall through to local SQLite so the app never hard-fails on Cloud
            pass

    # SQLite path — force local user row (FK) even if auth tokens are set
    _ensure_sqlite_user(user_id, path=path)
    ctx = json.dumps(context or {}, ensure_ascii=False, default=str)
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


def _ensure_sqlite_user(user_id: str, *, path: Path | str | None = None) -> None:
    """Insert user into SQLite if missing — ignores Supabase auth routing."""
    with get_conn(path) as conn:
        row = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
        if row:
            return
        conn.execute(
            """
            INSERT INTO users (id, created_at, language)
            VALUES (?, ?, ?)
            """,
            (user_id, utc_now(), "sv"),
        )


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
    meal_type: str | None = None,
    path: Path | str | None = None,
) -> list[str]:
    """Suggestions accepted/locked/shown recently — used as repetition guard.

    When meal_type is set (food), only count decisions with that meal_type in
    context — breakfast habits must not block dinner variety and vice versa.
    """
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        rows = store.recent_suggestions(user_id, domain, at, rt, days=days)
        # store returns suggestion strings only today — filter via list_decisions
        if meal_type:
            decisions = store.list_decisions(
                user_id, at, rt, domain=domain, limit=80
            )
            out: list[str] = []
            for d in decisions:
                ctx = d.get("context") or {}
                if isinstance(ctx, str):
                    try:
                        ctx = json.loads(ctx)
                    except Exception:
                        ctx = {}
                if isinstance(ctx, dict) and ctx.get("meal_type") == meal_type and d.get("suggestion"):
                    out.append(d["suggestion"])
            return out
        return rows
    with get_conn(path) as conn:
        if meal_type and domain == "food":
            rows = conn.execute(
                """
                SELECT suggestion FROM decisions
                WHERE user_id = ? AND domain = ?
                  AND status IN ('accepted', 'locked', 'shown', 'rejected')
                  AND datetime(created_at) >= datetime('now', ?)
                  AND json_extract(context_json, '$.meal_type') = ?
                ORDER BY created_at DESC
                """,
                (user_id, domain, f"-{int(days)} days", meal_type),
            ).fetchall()
        else:
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
    """Mark decision accepted/rejected and update preference scores.

    If Supabase is selected but the row is missing / RLS fails, fall back to
    local SQLite so accept never hard-crashes the UI mid-button-handler.
    """
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        try:
            return store.record_feedback(
                decision_id, accepted=accepted, access_token=at, refresh_token=rt
            )
        except Exception as exc:
            import logging

            logging.getLogger("onechoice.db").warning(
                "supabase record_feedback failed (%s); falling back to sqlite", exc
            )
            path = path or DB_PATH

    return _record_feedback_sqlite(decision_id, accepted=accepted, path=path or DB_PATH)


def _record_feedback_sqlite(
    decision_id: int,
    *,
    accepted: bool,
    path: Path | str,
) -> dict[str, Any]:
    """SQLite-only accept/reject — never routes back to Supabase."""
    status = "accepted" if accepted else "rejected"
    try:
        # Pass explicit path so _use_supabase is False
        decision = set_decision_status(decision_id, status, path=path)
    except KeyError:
        import logging

        logging.getLogger("onechoice.db").warning(
            "record_feedback: decision %s missing in sqlite — soft-succeed",
            decision_id,
        )
        return {
            "id": decision_id,
            "status": status,
            "suggestion": "",
            "user_id": "",
            "domain": "",
            "context": {},
        }
    delta = 1.0 if accepted else -1.0
    suggestion = str(decision.get("suggestion") or "").strip().lower()
    if suggestion and decision.get("user_id") and decision.get("domain"):
        upsert_preference(
            decision["user_id"],
            decision["domain"],
            "suggestion",
            suggestion,
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


# ---------------------------------------------------------------------------
# Routed query logging (privacy-aware)
# ---------------------------------------------------------------------------
def log_routed_query(
    user_id: str,
    *,
    route: str,
    domain: str | None = None,
    confidence: float | None = None,
    category_guess: str | None = None,
    normalized_question: str | None = None,
    raw_text: str | None = None,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Insert one router log row.

    HIGH_STAKES privacy: store ONLY route + timestamp + user_id.
    """
    if route == "HIGH_STAKES":
        raw_text = None
        domain = None
        confidence = None
        category_guess = None
        normalized_question = None

    if _use_supabase(path):
        try:
            import supabase_store as store

            at, rt = _tokens()
            row = store.log_routed_query(
                user_id,
                access_token=at,
                refresh_token=rt,
                route=route,
                domain=domain,
                confidence=confidence,
                category_guess=category_guess,
                normalized_question=normalized_question,
                raw_text=raw_text,
            )
            if row.get("id") is not None:
                return row
        except Exception:
            pass

    _ensure_sqlite_user(user_id, path=path)
    with get_conn(path) as conn:
        cur = conn.execute(
            """
            INSERT INTO routed_queries (
                user_id, created_at, raw_text, route, domain, confidence,
                category_guess, normalized_question, decision_shown, accepted
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, NULL)
            """,
            (
                user_id,
                utc_now(),
                raw_text,
                route,
                domain,
                confidence,
                category_guess,
                normalized_question,
            ),
        )
        row = conn.execute(
            "SELECT * FROM routed_queries WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)


def update_routed_query(
    query_id: int,
    *,
    decision_shown: bool | None = None,
    accepted: bool | None = None,
    path: Path | str | None = None,
) -> dict[str, Any] | None:
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.update_routed_query(
            query_id,
            access_token=at,
            refresh_token=rt,
            decision_shown=decision_shown,
            accepted=accepted,
        )
    updates: list[str] = []
    params: list[Any] = []
    if decision_shown is not None:
        updates.append("decision_shown = ?")
        params.append(1 if decision_shown else 0)
    if accepted is not None:
        updates.append("accepted = ?")
        params.append(1 if accepted else 0)
    if not updates:
        return None
    params.append(query_id)
    with get_conn(path) as conn:
        conn.execute(
            f"UPDATE routed_queries SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        row = conn.execute(
            "SELECT * FROM routed_queries WHERE id = ?", (query_id,)
        ).fetchone()
        return dict(row) if row else None


def purge_expired_raw_text(
    *,
    days: int = 90,
    path: Path | str | None = None,
) -> int:
    """Null out raw_text older than `days`. Keeps normalized_question + category_guess."""
    if _use_supabase(path):
        import supabase_store as store

        at, rt = _tokens()
        return store.purge_expired_raw_text(days=days, access_token=at, refresh_token=rt)
    with get_conn(path) as conn:
        cur = conn.execute(
            """
            UPDATE routed_queries
            SET raw_text = NULL
            WHERE raw_text IS NOT NULL
              AND datetime(created_at) < datetime('now', ?)
            """,
            (f"-{int(days)} days",),
        )
        return int(cur.rowcount or 0)


def near_domain_demand(*, path: Path | str | None = None) -> list[dict[str, Any]]:
    with get_conn(path) as conn:
        rows = conn.execute(
            "SELECT * FROM near_domain_demand"
        ).fetchall()
        return [dict(r) for r in rows]
