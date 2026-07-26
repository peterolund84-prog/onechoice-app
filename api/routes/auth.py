# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

import db
from api.deps import SessionDep, apply_auth
from api.session_store import COOKIE_MAX_AGE, COOKIE_NAME, STORE

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class SignupBody(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    privacy_consent: bool = False


@router.get("/session")
def session_info(sess: SessionDep) -> dict:
    from api.secrets import secrets_status, supabase_configured

    apply_auth(sess)
    status = secrets_status()
    out = sess.public()
    out["supabase_configured"] = bool(status.get("supabase_configured")) or supabase_configured()
    out["secrets"] = status
    return out


@router.post("/guest")
def ensure_guest(sess: SessionDep, response: Response) -> dict:
    sess.guest_mode = True
    sess.access_token = None
    sess.refresh_token = None
    sess.email = None
    db.clear_auth()
    STORE.save(sess)
    response.set_cookie(
        key=COOKIE_NAME,
        value=sess.sid,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return sess.public()


@router.post("/login")
def login(body: LoginBody, sess: SessionDep, response: Response) -> dict:
    import supabase_client as sb
    from api.secrets import secrets_status

    if not sb.is_configured():
        st = secrets_status()
        if not st.get("secrets_file_found"):
            msg = (
                "Supabase är inte konfigurerad. "
                "Ingen .streamlit/secrets.toml hittades lokalt. "
                "Streamlit Cloud-nycklar följer inte med — lägg SUPABASE_URL och "
                "SUPABASE_KEY i .streamlit/secrets.toml i projektmappen (samma fil Streamlit använder lokalt)."
            )
        elif not st.get("supabase_url_set") or not st.get("supabase_key_set"):
            msg = (
                "Supabase är inte konfigurerad. "
                f"Hittade {st.get('secrets_file')} men SUPABASE_URL/SUPABASE_KEY saknas eller är placeholder."
            )
        else:
            msg = "Supabase är inte konfigurerad."
        return {"ok": False, "error": msg, "secrets": st}
    try:
        data = sb.sign_in(body.email, body.password)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    user = data.get("user") or {}
    sess.user_id = str(user.get("id") or sess.user_id)
    sess.email = str(user.get("email") or body.email)
    sess.access_token = data.get("access_token")
    sess.refresh_token = data.get("refresh_token")
    sess.guest_mode = False
    apply_auth(sess)
    db.ensure_user(sess.user_id, language=sess.language, email=sess.email)
    STORE.save(sess)
    response.set_cookie(
        key=COOKIE_NAME,
        value=sess.sid,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True, **sess.public()}


@router.post("/signup")
def signup(body: SignupBody, sess: SessionDep, response: Response) -> dict:
    import supabase_client as sb

    if not body.privacy_consent:
        return {"ok": False, "error": "Du måste godkänna integritetspolicyn."}
    if not sb.is_configured():
        return {"ok": False, "error": "Supabase är inte konfigurerad."}
    try:
        data = sb.sign_up(body.email, body.password)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    if data.get("needs_email_confirm"):
        return {"ok": True, "needs_email_confirm": True}
    user = data.get("user") or {}
    sess.user_id = str(user.get("id") or sess.user_id)
    sess.email = str(user.get("email") or body.email)
    sess.access_token = data.get("access_token")
    sess.refresh_token = data.get("refresh_token")
    sess.guest_mode = False
    apply_auth(sess)
    db.ensure_user(sess.user_id, language=sess.language, email=sess.email)
    STORE.save(sess)
    return {"ok": True, **sess.public()}


@router.post("/logout")
def logout(sess: SessionDep, response: Response) -> dict:
    STORE.delete(sess.sid)
    db.clear_auth()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}
