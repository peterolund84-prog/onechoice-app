# -*- coding: utf-8 -*-
"""Historik editorial filter, date labels, icon-button chrome rule."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import app as app_mod


class HistoryFilterTests(unittest.TestCase):
    def _row(self, *, status: str, suggestion: str, created_at: str, favorite: bool = False):
        return {
            "id": hash((status, suggestion, created_at)) % 10_000_000,
            "status": status,
            "suggestion": suggestion,
            "favorite": favorite,
            "created_at": created_at,
            "domain": "food",
        }

    def test_default_excludes_shown_and_dedupes_same_dish_per_day(self) -> None:
        day = "2026-07-20T15:47:00+02:00"
        day2 = "2026-07-20T18:00:00+02:00"
        rows = [
            self._row(status="shown", suggestion="Pasta", created_at=day),
            self._row(status="accepted", suggestion="Pasta", created_at=day),
            self._row(status="accepted", suggestion="Pasta", created_at=day2),
            self._row(status="locked", suggestion="Tacos", created_at=day),
            self._row(status="rejected", suggestion="Sushi", created_at=day),
        ]
        out = app_mod._filter_history_rows(rows, show_all=False, favorites_only=False)
        titles = [r["suggestion"] for r in out]
        self.assertEqual(titles, ["Pasta", "Tacos"])
        self.assertTrue(all(r["status"] in ("accepted", "locked") for r in out))

    def test_show_all_includes_visat(self) -> None:
        day = "2026-07-20T15:47:00+02:00"
        rows = [
            self._row(status="shown", suggestion="Visat-rätt", created_at=day),
            self._row(status="accepted", suggestion="Gjort", created_at=day),
        ]
        out = app_mod._filter_history_rows(rows, show_all=True, favorites_only=False)
        self.assertEqual([r["suggestion"] for r in out], ["Visat-rätt", "Gjort"])

    def test_favorites_only(self) -> None:
        day = "2026-07-20T15:47:00+02:00"
        rows = [
            self._row(status="accepted", suggestion="A", created_at=day, favorite=True),
            self._row(status="accepted", suggestion="B", created_at=day, favorite=False),
        ]
        out = app_mod._filter_history_rows(rows, show_all=True, favorites_only=True)
        self.assertEqual([r["suggestion"] for r in out], ["A"])


class HistoryDateLabelTests(unittest.TestCase):
    def test_today_yesterday_swedish(self) -> None:
        today = datetime.now(app_mod.APP_LOCAL_TZ).date()
        yesterday = today - timedelta(days=1)
        self.assertEqual(
            app_mod._hist_date_label(today, language="sv"),
            "IDAG",
        )
        self.assertEqual(
            app_mod._hist_date_label(yesterday, language="sv"),
            "IGÅR",
        )

    def test_weekday_month_swedish_upper(self) -> None:
        # Fixed Monday 20 July 2026
        d = date(2026, 7, 20)
        label = app_mod._hist_date_label(d, language="sv")
        self.assertEqual(label, "MÅNDAG 20 JULI")
        self.assertNotIn("2026", label)
        self.assertNotIn("T", label)

    def test_time_meta_no_iso(self) -> None:
        row = {
            "created_at": "2026-07-20T15:47:00+02:00",
            "domain": "food",
        }
        with mock.patch.object(app_mod, "domain_label", return_value="Mat"):
            meta = app_mod._hist_time_meta(row, "sv")
        self.assertEqual(meta, "15:47 · Mat")
        self.assertNotIn("2026-07-20", meta)


class IconButtonCssTests(unittest.TestCase):
    def test_oc_icon_btn_rule_present(self) -> None:
        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn(".oc-icon-btn", src)
        self.assertIn(".oc-icon-btn.active", src)
        self.assertIn("width: 40px", src)
        self.assertIn("oc-icon-btn oc-share-icon-btn", src)
        # Heart chrome stripped via Streamlit key wrappers
        self.assertIn("st-key-hist_fav_", src)
        self.assertIn("st-key-exec_fav_corner", src)
        # Labels visually hidden — glyph only
        self.assertIn("text-indent: -9999px", src)


class HistoryRowPolishTests(unittest.TestCase):
    def test_row_thumb_and_inset_separator_css(self) -> None:
        src = open(app_mod.__file__, encoding="utf-8").read()
        self.assertIn(".oc-row-thumb", src)
        self.assertIn("box-shadow: inset 0 0 0 1px rgba(0,0,0,0.06)", src)
        self.assertIn("padding: 4px 16px", src)
        self.assertIn(".oc-hist-row-main", src)
        self.assertIn("border-bottom: 1px solid var(--oc-border)", src)
        self.assertIn("font-size: 16px", src)
        self.assertIn(".oc-row-thumb-ph", src)
        self.assertIn("data-oc-hist-row", src)
        self.assertIn(".oc-hist-heart-glyph.is-on", src)
        # No plate background on photo thumb
        self.assertNotIn(".oc-hist-thumb", src)

    def test_row_visual_html_is_self_contained(self) -> None:
        html = app_mod._hist_row_visual_html(
            {
                "id": 1,
                "domain": "food",
                "suggestion": "Etiopisk-inspirerad linsgryta",
                "favorite": True,
                "created_at": "2026-07-20T15:47:00+02:00",
                "context": {"dish_category": "linser"},
            },
            is_fav=True,
            last=False,
        )
        self.assertIn('data-oc-hist-row="1"', html)
        self.assertIn("Etiopisk-inspirerad linsgryta", html)
        self.assertIn("oc-hist-heart-glyph is-on", html)
        self.assertIn("display:flex", html)
        self.assertIn("height:64px", html)
        self.assertIn("border-bottom:1px solid", html)
        self.assertIn("oc-row-thumb", html)

    def test_generic_uses_tonal_placeholder_not_photo(self) -> None:
        html = app_mod._hist_thumb_html(
            {"domain": "food", "suggestion": "Något okänt", "context": {}}
        )
        self.assertIn("oc-row-thumb-ph", html)
        self.assertNotIn("data:image/jpeg", html)

        html_movie = app_mod._hist_thumb_html(
            {"domain": "movie", "suggestion": "Inception", "context": {}}
        )
        self.assertIn("oc-row-thumb-ph", html_movie)

    def test_known_category_uses_photo_thumb(self) -> None:
        html = app_mod._hist_thumb_html(
            {
                "domain": "food",
                "suggestion": "Pasta pesto",
                "context": {"dish_category": "pasta"},
            }
        )
        self.assertIn('class="oc-row-thumb"', html)
        self.assertIn("data:image/jpeg", html)
        self.assertNotIn("oc-row-thumb-ph", html)

    def test_dish_assets_meet_brightness_floor(self) -> None:
        from pathlib import Path

        from PIL import Image, ImageStat

        import food_categories as fcat

        base = Path(fcat.dish_image_path("pasta")).parent
        dark = []
        for cat in fcat.DISH_CATEGORIES:
            if cat == "generic":
                continue
            p = base / f"{cat}.jpg"
            if not p.is_file():
                continue
            im = Image.open(p).convert("L").resize((64, 64))
            br = float(ImageStat.Stat(im).mean[0])
            if br < 110:
                dark.append((cat, br))
        self.assertEqual(dark, [], f"dark outliers remain: {dark}")

    def test_manifest_records_style_bar(self) -> None:
        from pathlib import Path

        import food_categories as fcat

        manifest = Path(fcat.dish_image_path("pasta")).parent / "MANIFEST.md"
        text = manifest.read_text(encoding="utf-8")
        self.assertIn("tight crop, food ≥70% of frame, light neutral surface", text)
        self.assertIn("no dark moody shots", text)


class HistoryAppFilterTests(unittest.TestCase):
    def test_default_history_hides_shown_rows(self) -> None:
        from streamlit.testing.v1 import AppTest

        import db

        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("db._use_supabase", return_value=False):
                    at = AppTest.from_file("app.py", default_timeout=120)
                    at.run()
                    uid = "uid-hist-filter"
                    at.session_state["access_token"] = "hist-at"
                    at.session_state["refresh_token"] = "hist-rt"
                    at.session_state["user_id"] = uid
                    at.session_state["guest_mode"] = False
                    at.session_state["_auth_cookie_checked"] = True
                    db._SHOPPING_FORCE_SQLITE = True
                    db._ensure_sqlite_user(uid)
                    shown = db.create_decision(
                        user_id=uid,
                        domain="food",
                        question="test",
                        suggestion="Visat Pasta Wall",
                        justification="x",
                        status="shown",
                        context={"meal_type": "middag"},
                    )
                    accepted = db.create_decision(
                        user_id=uid,
                        domain="food",
                        question="test",
                        suggestion="Accepterad Lax",
                        justification="x",
                        status="accepted",
                        context={"meal_type": "middag"},
                    )
                    at.session_state["page"] = "history"
                    at.session_state["_hist_show_all"] = False
                    at.run()
        self.assertFalse(at.exception)
        keys = {getattr(b, "key", None) for b in at.button}
        self.assertIn(f"hist_open_btn_history_{int(accepted['id'])}", keys)
        self.assertNotIn(f"hist_open_btn_history_{int(shown['id'])}", keys)
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertNotIn("Här ser du beslut", body)
        self.assertIn("Visa alla händelser", " ".join(
            str(getattr(b, "label", "") or "") for b in at.button
        ) + body)
        db._SHOPPING_FORCE_SQLITE = False


if __name__ == "__main__":
    unittest.main()
