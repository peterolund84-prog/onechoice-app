# -*- coding: utf-8 -*-
"""
GDPR helpers for OneChoice (Art. 15/17/20 + LLM transfer hygiene).

- export_user_data: portable JSON of everything we store for a user
- delete_user_account: hard-delete auth + all app rows + storage objects
- llm_safe_*: strip direct identifiers before any AI provider call
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import db

log = logging.getLogger("onechoice.gdpr")

# Keys that must never leave the app toward an LLM provider
_LLM_BLOCKED_KEYS = frozenset(
    {
        "id",
        "user_id",
        "email",
        "access_token",
        "refresh_token",
        "created_at",
        "updated_at",
        "password",
        "phone",
        "name",
        "full_name",
        "address",
        "ssn",
        "personnummer",
    }
)


def privacy_policy_url() -> str:
    """Optional absolute URL; empty → in-app privacy page (?privacy=1)."""
    try:
        import os

        env = (os.environ.get("PRIVACY_URL") or "").strip()
        if env:
            return env
        import streamlit as st

        return str(st.secrets.get("PRIVACY_URL", "") or "").strip()
    except Exception:
        return ""


def export_user_data(
    user_id: str,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    """Art. 20 — machine-readable export of all rows for this user."""
    uid = str(user_id)
    if db._use_supabase(path):
        import supabase_store as store

        at, rt = db._tokens()
        return store.export_user_data(uid, at, rt)

    db.init_db(path)
    profile = db.ensure_user(uid, path=path)
    decisions = db.list_decisions(uid, limit=5000, path=path)
    prefs = db.get_preferences(uid, path=path)
    with db.get_conn(path) as conn:
        routed = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM routed_queries WHERE user_id = ? ORDER BY created_at DESC",
                (uid,),
            ).fetchall()
        ]
        # Shares tied to this user's decisions (owner_id if present)
        share_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(public_shares)").fetchall()
        }
        if "owner_id" in share_cols:
            shares = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM public_shares WHERE owner_id = ?",
                    (uid,),
                ).fetchall()
            ]
        else:
            shares = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT s.* FROM public_shares s
                    JOIN decisions d ON d.id = s.decision_id
                    WHERE d.user_id = ?
                    """,
                    (uid,),
                ).fetchall()
            ]
        tokens = [s["token"] for s in shares if s.get("token")]
        opens: list[dict[str, Any]] = []
        for tok in tokens:
            opens.extend(
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM share_opens WHERE token = ?",
                    (tok,),
                ).fetchall()
            )
        photo_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(user_photos)").fetchall()
        }
        photos: list[dict[str, Any]] = []
        if photo_cols:
            photos = [
                dict(r)
                for r in conn.execute(
                    "SELECT id, user_id, kind, path, created_at, expires_at "
                    "FROM user_photos WHERE user_id = ?",
                    (uid,),
                ).fetchall()
            ]
        shopping_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(shopping_items)").fetchall()
        }
        shopping: list[dict[str, Any]] = []
        if shopping_cols:
            shopping = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM shopping_items WHERE user_id = ? ORDER BY created_at DESC",
                    (uid,),
                ).fetchall()
            ]

    # Parse JSON fields for readability
    out_profile = dict(profile)
    for key in ("dietary_json", "wardrobe_json", "profile_json"):
        raw = out_profile.get(key)
        if isinstance(raw, str):
            try:
                out_profile[key] = json.loads(raw)
            except json.JSONDecodeError:
                pass

    return {
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "user_id": uid,
        "profile": out_profile,
        "decisions": decisions,
        "preferences": prefs,
        "routed_queries": routed,
        "public_shares": shares,
        "share_opens": opens,
        "user_photos": photos,
        "shopping_items": shopping,
    }


