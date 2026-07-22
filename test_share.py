# -*- coding: utf-8 -*-
"""Share copy, public snapshots, list share text, and landing attribution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import share_domain as sd


def _html_blobs(at) -> str:
    """Collect markdown + st.html bodies from an AppTest tree (including columns)."""
    parts: list[str] = []
    for m in at.markdown:
        parts.append(str(getattr(m, "value", None) or ""))

    def walk(block) -> None:
        kids = getattr(block, "children", None)
        if not isinstance(kids, dict):
            return
        for _k, v in kids.items():
            items = v if isinstance(v, list) else [v]
            for it in items:
                proto = getattr(it, "proto", None)
                body = getattr(proto, "body", None) if proto is not None else None
                if body:
                    parts.append(str(body))
                else:
                    try:
                        val = it.value
                    except Exception:
                        val = None
                    if isinstance(val, str):
                        parts.append(val)
                walk(it)

    try:
        walk(at._tree.main)
    except Exception:
        pass
    return "\n".join(parts)


def _assert_share_icon(test: unittest.TestCase, at, *, where: str) -> None:
    body = _html_blobs(at)
    test.assertIn('data-oc-share="icon"', body, where)
    test.assertIn("ocNativeShare", body, where)
    test.assertIn("onclick=", body, where)
    # No floating Dela pills
    labels = [b.label or "" for b in at.button]
    test.assertFalse(
        any(lab.strip() in ("Dela", "↗ Dela", "Share", "Dela listan") for lab in labels),
        labels,
    )


class ShareCopyTests(unittest.TestCase):
    def test_food_frames_app_as_decider_tonight(self) -> None:
        msg = sd.share_message(
            domain="food", suggestion="Kycklingwok med ris", language="sv"
        )
        self.assertIn("OneChoice har bestämt", msg)
        self.assertIn("Kycklingwok med ris", msg)
        self.assertIn("ikväll", msg)
        self.assertTrue(msg.startswith("🍽"))

    def test_workout_frames_app_as_decider(self) -> None:
        msg = sd.share_message(
            domain="workout", suggestion="30 min helkroppsstyrka", language="sv"
        )
        self.assertIn("OneChoice har bestämt", msg)
        self.assertIn("30 min helkroppsstyrka", msg)
        self.assertTrue(msg.startswith("💪"))

    def test_movie_includes_year(self) -> None:
        msg = sd.share_message(
            domain="movie", suggestion="Dune", language="sv", year=2021
        )
        self.assertIn("OneChoice har bestämt", msg)
        self.assertIn("Dune", msg)
        self.assertIn("(2021)", msg)
        self.assertTrue(msg.startswith("🎬"))

    def test_clothes_movie_weekend_same_pattern(self) -> None:
        for domain, emoji in (
            ("clothes", "👕"),
            ("movie", "🎬"),
            ("weekend", "🌿"),
        ):
            msg = sd.share_message(domain=domain, suggestion="X", language="sv")
            self.assertIn("OneChoice har bestämt", msg)
            self.assertTrue(msg.startswith(emoji))

    def test_share_url_has_ref_and_decision_id(self) -> None:
        path = sd.share_path(token="abc123", decision_id=42)
        self.assertIn("share=abc123", path)
        self.assertIn("ref=share", path)
        self.assertIn("decision_id=42", path)

    def test_absolute_share_url_keeps_query_mark(self) -> None:
        url = sd.absolute_share_url(
            "https://onechoice.app", token="tok", decision_id=9
        )
        self.assertTrue(url.startswith("https://onechoice.app/?"))
        self.assertIn("share=tok", url)
        self.assertIn("ref=share", url)


class ListShareFormatTests(unittest.TestCase):
    def test_unchecked_only_grouped_en_dash(self) -> None:
        items = [
            {
                "name": "gul lök",
                "category": "frukt & grönt",
                "checked": False,
            },
            {
                "name": "krossade tomater",
                "category": "frukt & grönt",
                "checked": False,
            },
            {
                "name": "tonfisk",
                "category": "kött & fisk",
                "checked": False,
            },
            {
                "name": "mjölk",
                "category": "mejeri",
                "checked": True,
            },
        ]
        text = sd.format_list_share_text(items, language="sv")
        self.assertTrue(text.startswith("🛒 Inköpslista (OneChoice)"))
        self.assertIn("FRUKT & GRÖNT", text)
        self.assertIn("– gul lök", text)
        self.assertIn("– krossade tomater", text)
        self.assertIn("KÖTT & FISK", text)
        self.assertIn("– tonfisk", text)
        self.assertNotIn("mjölk", text)
        self.assertNotIn("MEJERI", text)

    def test_empty_list_message(self) -> None:
        text = sd.format_list_share_text([], language="sv")
        self.assertIn("Inköpslista", text)
        self.assertIn("tom", text.lower())


class PublicShareDbTests(unittest.TestCase):
    def test_ensure_and_open_logs_attribution(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        decision = db.create_decision(
            user_id=user["id"],
            domain="food",
            question="Vad äter vi?",
            suggestion="Tacos",
            justification="Snabb vardag",
            status="accepted",
            context={
                "shopping": {"store": "", "to_buy": {"Kött": ["köttfärs"]}},
                "recipe": {"active_minutes": 20, "steps": ["Stek"]},
            },
            path=path,
        )
        share = db.ensure_public_share(
            {
                "decision_id": decision["id"],
                "domain": "food",
                "suggestion": "Tacos",
                "justification": "Snabb vardag",
                "context": decision.get("context") or {},
            },
            language="sv",
            path=path,
        )
        self.assertTrue(share["token"])
        loaded = db.get_public_share(share["token"], path=path)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded["payload"]["suggestion"], "Tacos")
        self.assertIn("shopping", loaded["payload"]["context"])

        db.log_share_open(
            share["token"], decision_id=decision["id"], ref="share", path=path
        )
        self.assertEqual(db.count_share_opens(share["token"], path=path), 1)
        again = db.ensure_public_share(
            {
                "decision_id": decision["id"],
                "domain": "food",
                "suggestion": "Tacos",
                "justification": "Snabb vardag",
                "context": {},
            },
            language="sv",
            path=path,
        )
        self.assertEqual(again["token"], share["token"])
        tmp.cleanup()

    def test_list_share_counter_bumps(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "t.db")
        db.init_db(path)
        user = db.ensure_user(language="sv", path=path)
        n1 = db.record_list_share(user["id"], path=path)
        n2 = db.record_list_share(user["id"], path=path)
        n3 = db.record_list_share(user["id"], path=path)
        self.assertEqual(n1, 1)
        self.assertEqual(n2, 2)
        self.assertEqual(n3, 3)
        tmp.cleanup()


class ShareLandingUiTests(unittest.TestCase):
    def test_shared_page_renders_cta_and_logs_open(self) -> None:
        from streamlit.testing.v1 import AppTest

        tmp = tempfile.TemporaryDirectory()
        path = str(Path(tmp.name) / "share.db")
        db.init_db(path)
        orig = db.DB_PATH
        db.DB_PATH = Path(path)
        try:
            share = db.ensure_public_share(
                {
                    "decision_id": 7,
                    "domain": "workout",
                    "suggestion": "30 min helkroppsstyrka",
                    "justification": "Ett pass, klart.",
                    "execution_type": "workout",
                    "context": {
                        "workout": {
                            "title": "Helkropp",
                            "blocks": [
                                {
                                    "name": "Squats",
                                    "type": "reps",
                                    "sets": 3,
                                    "reps": 10,
                                    "rest_seconds": 30,
                                }
                            ],
                        },
                        "execution_detail": "30 min · 1 block",
                    },
                },
                language="sv",
                path=path,
            )
            at = AppTest.from_file("app.py", default_timeout=45)
            at.query_params["share"] = share["token"]
            at.query_params["ref"] = "share"
            at.query_params["decision_id"] = "7"
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(at.session_state["page"], "shared")
            body = " ".join(str(m.value or "") for m in at.markdown)
            self.assertIn("30 min helkroppsstyrka", body)
            self.assertIn('data-oc-share="landing"', body)
            # Landing has no bottom nav chrome
            self.assertNotIn('data-oc-nav="glass"', body)
            labels = [b.label or "" for b in at.button]
            self.assertTrue(
                any("OneChoice" in lab for lab in labels),
                labels,
            )
            self.assertGreaterEqual(db.count_share_opens(share["token"], path=path), 1)
        finally:
            db.DB_PATH = orig
            tmp.cleanup()

    def test_lock_card_exposes_share_after_accept(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.query_params["domain"] = "workout"
        at.run()
        for b in at.button:
            if "Starta" in (b.label or ""):
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        _assert_share_icon(self, at, where="execute")
        # Back to locked result
        for b in at.button:
            if (b.label or "") in ("Tillbaka", "Back"):
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "result")
        self.assertTrue(at.session_state["accepted"])
        cur = at.session_state["current"] or {}
        did = cur.get("decision_id") or at.session_state["decision_id"]
        self.assertIsNotNone(did)
        share = db.ensure_public_share(dict(cur), language="sv")
        self.assertTrue(share.get("token"))
        self.assertIn("ref=share", sd.share_path(token=share["token"], decision_id=did))
        _assert_share_icon(self, at, where="lock card")

    def test_food_decision_and_execute_expose_share(self) -> None:
        from streamlit.testing.v1 import AppTest

        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("db._use_supabase", return_value=False):
                    at = AppTest.from_file("app.py", default_timeout=90)
                    at.run()
                    at.session_state["access_token"] = "share-at"
                    at.session_state["refresh_token"] = "share-rt"
                    at.session_state["user_id"] = "uid-share-food"
                    at.session_state["guest_mode"] = False
                    at.session_state["page"] = "home"
                    at.session_state["_auth_cookie_checked"] = True
                    at.session_state["food_meal_type"] = "middag"
                    at.run()
        mat = next(b for b in at.button if (b.label or "") == "Mat")
        mat.click().run()
        self.assertEqual(at.session_state["page"], "result")
        _assert_share_icon(self, at, where="food decision")
        go = next(b for b in at.button if (b.label or "") == "Gör det")
        go.click().run()
        self.assertEqual(at.session_state["page"], "execute")
        _assert_share_icon(self, at, where="food execute")

    def test_lista_exposes_share_list_when_items_present(self) -> None:
        from streamlit.testing.v1 import AppTest

        db.init_db()
        db._SHOPPING_FORCE_SQLITE = True
        uid = "uid-share-lista"
        db._ensure_sqlite_user(uid)
        with db.get_conn() as conn:
            conn.execute("DELETE FROM shopping_items WHERE user_id = ?", (uid,))
        db.upsert_shopping_item(uid, "banan", "frukt & grönt")
        db.upsert_shopping_item(uid, "mjölk", "mejeri")
        try:
            with mock.patch("supabase_client.is_configured", return_value=True):
                with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                    with mock.patch("db._use_supabase", return_value=False):
                        at = AppTest.from_file("app.py", default_timeout=90)
                        at.run()
                        at.session_state["access_token"] = "lista-share-at"
                        at.session_state["refresh_token"] = "lista-share-rt"
                        at.session_state["user_id"] = uid
                        at.session_state["guest_mode"] = False
                        at.session_state["page"] = "lista"
                        at.session_state["_auth_cookie_checked"] = True
                        at.session_state["shopping_list_cache"] = None
                        at.run()
            body = _html_blobs(at)
            self.assertIn('data-oc-share="icon"', body)
            self.assertIn('data-oc-share-key="lista_share"', body)
            self.assertIn("ocNativeShare", body)
            self.assertIn("navigator.share", body)
        finally:
            db._SHOPPING_FORCE_SQLITE = False

    def test_share_button_html_is_sync_onclick_not_streamlit_button(self) -> None:
        import app as app_mod

        html_btn = app_mod._share_icon_button_html(
            title="OneChoice",
            text="🍽 OneChoice har bestämt: X ikväll",
            url="?share=tok&ref=share&decision_id=1",
            key="unit",
        )
        self.assertIn('data-oc-share="icon"', html_btn)
        self.assertIn("onclick=", html_btn)
        self.assertIn("ocNativeShare", html_btn)
        self.assertIn("oc-share-icon-btn", html_btn)
        runtime = app_mod._oc_share_runtime_html()
        self.assertIn("navigator.share", runtime)
        self.assertIn("oc-share-toast", runtime)
        self.assertIn("web-share", runtime)


if __name__ == "__main__":
    unittest.main()
