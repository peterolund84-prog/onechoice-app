# -*- coding: utf-8 -*-
"""Auth cookie persistence + boot login gate."""

from __future__ import annotations

import unittest
from unittest import mock


class AuthCookieUnitTests(unittest.TestCase):
    def test_encode_decode_roundtrip(self) -> None:
        import auth_cookie as ac

        raw = ac._encode({"at": "access", "rt": "refresh"})
        parsed = ac._decode(raw)
        self.assertEqual(parsed, {"at": "access", "rt": "refresh"})

    def test_get_cookie_manager_reuses_within_script_ctx(self) -> None:
        import auth_cookie as ac

        ac._COOKIE_MANAGER = None
        ac._COOKIE_MANAGER_CTX_ID = None
        calls: list[str] = []

        class FakeCM:
            cookies: dict[str, str] = {}

            def __init__(self, key: str = "init") -> None:
                calls.append(key)

        with mock.patch("extra_streamlit_components.CookieManager", FakeCM):
            with mock.patch.object(ac, "_script_ctx_id", return_value=101):
                m1 = ac.get_cookie_manager()
                m2 = ac.get_cookie_manager()
        self.assertIs(m1, m2)
        self.assertEqual(calls, [ac.COOKIE_COMPONENT_KEY])

    def test_get_cookie_manager_remounts_on_new_script_ctx(self) -> None:
        import auth_cookie as ac

        ac._COOKIE_MANAGER = None
        ac._COOKIE_MANAGER_CTX_ID = None
        calls: list[str] = []

        class FakeCM:
            cookies: dict[str, str] = {}

            def __init__(self, key: str = "init") -> None:
                calls.append(key)

        with mock.patch("extra_streamlit_components.CookieManager", FakeCM):
            with mock.patch.object(ac, "_script_ctx_id", side_effect=[1, 2]):
                m1 = ac.get_cookie_manager()
                m2 = ac.get_cookie_manager()
        self.assertIsNot(m1, m2)
        self.assertEqual(calls, [ac.COOKIE_COMPONENT_KEY, ac.COOKIE_COMPONENT_KEY])

    def test_quiet_set_auth_cookie_skips_component_set(self) -> None:
        import auth_cookie as ac

        ac._COOKIE_MANAGER = None
        ac._COOKIE_MANAGER_CTX_ID = None
        set_calls: list[str] = []

        class FakeCM:
            def __init__(self, key: str = "init") -> None:
                self.cookies: dict[str, str] = {}

            def set(self, *args, **kwargs) -> None:
                set_calls.append("set")

        with mock.patch("extra_streamlit_components.CookieManager", FakeCM):
            with mock.patch.object(ac, "_script_ctx_id", return_value=7):
                with mock.patch.object(ac, "_paint_cookie_js") as paint:
                    ac.set_auth_cookie("at", "rt", quiet=True)
        self.assertEqual(set_calls, [])
        paint.assert_called_once()
        snippet = paint.call_args[0][0]
        self.assertIn("document.cookie", snippet)
        self.assertIn(ac.COOKIE_NAME, snippet)

    def test_read_auth_cookie_uses_init_cookies_not_get_all(self) -> None:
        import auth_cookie as ac
        import streamlit as st

        ac._COOKIE_MANAGER = None
        ac._COOKIE_MANAGER_CTX_ID = None
        payload = ac._encode({"at": "a", "rt": "r"})
        st.session_state["_oc_cookie_component_ready"] = True

        class FakeCM:
            def __init__(self, key: str = "init") -> None:
                self.cookies = {ac.COOKIE_NAME: payload}
                self.get_all_calls = 0

            def get_all(self, key: str = "get_all") -> dict[str, str]:
                self.get_all_calls += 1
                return self.cookies

        with mock.patch("extra_streamlit_components.CookieManager", FakeCM):
            with mock.patch.object(ac, "_script_ctx_id", return_value=3):
                out = ac.read_auth_cookie()
                self.assertEqual(out, {"at": "a", "rt": "r"})
                self.assertEqual(ac.get_cookie_manager().get_all_calls, 0)

    def test_read_auth_cookie_waits_one_frame(self) -> None:
        import auth_cookie as ac
        import streamlit as st

        ac._COOKIE_MANAGER = None
        ac._COOKIE_MANAGER_CTX_ID = None

        class FakeCM:
            def __init__(self, key: str = "init") -> None:
                self.cookies = {}

        # Fresh session flag
        if "_oc_cookie_component_ready" in st.session_state:
            del st.session_state["_oc_cookie_component_ready"]

        with mock.patch("extra_streamlit_components.CookieManager", FakeCM):
            with mock.patch.object(ac, "_script_ctx_id", return_value=9):
                first = ac.read_auth_cookie()
                second = ac.read_auth_cookie()
        self.assertIsNone(first)
        self.assertEqual(second, {})

    def test_refresh_session_wrapper(self) -> None:
        import supabase_client as sb

        class FakeSession:
            access_token = "new_at"
            refresh_token = "new_rt"

        class FakeUser:
            id = "user-1"
            email = "a@b.se"

        class FakeRes:
            user = FakeUser()
            session = FakeSession()

        class FakeAuth:
            def refresh_session(self, refresh_token=None):
                self.got = refresh_token
                return FakeRes()

        class FakeClient:
            auth = FakeAuth()

        with mock.patch.object(sb, "get_client", return_value=FakeClient()):
            out = sb.refresh_session("old_rt")
        self.assertEqual(out["user_id"], "user-1")
        self.assertEqual(out["access_token"], "new_at")