def delete_user_account(
    user_id: str,
    *,
    path: Path | str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> dict[str, Any]:
    """
    Art. 17 — permanent delete. Not soft-delete / deactivate.

    Supabase: RPC delete_own_account (cascades DB) + storage purge, then sign out.
    SQLite: explicit deletes across every table owning this user_id.
    """
    uid = str(user_id)
    summary: dict[str, Any] = {"user_id": uid, "backend": "sqlite", "ok": False}

    if access_token and refresh_token and path is None:
        try:
            import supabase_client as sb

            if sb.is_configured():
                summary["backend"] = "supabase"
                summary.update(
                    _delete_supabase_account(uid, access_token, refresh_token)
                )
                summary["ok"] = True
                return summary
        except Exception as exc:
            log.exception("supabase account delete failed: %s", exc)
            summary["error"] = str(exc)
            # Fall through to local wipe if tokens also have sqlite guest data

    db.init_db(path)
    with db.get_conn(path) as conn:
        # Shares linked to decisions or owner_id
        share_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(public_shares)").fetchall()
        }
        if "owner_id" in share_cols:
            tokens = [
                r[0]
                for r in conn.execute(
                    "SELECT token FROM public_shares WHERE owner_id = ?",
                    (uid,),
                ).fetchall()
            ]
        else:
            tokens = [
                r[0]
                for r in conn.execute(
                    """
                    SELECT s.token FROM public_shares s
                    JOIN decisions d ON d.id = s.decision_id
                    WHERE d.user_id = ?
                    """,
                    (uid,),
                ).fetchall()
            ]
        for tok in tokens:
            conn.execute("DELETE FROM share_opens WHERE token = ?", (tok,))
        if "owner_id" in share_cols:
            conn.execute("DELETE FROM public_shares WHERE owner_id = ?", (uid,))
        else:
            conn.execute(
                """
                DELETE FROM public_shares WHERE decision_id IN (
                  SELECT id FROM decisions WHERE user_id = ?
                )
                """,
                (uid,),
            )
        n_photos = 0
        photo_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(user_photos)").fetchall()
        }
        if photo_cols:
            n_photos = conn.execute(
                "DELETE FROM user_photos WHERE user_id = ?", (uid,)
            ).rowcount
        n_rq = conn.execute(
            "DELETE FROM routed_queries WHERE user_id = ?", (uid,)
        ).rowcount
        n_pref = conn.execute(
            "DELETE FROM preferences WHERE user_id = ?", (uid,)
        ).rowcount
        shop_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(shopping_items)").fetchall()
        }
        n_shop = 0
        if shop_cols:
            n_shop = conn.execute(
                "DELETE FROM shopping_items WHERE user_id = ?", (uid,)
            ).rowcount
        n_dec = conn.execute(
            "DELETE FROM decisions WHERE user_id = ?", (uid,)
        ).rowcount
        n_user = conn.execute("DELETE FROM users WHERE id = ?", (uid,)).rowcount
        summary.update(
            {
                "ok": True,
                "deleted": {
                    "users": n_user,
                    "decisions": n_dec,
                    "preferences": n_pref,
                    "shopping_items": n_shop,
                    "routed_queries": n_rq,
                    "user_photos": n_photos,
                    "public_shares": len(tokens),
                },
            }
        )
    return summary


def _delete_supabase_account(
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any]:
    import supabase_client as sb
    import supabase_store as store

    # Purge storage objects first (best-effort)
    storage_n = store.delete_user_photos(user_id, access_token, refresh_token)
    # Preferred: security-definer RPC that deletes auth.users (cascades profiles…)
    client = sb.authed_client(access_token, refresh_token)
    rpc_ok = False
    try:
        client.rpc("delete_own_account").execute()
        rpc_ok = True
    except Exception as exc:
        log.warning("delete_own_account RPC failed (%s) — wiping app tables", exc)
        store.delete_all_user_rows(user_id, access_token, refresh_token)
        # Optional service-role auth delete
        sb.admin_delete_user(user_id)
    try:
        sb.sign_out(access_token, refresh_token)
    except Exception:
        pass
    return {"rpc_delete_own_account": rpc_ok, "storage_objects_removed": storage_n}


