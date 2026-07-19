# -*- coding: utf-8 -*-
"""Supabase-backed storage for profiles, decisions, preferences."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import supabase_client as sb


def _client(access_token: str, refresh_token: str):
    return sb.authed_client(access_token, refresh_token)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_profile(
    user_id: str,
    access_token: str,
    refresh_token: str,
    *,
    language: str = "sv",
    email: str | None = None,
) -> dict[str, Any]:
    client = _client(access_token, refresh_token)
    res = client.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    rows = res.data or []
    if rows:
        return _profile_row(rows[0])
    payload = {"id": user_id, "language": language}
    if email:
        payload["email"] = email
    ins = client.table("profiles").insert(payload).execute()
    data = (ins.data or [payload])[0]
    return _profile_row(data)


def update_profile(
    user_id: str,
    access_token: str,
    refresh_token: str,
    **fields: Any,
) -> dict[str, Any]:
    allowed = {"language", "is_pro", "budget", "dietary", "location", "wardrobe", "email"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    # Accept dietary_json / wardrobe_json aliases from sqlite API
    if "dietary_json" in fields:
        updates["dietary"] = fields["dietary_json"]
        if isinstance(updates["dietary"], str):
            try:
                updates["dietary"] = json.loads(updates["dietary"])
            except json.JSONDecodeError:
                updates["dietary"] = []
    if "wardrobe_json" in fields:
        updates["wardrobe"] = fields["wardrobe_json"]
        if isinstance(updates["wardrobe"], str):
            try:
                updates["wardrobe"] = json.loads(updates["wardrobe"])
            except json.JSONDecodeError:
                updates["wardrobe"] = []
    if "is_pro" in updates:
        updates["is_pro"] = bool(updates["is_pro"])
    if not updates:
        return ensure_profile(user_id, access_token, refresh_token)
    client = _client(access_token, refresh_token)
    client.table("profiles").update(updates).eq("id", user_id).execute()
    return ensure_profile(user_id, access_token, refresh_token)


def create_decision(
    *,
    user_id: str,
    access_token: str,
    refresh_token: str,
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
) -> dict[str, Any]:
    client = _client(access_token, refresh_token)
    payload = {
        "user_id": user_id,
        "domain": domain,
        "question": question,
        "suggestion": suggestion,
        "justification": justification,
        "execution_type": execution_type,
        "execution_label": execution_label,
        "execution_url": execution_url,
        "status": status,
        "reroll_index": reroll_index,
        "context": context or {},
    }
    res = client.table("decisions").insert(payload).execute()
    row = (res.data or [payload])[0]
    return _decision_row(row)


def set_decision_status(
    decision_id: int,
    status: str,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any]:
    client = _client(access_token, refresh_token)
    client.table("decisions").update({"status": status}).eq("id", decision_id).execute()
    res = client.table("decisions").select("*").eq("id", decision_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise KeyError(f"decision {decision_id} not found")
    return _decision_row(rows[0])


def list_decisions(
    user_id: str,
    access_token: str,
    refresh_token: str,
    *,
    domain: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    client = _client(access_token, refresh_token)
    q = client.table("decisions").select("*").eq("user_id", user_id)
    if domain:
        q = q.eq("domain", domain)
    if status:
        q = q.eq("status", status)
    res = q.order("created_at", desc=True).limit(limit).execute()
    return [_decision_row(r) for r in (res.data or [])]


def recent_suggestions(
    user_id: str,
    domain: str,
    access_token: str,
    refresh_token: str,
    *,
    days: int = 14,
) -> list[str]:
    client = _client(access_token, refresh_token)
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    res = (
        client.table("decisions")
        .select("suggestion")
        .eq("user_id", user_id)
        .eq("domain", domain)
        .gte("created_at", since)
        .order("created_at", desc=True)
        .execute()
    )
    return [r["suggestion"] for r in (res.data or []) if r.get("suggestion")]


def upsert_preference(
    user_id: str,
    domain: str,
    key: str,
    value: str,
    delta: float,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any]:
    client = _client(access_token, refresh_token)
    existing = (
        client.table("preferences")
        .select("*")
        .eq("user_id", user_id)
        .eq("domain", domain)
        .eq("key", key)
        .eq("value", value)
        .limit(1)
        .execute()
    )
    rows = existing.data or []
    now = _utc_now()
    if rows:
        row = rows[0]
        new_score = float(row.get("score") or 0) + float(delta)
        client.table("preferences").update(
            {"score": new_score, "updated_at": now}
        ).eq("id", row["id"]).execute()
        return {
            "id": row["id"],
            "user_id": user_id,
            "domain": domain,
            "key": key,
            "value": value,
            "score": new_score,
            "updated_at": now,
        }
    payload = {
        "user_id": user_id,
        "domain": domain,
        "key": key,
        "value": value,
        "score": float(delta),
        "updated_at": now,
    }
    res = client.table("preferences").insert(payload).execute()
    return (res.data or [payload])[0]


def get_preferences(
    user_id: str,
    access_token: str,
    refresh_token: str,
    domain: str | None = None,
) -> list[dict[str, Any]]:
    client = _client(access_token, refresh_token)
    q = client.table("preferences").select("*").eq("user_id", user_id)
    if domain:
        q = q.eq("domain", domain)
    res = q.order("updated_at", desc=True).execute()
    return list(res.data or [])


def record_feedback(
    decision_id: int,
    *,
    accepted: bool,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any]:
    status = "accepted" if accepted else "rejected"
    decision = set_decision_status(
        decision_id, status, access_token, refresh_token
    )
    delta = 1.0 if accepted else -1.0
    upsert_preference(
        decision["user_id"],
        decision["domain"],
        "suggestion",
        decision["suggestion"].strip().lower(),
        delta,
        access_token,
        refresh_token,
    )
    return decision


def _profile_row(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    # Normalize to sqlite-compatible keys used by pipeline/app
    d["dietary_json"] = json.dumps(d.get("dietary") or [], ensure_ascii=False)
    d["wardrobe_json"] = json.dumps(d.get("wardrobe") or [], ensure_ascii=False)
    d["is_pro"] = 1 if d.get("is_pro") else 0
    return d


def _decision_row(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    ctx = d.get("context")
    if isinstance(ctx, str):
        try:
            d["context"] = json.loads(ctx)
        except json.JSONDecodeError:
            d["context"] = {}
    elif ctx is None:
        d["context"] = {}
    d["context_json"] = json.dumps(d.get("context") or {}, ensure_ascii=False)
    return d
