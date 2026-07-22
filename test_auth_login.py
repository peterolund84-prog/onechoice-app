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

if __name__ == "__main__":
    unittest.main()
