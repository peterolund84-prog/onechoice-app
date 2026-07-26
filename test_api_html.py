# -*- coding: utf-8 -*-
"""HTML + FastAPI stack — smoke tests for MVP routes."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class ApiHtmlSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health_and_home_html(self) -> None:
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["stack"], "html+fastapi")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("OneChoice", home.text)
        self.assertIn("Bestäm åt mig", home.text)
        self.assertIn("/static/app.css", home.text)
        api_home = self.client.get("/api/home")
        self.assertEqual(api_home.status_code, 200)
        self.assertEqual(
            api_home.json()["hero"]["headline"],
            "Vad ska vi bestämma idag?",
        )

    def test_session_guest_and_home_api(self) -> None:
        g = self.client.post("/api/auth/guest")
        self.assertEqual(g.status_code, 200)
        self.assertTrue(g.json()["guest_mode"])
        h = self.client.get("/api/home")
        self.assertEqual(h.status_code, 200)
        body = h.json()
        self.assertIn("hero", body)
        self.assertEqual(len(body["domains"]), 6)
        self.assertEqual(body["domains"][0]["id"], "food")

    def test_decide_food_returns_result(self) -> None:
        self.client.post("/api/auth/guest")
        r = self.client.post(
            "/api/decide",
            json={
                "domain_hint": "food",
                "context_extra": {"meal_type": "middag"},
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        self.assertIn(data["page"], ("result", "refused", "not_a_decision"))
        self.assertIsNotNone(data.get("decision"))
        if data["page"] == "result":
            self.assertTrue(data["decision"].get("suggestion"))
            pres = data["decision"].get("presentation") or {}
            self.assertIn("dish_image_url", pres)
            self.assertIn("food_meta", pres)
            cur = self.client.get("/api/decision/current")
            self.assertEqual(cur.status_code, 200)
            acc = self.client.post(
                "/api/decision/accept", json={"open_execute": True}
            )
            self.assertEqual(acc.status_code, 200)
            self.assertEqual(acc.json()["page"], "execute")
            ex = self.client.get("/api/decision/execute")
            self.assertEqual(ex.status_code, 200)
            self.assertIn("nutrition", ex.json())

    def test_lista_and_profile(self) -> None:
        self.client.post("/api/auth/guest")
        lista = self.client.get("/api/lista")
        self.assertEqual(lista.status_code, 200)
        self.assertIn("items", lista.json())
        prof = self.client.get("/api/profile")
        self.assertEqual(prof.status_code, 200)
        self.assertIn("html+fastapi", prof.json()["stack"])
        self.assertIn("ai_status", prof.json())
        self.assertIn("supabase_configured", prof.json())
        self.assertIn("tmdb_configured", prof.json())
        self.assertIn("integrations", prof.json())
        self.assertIn("secrets", prof.json())
        self.assertIn("secrets_file_found", prof.json()["secrets"])
        sess = self.client.get("/api/auth/session")
        self.assertEqual(sess.status_code, 200)
        self.assertIn("secrets", sess.json())

    def test_dish_assets_mounted(self) -> None:
        from pathlib import Path

        dishes = Path(__file__).resolve().parent / "assets" / "dishes"
        sample = next(dishes.glob("*.jpg"), None)
        self.assertIsNotNone(sample)
        r = self.client.get(f"/assets/dishes/{sample.name}")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 100)

    def test_icon_buttons_have_visible_chip_styles(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent
        css = (root / "web" / "static" / "app.css").read_text(encoding="utf-8")
        js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
        html = (root / "web" / "result.html").read_text(encoding="utf-8")
        self.assertIn(".card-actions-bar", css)
        self.assertIn("background: #111118", css)
        self.assertIn("HEART_SVG", js)
        self.assertIn("card-actions-bar", js)
        self.assertIn("app.css?v=", html)
        self.assertIn("app.js?v=", html)

    def test_media_api_and_share_favorite(self) -> None:
        self.client.post("/api/auth/guest")
        media = self.client.get(
            "/api/media/dish",
            params={"title": "Kycklingwok med ris"},
        )
        self.assertEqual(media.status_code, 200, media.text)
        self.assertGreater(len(media.content), 100)
        self.assertIn("image", media.headers.get("content-type", ""))

        r = self.client.post(
            "/api/decide",
            json={
                "domain_hint": "food",
                "context_extra": {"meal_type": "middag"},
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        if data.get("page") != "result":
            self.skipTest("decide did not return result")
        decision = data["decision"]
        pres = decision.get("presentation") or {}
        self.assertTrue(pres.get("dish_image_url", "").startswith("/api/media/dish"))
        img = self.client.get(pres["dish_image_url"])
        self.assertEqual(img.status_code, 200)
        self.assertIn("share_text", pres)

        did = decision.get("decision_id") or (pres.get("decision_id"))
        if did:
            fav = self.client.post("/api/decision/favorite")
            self.assertEqual(fav.status_code, 200, fav.text)
            self.assertIn("favorite", fav.json())
            share = self.client.get("/api/decision/share")
            self.assertEqual(share.status_code, 200, share.text)
            self.assertTrue(share.json().get("text"))
            self.assertIn("/share", share.json().get("url", ""))
            token = share.json().get("token")
            if token:
                pub = self.client.get(f"/api/share/{token}")
                self.assertEqual(pub.status_code, 200)
                landing = self.client.get("/share")
                self.assertEqual(landing.status_code, 200)

    def test_cta_and_logo_spark_layout(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent
        css = (root / "web" / "static" / "app.css").read_text(encoding="utf-8")
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        result = (root / "web" / "result.html").read_text(encoding="utf-8")
        execute = (root / "web" / "execute.html").read_text(encoding="utf-8")
        self.assertIn(".cta-inner", css)
        self.assertIn("flex-direction: row", css)
        self.assertIn(".logo-i", css)
        self.assertIn('class="logo-i"', html)
        self.assertIn("cta-inner", html)
        js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("food-img", result)
        self.assertIn("movie-poster", result)
        self.assertIn("cardActionsHtml", result)
        self.assertIn("bindCardActions", result)
        self.assertIn("cardActionsHtml", execute)
        self.assertIn('id="favBtn"', js)
        self.assertIn('id="shareBtn"', js)
        self.assertIn("nut-stats", execute)
        self.assertIn("presentation", result)


if __name__ == "__main__":
    unittest.main()
