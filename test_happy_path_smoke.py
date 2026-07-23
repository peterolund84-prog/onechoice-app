# -*- coding: utf-8 -*-
"""Canonical happy-path smoke test — login → home → food → execute → lista → home."""

from __future__ import annotations

import unittest
from unittest import mock

from streamlit.testing.v1 import AppTest


class HappyPathSmokeTest(unittest.TestCase):
    """End-to-end AppTest: session-safe navigation and auth preserved throughout."""

    def _boot_authenticated(self) -> AppTest:
        with mock.patch("supabase_client.is_configured", return_value=True):
            with mock.patch("auth_cookie.read_auth_cookie", return_value={}):
                with mock.patch("db._use_supabase", return_value=False):
                    at = AppTest.from_file("app.py", default_timeout=120)
                    at.run()
                    at.session_state["access_token"] = "smoke-at"
                    at.session_state["refresh_token"] = "smoke-rt"
                    at.session_state["user_id"] = "uid-smoke"
                    at.session_state["guest_mode"] = False
                    at.session_state["page"] = "home"
                    at.session_state["_auth_cookie_checked"] = True
                    at.session_state["food_meal_type"] = "middag"
                    at.run()
                    return at

    def _assert_authenticated(self, at: AppTest) -> None:
        self.assertNotEqual(at.session_state["page"], "auth")
        self.assertEqual(at.session_state["access_token"], "smoke-at")
        self.assertEqual(at.session_state["user_id"], "uid-smoke")
        self.assertFalse(bool(at.session_state["guest_mode"]))

    def _prime_stale_checkbox_state(self, at: AppTest) -> None:
        """AppTest retains execute checklist widgets across page flips.

        When those widgets are no longer rendered, their keys may be missing
        from session_state; click().run() then KeyErrors while serializing
        widget state. Prime any missing checkbox keys before the next run.
        """
        for cb in list(at.checkbox):
            ck = getattr(cb, "key", None)
            if not isinstance(ck, str) or not ck:
                continue
            try:
                at.session_state[ck]
            except Exception:
                at.session_state[ck] = False

    def _click_nav(self, at: AppTest, target: str) -> None:
        key = f"nav_{target}"
        matches = [b for b in at.button if getattr(b, "key", None) == key]
        if not matches:
            self.fail(
                f"nav button {key!r} not in {[getattr(b, 'key', None) for b in at.button]}"
            )
        self._prime_stale_checkbox_state(at)
        matches[-1].click().run()

    def test_full_happy_path(self) -> None:
        at = self._boot_authenticated()
        self._assert_authenticated(at)

        at.session_state["food_meal_type"] = "middag"
        mat = next(b for b in at.button if (b.label or "") == "Mat")
        mat.click().run()
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "result")

        # Välj → execute directly (no intermediate Handla card)
        go = next(b for b in at.button if (b.label or "") == "Välj")
        go.click().run()
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "execute")
        self.assertTrue(at.session_state["accepted"])
        labels = [b.label or "" for b in at.button]
        self.assertFalse(any("Handla" in lab for lab in labels), labels)

        boxes = list(at.checkbox)
        self.assertGreaterEqual(len(boxes), 3, [getattr(c, "label", None) for c in boxes])
        for i in range(3):
            boxes = list(at.checkbox)
            boxes[i].check().run()
            self.assertEqual(at.session_state["page"], "execute")

        add_btn = next(
            b for b in at.button if b.label and "Lägg till i handlingslista (3)" in b.label
        )
        add_btn.click().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "execute")
        open_btn = next(b for b in at.button if b.label and "Öppna listan" in b.label)
        open_btn.click().run()
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        self.assertEqual(at.session_state["page"], "lista")
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Inköpslista", body)
        self.assertIn("oc-shop-pick-marker", body)
        self.assertIn('data-oc-nav="glass"', body)
        self.assertGreaterEqual(len(at.checkbox), 3)
        self.assertFalse(any((b.label or "").startswith("○") for b in at.button))
        keys = {getattr(b, "key", None) for b in at.button}
        self.assertIn("nav_home", keys)
        self.assertIn("nav_lista", keys)
        self._assert_authenticated(at)
        # Hem navigation covered by test_home_nav_from_execute (AppTest retains
        # stale execute checkbox widgets across page flips in the same tree).

    def test_home_nav_from_execute(self) -> None:
        at = self._boot_authenticated()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self._click_nav(at, "home")
        self.assertFalse(at.exception)
        self._assert_authenticated(at)
        # Nav Hem always opens the domain chooser — never resume the dish.
        self.assertEqual(at.session_state["page"], "home")
        labels = [b.label or "" for b in at.button]
        self.assertIn("Mat", labels)

    def test_home_nav_from_lista_opens_chooser(self) -> None:
        """Lista → Hem must not bounce back to the accepted dish/execute page."""
        at = self._boot_authenticated()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        self._click_nav(at, "lista")
        self.assertEqual(at.session_state["page"], "lista")
        self._click_nav(at, "home")
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["page"], "home")
        labels = [b.label or "" for b in at.button]
        self.assertIn("Mat", labels)
        self.assertNotEqual(at.session_state["page"], "execute")

    def test_nav_chrome_identical_across_pages(self) -> None:
        """Glass nav marker + four nav keys present on home/lista/history/execute."""
        at = self._boot_authenticated()
        pages = ["home", "lista", "history"]
        # Build execute via food path
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        pages.append("execute")

        for page in ("home", "lista", "history", "execute"):
            at.session_state["page"] = page
            if page == "home":
                # Explicit chooser — otherwise accepted food resumes execute
                at.session_state["_force_home_chooser"] = True
            at.run()
            body = " ".join(str(m.value or "") for m in at.markdown)
            self.assertIn('data-oc-nav="glass"', body, page)
            keys = {getattr(b, "key", None) for b in at.button}
            for k in ("nav_home", "nav_lista", "nav_history", "nav_profile"):
                self.assertIn(k, keys, (page, keys))
            from pathlib import Path

            css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
            self.assertIn("backdrop-filter: blur(14px)", css)

    def test_home_redirects_to_execute_when_food_accepted(self) -> None:
        at = self._boot_authenticated()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "execute")
        at.session_state["page"] = "home"
        at.run()
        self.assertEqual(at.session_state["page"], "execute")
        labels = [b.label or "" for b in at.button]
        self.assertNotIn("Mat", labels)
        self.assertFalse(any("Bestäm åt mig" == lab for lab in labels), labels)


class DishManifestTests(unittest.TestCase):
    def test_manifest_covers_taxonomy(self) -> None:
        import food_categories as fcat

        on_disk = fcat.manifest_category_ids()
        expected = fcat.DISH_CATEGORY_SET - {"generic"}
        self.assertTrue(expected.issubset(on_disk))
        for cat in expected:
            path = fcat.dish_image_path(cat)
            self.assertTrue(path.is_file(), cat)
        self.assertFalse(fcat.dish_image_path("generic").is_file())

    def test_no_duplicate_dish_bytes(self) -> None:
        import hashlib
        from pathlib import Path

        import food_categories as fcat

        base = Path(__file__).resolve().parent / "assets" / "dishes"
        by_hash: dict[str, list[str]] = {}
        for p in base.glob("*.jpg"):
            h = hashlib.md5(p.read_bytes()).hexdigest()
            by_hash.setdefault(h, []).append(p.name)
        dups = {h: names for h, names in by_hash.items() if len(names) > 1}
        self.assertEqual(dups, {}, dups)

    def test_local_pack_images_resolve(self) -> None:
        import dish_images as dimg

        dimg.assert_local_packs_resolve()


if __name__ == "__main__":
    unittest.main()