class AuthBootTests(unittest.TestCase):
    def test_boot_unauthenticated_shows_login_when_supabase_on(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                at = AppTest.from_file("app.py", default_timeout=90)
                at.run()
                self.assertEqual(at.session_state["page"], "auth")
                labels = [b.label or "" for b in at.button]
                self.assertTrue(any("Logga in" in lab for lab in labels), labels)
                self.assertTrue(any("gäst" in lab.lower() for lab in labels), labels)

    def test_try_restore_applies_session_from_cookie(self) -> None:
        import app as app_mod

        sess = {
            "user_id": "uid-42",
            "email": "test@example.com",
            "access_token": "at",
            "refresh_token": "rt",
        }
        ss: dict = {
            "language": "sv",
            "_auth_cookie_checked": False,
            "guest_mode": False,
        }
        with mock.patch.object(app_mod, "st") as st_mod:
            st_mod.session_state = ss
            with mock.patch.object(app_mod, "_guest_query_active", return_value=False):
                with mock.patch.object(app_mod, "db"):
                    with mock.patch("supabase_client.is_configured", return_value=True):
                        with mock.patch(
                            "auth_cookie.read_auth_cookie",
                            return_value={"at": "at", "rt": "rt"},
                        ):
                            with mock.patch(
                                "supabase_client.refresh_session", return_value=sess
                            ):
                                with mock.patch(
                                    "app._apply_auth_session"
                                ) as apply:
                                    waiting = app_mod._try_restore_auth_from_cookie()
        self.assertFalse(waiting)
        apply.assert_called_once_with(sess, persist_cookie="quiet")

    def test_domain_query_on_auth_page_does_not_bypass_login(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                at = AppTest.from_file("app.py", default_timeout=90)
                at.query_params["domain"] = "food"
                at.run()
                self.assertEqual(at.session_state["page"], "auth")

    def test_home_domain_click_preserves_auth(self) -> None:
        """Regression: domain taps must not wipe Supabase session (no anchor reload)."""
        from streamlit.testing.v1 import AppTest

        fake_decision = mock.MagicMock()
        fake_decision.ok = True
        fake_decision.domain = "food"
        fake_decision.decision_id = "dec-1"
        fake_decision.route_log_id = None
        fake_decision.needs_domain_pick = False
        fake_decision.ui_message = None
        fake_decision.refused = False
        fake_decision.to_dict.return_value = {
            "domain": "food",
            "suggestion": "Test",
            "justification": "test",
            "decision_id": "dec-1",
            "context": {},
        }
        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("db.ensure_user", return_value={"user_id": "uid-1"}):
                    with mock.patch("db.set_auth"):
                        with mock.patch("pipeline.decide", return_value=fake_decision):
                            at = AppTest.from_file("app.py", default_timeout=90)
                            at.run()
                            at.session_state["access_token"] = "at"
                            at.session_state["refresh_token"] = "rt"
                            at.session_state["user_id"] = "uid-1"
                            at.session_state["guest_mode"] = False
                            at.session_state["page"] = "home"
                            at.session_state["_auth_cookie_checked"] = True
                            at.run()
                            mat = next(b for b in at.button if b.label == "Mat")
                            mat.click().run()
                            self.assertNotEqual(at.session_state["page"], "auth")
                            self.assertEqual(at.session_state["access_token"], "at")
                            self.assertEqual(at.session_state["user_id"], "uid-1")


if __name__ == "__main__":
    unittest.main()