def assert_user_gone(user_id: str, *, path: Path | str | None = None) -> None:
    """Test helper — raise if any row remains for user_id."""
    uid = str(user_id)
    db.init_db(path)
    with db.get_conn(path) as conn:
        checks = [
            ("users", "SELECT COUNT(*) FROM users WHERE id = ?", (uid,)),
            ("decisions", "SELECT COUNT(*) FROM decisions WHERE user_id = ?", (uid,)),
            ("preferences", "SELECT COUNT(*) FROM preferences WHERE user_id = ?", (uid,)),
            (
                "routed_queries",
                "SELECT COUNT(*) FROM routed_queries WHERE user_id = ?",
                (uid,),
            ),
        ]
        photo_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(user_photos)").fetchall()
        }
        if photo_cols:
            checks.append(
                (
                    "user_photos",
                    "SELECT COUNT(*) FROM user_photos WHERE user_id = ?",
                    (uid,),
                )
            )
        shop_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(shopping_items)").fetchall()
        }
        if shop_cols:
            checks.append(
                (
                    "shopping_items",
                    "SELECT COUNT(*) FROM shopping_items WHERE user_id = ?",
                    (uid,),
                )
            )
        share_cols = {
            r[1] for r in conn.execute("PRAGMA table_info(public_shares)").fetchall()
        }
        if "owner_id" in share_cols:
            checks.append(
                (
                    "public_shares",
                    "SELECT COUNT(*) FROM public_shares WHERE owner_id = ?",
                    (uid,),
                )
            )
        leftover: dict[str, int] = {}
        for name, sql, args in checks:
            n = int(conn.execute(sql, args).fetchone()[0])
            if n:
                leftover[name] = n
        if leftover:
            raise AssertionError(f"user data remains after delete: {leftover}")


def llm_safe_profile(profile: dict[str, Any] | None) -> dict[str, Any]:
    """Anonymous preference slice for AI providers — never id/email."""
    src = dict(profile or {})
    dietary = src.get("dietary")
    if dietary is None:
        raw = src.get("dietary_json")
        if isinstance(raw, str):
            try:
                dietary = json.loads(raw)
            except json.JSONDecodeError:
                dietary = []
        else:
            dietary = raw or []
    wardrobe = src.get("wardrobe")
    if wardrobe is None:
        raw = src.get("wardrobe_json")
        if isinstance(raw, str):
            try:
                wardrobe = json.loads(raw)
            except json.JSONDecodeError:
                wardrobe = []
        else:
            wardrobe = raw or []
    clothes = {}
    pj = src.get("profile_json")
    if isinstance(pj, str):
        try:
            pj = json.loads(pj)
        except json.JSONDecodeError:
            pj = {}
    if isinstance(pj, dict):
        c = pj.get("clothes") or {}
        if isinstance(c, dict):
            clothes = {
                "section": c.get("section"),
                "sizes": c.get("sizes") or {},
                "retailers": c.get("retailers") or [],
            }
    return {
        "language": src.get("language") or "sv",
        "budget": src.get("budget"),
        "dietary": dietary,
        "location": src.get("location"),
        "wardrobe": wardrobe,
        "clothes": clothes,
        "is_pro": bool(src.get("is_pro")),
    }


def llm_safe_context(context: dict[str, Any] | None) -> dict[str, Any]:
    """Drop direct identifiers from decision context before LLM send."""
    return _strip_blocked(context or {})


def llm_safe_preferences(prefs: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in prefs or []:
        if not isinstance(p, dict):
            continue
        out.append(
            {
                "domain": p.get("domain"),
                "key": p.get("key"),
                "value": p.get("value"),
                "score": p.get("score"),
            }
        )
    return out


def _strip_blocked(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for k, v in value.items():
            if str(k).lower() in _LLM_BLOCKED_KEYS:
                continue
            clean[str(k)] = _strip_blocked(v)
        return clean
    if isinstance(value, list):
        return [_strip_blocked(x) for x in value]
    return value
