# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Response

import db
from api.session_store import COOKIE_MAX_AGE, COOKIE_NAME, STORE, Session


def apply_auth(sess: Session) -> None:
    if sess.guest_mode or not sess.access_token:
        db.clear_auth()
    else:
        db.set_auth(sess.access_token, sess.refresh_token)


def get_session(
    response: Response,
    oc_session: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> Session:
    db.init_db()
    sess = STORE.get(oc_session)
    if sess is None:
        sess = STORE.create()
        response.set_cookie(
            key=COOKIE_NAME,
            value=sess.sid,
            max_age=COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/",
        )
    apply_auth(sess)
    return sess


SessionDep = Annotated[Session, Depends(get_session)]
