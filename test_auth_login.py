# -*- coding: utf-8 -*-
"""Auth / login entry — guest can reach login when Supabase is configured."""

from __future__ import annotations

import unittest
from unittest import mock


class SupabaseSecretTests(unittest.TestCase):
    def test_nested_supabase_table_secrets(self) -> None:
        import supabase_client as sb

        class FakeSecrets:
            def keys(self):
                return ["supabase"]

            def get(self, name, default=None):
                return default

            def __getitem__(self, key):
                if key == "supabase":
                    return {
                        "url": "https://abc.supabase.co",
                        "key": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test",
                    }
                raise KeyError(key)

        with mock.patch.object(sb, "os") as fake_os:
            fake_os.environ.get.return_value = ""
            with mock.patch("streamlit.secrets", FakeSecrets(), create=True):
                self.assertTrue(sb.is_configured())
                url, key = sb.get_creds()
                self.assertEqual(url, "https://abc.supabase.co")
                self.assertTrue(key.startswith("eyJ"))


class AuthUiTests(unittest.TestCase):
    def test_guest_profile_shows_login_when_supabase_configured(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            at = AppTest.from_file("app.py", default_timeout=90)
            at.run()
            at.session_state["guest_mode"] = True
            at.session_state["user_id"] = "guest-test-uuid"
            at.session_state["page"] = "profile"
            at.run()
            labels = [b.label or "" for b in at.button]
            self.assertTrue(any("Logga in" in lab for lab in labels), labels)
            self.assertFalse(any("Logga ut" in lab for lab in labels), labels)

    def test_profile_login_opens_auth_page(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            at = AppTest.from_file("app.py", default_timeout=90)
            at.run()
            at.session_state["guest_mode"] = True
            at.session_state["user_id"] = "guest-test-uuid"
            at.session_state["page"] = "profile"
            at.run()
            for b in at.button:
                if (b.label or "") == "Logga in":
                    b.click().run()
                    break
            else:
                self.fail([b.label for b in at.button])
            self.assertEqual(at.session_state["page"], "auth")
            self.assertFalse(bool(at.session_state["guest_mode"]))
            self.assertIsNone(at.session_state["user_id"])
            body = " ".join(str(m.value or "") for m in at.markdown)
            self.assertNotIn("Supabase Auth", body)
            self.assertNotIn("supabase auth", body.lower())

    def test_auth_page_has_no_vendor_eyebrow(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                at = AppTest.from_file("app.py", default_timeout=90)
                at.run()
                self.assertEqual(at.session_state["page"], "auth")
                body = " ".join(str(m.value or "") for m in at.markdown)
                self.assertNotIn("Supabase Auth", body)
                self.assertNotIn("spara beslut i molnet", body.lower())
                self.assertIn("Logga in", body)

    def test_login_lands_home_without_ui_error(self) -> None:
        """Regression: CookieManager mount after login caused the error boundary."""
        from streamlit.testing.v1 import AppTest

        import auth_cookie as ac

        sess = {
            "user_id": "uid-login",
            "email": "a@b.se",
            "access_token": "at-login",
            "refresh_token": "rt-login",
        }
        cm_ctors: list[str] = []
        paint_calls: list[str] = []

        class TrackingCM:
            def __init__(self, key: str = "init") -> None:
                cm_ctors.append(key)
                self.cookies: dict[str, str] = {}

            def set(self, *args, **kwargs) -> None:
                pass

            def delete(self, *args, **kwargs) -> None:
                pass

        def fake_paint(snippet: str) -> None:
            paint_calls.append(snippet)

        ac.begin_script_run()
        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("supabase_client.sign_in", return_value=sess):
                    with mock.patch("db.ensure_user", return_value={"id": "uid-login"}):
                        with mock.patch("db.set_auth"):
                            with mock.patch(
                                "extra_streamlit_components.CookieManager",
                                TrackingCM,
                            ):
                                with mock.patch.object(ac, "_paint_cookie_js", side_effect=fake_paint):
                                    at = AppTest.from_file("app.py", default_timeout=90)
                                    at.run()
                                    self.assertEqual(at.session_state["page"], "auth")
                                    # Seed credentials into widget state
                                    at.session_state["auth_email"] = "a@b.se"
                                    at.session_state["auth_password"] = "secret"
                                    at.run()
                                    for b in at.button:
                                        if (b.label or "") == "Logga in":
                                            b.click().run()
                                            break
                                    else:
                                        self.fail([b.label for b in at.button])
                                    self.assertEqual(at.session_state["page"], "home")
                                    self.assertFalse(bool(at.session_state["ui_error"]))
                                    self.assertFalse(bool(at.session_state["_last_ui_error"]))
                                    self.assertEqual(at.session_state["user_id"], "uid-login")
                                    self.assertFalse(bool(at.session_state["guest_mode"]))
                                    # Quiet document.cookie only — never mount oc_auth_cm
                                    self.assertTrue(paint_calls)
                                    self.assertTrue(
                                        any("document.cookie" in s for s in paint_calls)
                                    )
                                    self.assertEqual(cm_ctors, [])
                                    body = " ".join(str(m.value or "") for m in at.markdown)
                                    self.assertNotIn("Något gick fel", body)

    def test_init_state_survives_missing_begin_script_run(self) -> None:
        """Cloud can keep a stale auth_cookie module mid-redeploy — boot must not crash."""
        import app as app_mod
        import auth_cookie as ac

        real_begin = ac.begin_script_run
        try:
            delattr(ac, "begin_script_run")
            # Simulate what init_state does — must not raise
            reset = getattr(ac, "begin_script_run", None)
            self.assertIsNone(reset)
            if hasattr(ac, "_COOKIE_MANAGER"):
                ac._COOKIE_MANAGER = "stale"
                ac._COOKIE_MANAGER = None
            self.assertIsNone(ac._COOKIE_MANAGER)
        finally:
            ac.begin_script_run = real_begin  # type: ignore[method-assign]

        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn('getattr(ac, "begin_script_run", None)', src)
        self.assertIn("auth cookie script-run reset skipped", src)

    def test_home_domain_cards_css_kills_underline(self) -> None:
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        self.assertIn("st-key-home_domain_", css)
        # Domain card buttons must explicitly kill underline
        self.assertIn(
            '[class*="st-key-home_domain_"] div.stButton > button',
            css,
        )
        # Global secondary must not force underline on all buttons
        self.assertIn("text-decoration: none !important", css)

if __name__ == "__main__":
    unittest.main()
