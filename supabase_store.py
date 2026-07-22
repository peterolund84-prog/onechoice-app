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
    allowed = {
        "language",
        "is_pro",
        "budget",
        "dietary",
        "location",
        "wardrobe",
        "email",
        "profile_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if "profile_json" in fields and "profile_json" not in updates:
        updates["profile_json"] = fields["profile_json"]
    if "profile_json" in updates and isinstance(updates["profile_json"], str):
        try:
            updates["profile_json"] = json.loads(updates["profile_json"])
        except json.JSONDecodeError:
            updates["profile_json"] = {}
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
    rows = res.data or []
    if rows and rows[0].get("id") is not None:
        return _decision_row(rows[0])
    # Some RLS configs return no rows — fetch latest for this user
    fetched = (
        client.table("decisions")
        .select("*")
        .eq("user_id", user_id)
        .eq("suggestion", suggestion)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    frows = fetched.data or []
    if not frows or frows[0].get("id") is None:
        raise RuntimeError("Supabase insert returned no decision id")
    return _decision_row(frows[0])


def mark_execution_opened(
    decision_id: int,
    access_token: str,
    refresh_token: str,
    *,
    opened_at: str,
) -> dict[str, Any]:
    client = _client(access_token, refresh_token)
    existing = (
        client.table("decisions")
        .select("execution_opened_at")
        .eq("id", decision_id)
        .limit(1)
        .execute()
    )
    rows = existing.data or []
    if rows and rows[0].get("execution_opened_at"):
        res = (
            client.table("decisions")
            .select("*")
            .eq("id", decision_id)
            .limit(1)
            .execute()
        )
        got = res.data or []
        if not got:
            raise KeyError(f"decision {decision_id} not found")
        return _decision_row(got[0])
    client.table("decisions").update({"execution_opened_at": opened_at}).eq(
        "id", decision_id
    ).execute()
    res = client.table("decisions").select("*").eq("id", decision_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise KeyError(f"decision {decision_id} not found")
    return _decision_row(rows[0])


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


def log_routed_query(
    user_id: str,
    *,
    access_token: str,
    refresh_token: str,
    route: str,
    domain: str | None = None,
    confidence: float | None = None,
    category_guess: str | None = None,
    normalized_question: str | None = None,
    raw_text: str | None = None,
) -> dict[str, Any]:
    if route == "HIGH_STAKES":
        raw_text = None
        domain = None
        confidence = None
        category_guess = None
        normalized_question = None
    client = _client(access_token, refresh_token)
    payload = {
        "user_id": user_id,
        "raw_text": raw_text,
        "route": route,
        "domain": domain,
        "confidence": confidence,
        "category_guess": category_guess,
        "normalized_question": normalized_question,
        "decision_shown": False,
        "accepted": None,
    }
    res = client.table("routed_queries").insert(payload).execute()
    return (res.data or [payload])[0]


def update_routed_query(
    query_id: int,
    *,
    access_token: str,
    refresh_token: str,
    decision_shown: bool | None = None,
    accepted: bool | None = None,
) -> dict[str, Any] | None:
    updates: dict[str, Any] = {}
    if decision_shown is not None:
        updates["decision_shown"] = bool(decision_shown)
    if accepted is not None:
        updates["accepted"] = bool(accepted)
    if not updates:
        return None
    client = _client(access_token, refresh_token)
    client.table("routed_queries").update(updates).eq("id", query_id).execute()
    res = (
        client.table("routed_queries").select("*").eq("id", query_id).limit(1).execute()
    )
    rows = res.data or []
    return rows[0] if rows else None


def purge_expired_raw_text(
    *,
    days: int = 90,
    access_token: str,
    refresh_token: str,
) -> int:
    client = _client(access_token, refresh_token)
    try:
        res = client.rpc("purge_routed_query_raw_text", {"days": int(days)}).execute()
        return int(res.data or 0)
    except Exception:
        return 0


def export_user_data(
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any]:
    client = _client(access_token, refresh_token)
    profile = ensure_profile(user_id, access_token, refresh_token)
    decisions = list_decisions(user_id, access_token, refresh_token, limit=5000)
    prefs = get_preferences(user_id, access_token, refresh_token)
    routed = (
        client.table("routed_queries")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    shares = (
        client.table("public_shares")
        .select("*")
        .eq("owner_id", user_id)
        .execute()
    )
    photos = (
        client.table("user_photos")
        .select("id,user_id,kind,path,created_at,expires_at")
        .eq("user_id", user_id)
        .execute()
    )
    shopping = (
        client.table("shopping_items")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    share_rows = list(shares.data or [])
    opens: list[dict[str, Any]] = []
    for s in share_rows:
        tok = s.get("token")
        if not tok:
            continue
        try:
            op = (
                client.table("share_opens")
                .select("*")
                .eq("token", tok)
                .execute()
            )
            opens.extend(list(op.data or []))
        except Exception:
            pass
    return {
        "exported_at": _utc_now(),
        "user_id": user_id,
        "profile": profile,
        "decisions": decisions,
        "preferences": prefs,
        "routed_queries": list(routed.data or []),
        "public_shares": share_rows,
        "share_opens": opens,
        "user_photos": list(photos.data or []),
        "shopping_items": list(shopping.data or []),
    }


def delete_all_user_rows(
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> None:
    """Fallback wipe when delete_own_account RPC is unavailable."""
    client = _client(access_token, refresh_token)
    for table in ("shopping_items", "user_photos", "routed_queries", "preferences", "decisions"):
        try:
            client.table(table).delete().eq("user_id", user_id).execute()
        except Exception:
            pass
    try:
        client.table("public_shares").delete().eq("owner_id", user_id).execute()
    except Exception:
        pass
    try:
        client.table("profiles").delete().eq("id", user_id).execute()
    except Exception:
        pass


def delete_user_photos(
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> int:
    """Remove storage objects + metadata for user. Returns approx object count."""
    client = _client(access_token, refresh_token)
    n = 0
    try:
        meta = (
            client.table("user_photos")
            .select("id,path")
            .eq("user_id", user_id)
            .execute()
        )
        rows = list(meta.data or [])
        for row in rows:
            path = row.get("path")
            if path:
                try:
                    client.storage.from_("user-photos").remove([path])
                    n += 1
                except Exception:
                    pass
        client.table("user_photos").delete().eq("user_id", user_id).execute()
    except Exception:
        # Folder listing fallback
        try:
            listed = client.storage.from_("user-photos").list(user_id)
            names = [
                f"{user_id}/{item['name']}"
                for item in (listed or [])
                if isinstance(item, dict) and item.get("name")
            ]
            if names:
                client.storage.from_("user-photos").remove(names)
                n = len(names)
        except Exception:
            pass
    return n


def upload_fridge_photo(
    user_id: str,
    blob: bytes,
    *,
    access_token: str,
    refresh_token: str,
    mime: str = "image/jpeg",
) -> dict[str, Any] | None:
    """Store fridge photo privately; expires_at = now+24h (safety net)."""
    import uuid as _uuid

    client = _client(access_token, refresh_token)
    ext = "jpg" if "jpeg" in (mime or "") or "jpg" in (mime or "") else "png"
    path = f"{user_id}/fridge/{_uuid.uuid4().hex}.{ext}"
    try:
        client.storage.from_("user-photos").upload(
            path,
            blob,
            file_options={"content-type": mime or "image/jpeg", "upsert": "false"},
        )
        expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        row = {
            "user_id": user_id,
            "kind": "fridge",
            "path": path,
            "expires_at": expires,
        }
        ins = client.table("user_photos").insert(row).execute()
        return (ins.data or [row])[0]
    except Exception:
        return None


def delete_photo_path(
    path: str,
    *,
    access_token: str,
    refresh_token: str,
) -> None:
    client = _client(access_token, refresh_token)
    try:
        client.storage.from_("user-photos").remove([path])
    except Exception:
        pass
    try:
        client.table("user_photos").delete().eq("path", path).execute()
    except Exception:
        pass


def _shopping_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["checked"] = bool(out.get("checked"))
    return out


def list_shopping_items(
    user_id: str,
    access_token: str,
    refresh_token: str,
) -> list[dict[str, Any]]:
    client = _client(access_token, refresh_token)
    res = (
        client.table("shopping_items")
        .select("*")
        .eq("user_id", user_id)
        .order("checked")
        .order("category")
        .order("name")
        .execute()
    )
    return [_shopping_row(r) for r in (res.data or [])]


def purge_stale_checked_shopping_items(
    user_id: str,
    access_token: str,
    refresh_token: str,
    *,
    hours: int = 24,
) -> int:
    client = _client(access_token, refresh_token)
    cutoff = (
        datetime.now(timezone.utc) - timedelta(hours=int(hours))
    ).isoformat()
    try:
        stale = (
            client.table("shopping_items")
            .select("id")
            .eq("user_id", user_id)
            .eq("checked", True)
            .lt("checked_at", cutoff)
            .execute()
        )
        ids = [r["id"] for r in (stale.data or []) if r.get("id") is not None]
        if not ids:
            return 0
        client.table("shopping_items").delete().in_("id", ids).execute()
        return len(ids)
    except Exception:
        return 0


def upsert_shopping_item(
    user_id: str,
    name: str,
    category: str,
    *,
    source_decision_id: int | None = None,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any] | None:
    import shopping_items as si

    clean = si.normalize_name(name)
    if not clean:
        return None
    cat = category if category in si.CATEGORIES else si.categorize_item(clean)
    client = _client(access_token, refresh_token)
    existing = (
        client.table("shopping_items")
        .select("*")
        .eq("user_id", user_id)
        .eq("checked", False)
        .execute()
    )
    for row in existing.data or []:
        if si.normalize_name(str(row.get("name") or "")) == clean:
            return _shopping_row(row)
    payload: dict[str, Any] = {
        "user_id": user_id,
        "name": clean,
        "category": cat,
        "checked": False,
        "source_decision_id": source_decision_id,
    }
    ins = client.table("shopping_items").insert(payload).execute()
    rows = ins.data or []
    if rows:
        return _shopping_row(rows[0])
    fetched = (
        client.table("shopping_items")
        .select("*")
        .eq("user_id", user_id)
        .eq("name", clean)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    frows = fetched.data or []
    return _shopping_row(frows[0]) if frows else None


def toggle_shopping_item(
    user_id: str,
    item_id: int,
    checked: bool,
    *,
    access_token: str,
    refresh_token: str,
) -> dict[str, Any] | None:
    client = _client(access_token, refresh_token)
    updates: dict[str, Any] = {
        "checked": bool(checked),
        "checked_at": _utc_now() if checked else None,
    }
    client.table("shopping_items").update(updates).eq("id", item_id).eq(
        "user_id", user_id
    ).execute()
    res = (
        client.table("shopping_items")
        .select("*")
        .eq("id", item_id)
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    rows = res.data or []
    return _shopping_row(rows[0]) if rows else None
