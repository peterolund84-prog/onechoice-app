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
        self.assertIn("Vad vill du bestämma?", home.text)
        self.assertNotIn('id="heroCta"', home.text)
        self.assertIn("suggestBox", home.text)
        self.assertIn("/api/home/suggestion", home.text)
        self.assertNotIn("via_router: true", home.text)
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
        self.assertIn("tip", body)
        tip = body["tip"]
        self.assertIn("saknar du en kategori", tip.get("text", "").lower())
        self.assertIn("tipsa oss", tip.get("text", "").lower())

    def test_home_suggestion_box_saves_not_decide(self) -> None:
        self.client.post("/api/auth/guest")
        bad = self.client.post("/api/home/suggestion", json={"text": "x"})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(
            "/api/home/suggestion",
            json={"text": "Podcast som ny kategori"},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        data = ok.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("saved"))
        self.assertIn("Tack", data.get("message", ""))
        # Must not create a decision / navigate into decide flow
        self.assertNotIn("decision", data)
        self.assertNotIn("page", data)

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

    def test_movie_accept_exposes_stream_cta(self) -> None:
        from pathlib import Path

        self.client.post("/api/auth/guest")
        r = self.client.post(
            "/api/decide",
            json={
                "domain_hint": "movie",
                "context_extra": {
                    "format": "film",
                    "mood": "avkopplat",
                    "mode": "mood",
                },
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        data = r.json()
        if data.get("page") != "result":
            self.skipTest("decide did not return result")
        decision = data["decision"]
        self.assertTrue(decision.get("execution_url"))
        self.assertTrue(decision.get("execution_label"))
        pres = decision.get("presentation") or {}
        self.assertTrue(pres.get("execution_url"))
        root = Path(__file__).resolve().parent
        result_html = (root / "web" / "result.html").read_text(encoding="utf-8")
        self.assertIn("data-exec-url", result_html)
        self.assertIn("Titta", result_html)
        js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("shareNative", js)
        self.assertIn("warmShareButton", js)

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

    def test_lista_delete_and_clear_checked(self) -> None:
        self.client.post("/api/auth/guest")
        add = self.client.post("/api/lista/items", json={"name": "Mjölk"})
        self.assertEqual(add.status_code, 200, add.text)
        add2 = self.client.post("/api/lista/items", json={"name": "Bröd"})
        self.assertEqual(add2.status_code, 200, add2.text)
        rows = self.client.get("/api/lista").json()["items"]
        self.assertGreaterEqual(len(rows), 2)
        by_name = {str(r["name"]).lower(): r for r in rows}
        milk = by_name.get("mjölk")
        bread = by_name.get("bröd")
        self.assertIsNotNone(milk)
        self.assertIsNotNone(bread)
        assert milk is not None and bread is not None
        gone = self.client.delete(f"/api/lista/items/{milk['id']}")
        self.assertEqual(gone.status_code, 200, gone.text)
        self.assertTrue(gone.json().get("ok"))
        after = self.client.get("/api/lista").json()["items"]
        self.assertFalse(any(int(r["id"]) == int(milk["id"]) for r in after))
        patched = self.client.patch(
            f"/api/lista/items/{bread['id']}", json={"checked": True}
        )
        self.assertEqual(patched.status_code, 200, patched.text)
        cleared = self.client.post("/api/lista/clear-checked")
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertGreaterEqual(int(cleared.json().get("removed") or 0), 1)
        final = self.client.get("/api/lista").json()["items"]
        self.assertFalse(any(int(r["id"]) == int(bread["id"]) for r in final))

    def test_execute_and_lista_use_glass_blocks(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent
        execute = (root / "web" / "execute.html").read_text(encoding="utf-8")
        lista = (root / "web" / "lista.html").read_text(encoding="utf-8")
        css = (root / "web" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn("glass-block", execute)
        self.assertIn("recipe-steps", execute)
        self.assertIn("glass-block", lista)
        self.assertIn("list-del", lista)
        self.assertIn("clear-checked", lista)
        self.assertIn(".glass-block", css)
        self.assertIn(".list-del", css)

    def test_dish_assets_mounted(self) -> None:
        from pathlib import Path

        dishes = Path(__file__).resolve().parent / "assets" / "dishes"
        sample = next(dishes.glob("*.jpg"), None)
        self.assertIsNotNone(sample)
        r = self.client.get(f"/assets/dishes/{sample.name}")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.content), 100)

    def test_health_assets_and_llm(self) -> None:
        from pathlib import Path

        assets = self.client.get("/health/assets")
        self.assertEqual(assets.status_code, 200)
        body = assets.json()
        self.assertTrue(body["dishes"]["mounted"])
        self.assertTrue(body["posters"]["mounted"])
        self.assertGreater(body["dishes"]["count"], 0)
        self.assertGreaterEqual(body["posters"]["count"], 0)
        self.assertIn("path", body["dishes"])
        self.assertIn("path", body["posters"])

        posters = Path(__file__).resolve().parent / "assets" / "posters"
        sample = next(posters.glob("*.jpg"), None)
        if sample is not None:
            img = self.client.get(f"/assets/posters/{sample.name}")
            self.assertEqual(img.status_code, 200)
            self.assertGreater(len(img.content), 100)

        llm = self.client.get("/api/health/llm")
        self.assertEqual(llm.status_code, 200)
        payload = llm.json()
        self.assertIn("ok", payload)
        self.assertIn("model", payload)
        self.assertIn("detail", payload)

    def test_shared_nav_has_icons(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent
        js = (root / "web" / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("function mountNav", js)
        self.assertIn("NAV_SVGS", js)
        self.assertIn('id="app-nav"', (root / "web" / "index.html").read_text(encoding="utf-8"))
        for name in ("index", "result", "execute", "lista", "history", "profile"):
            html = (root / "web" / f"{name}.html").read_text(encoding="utf-8")
            self.assertIn('id="app-nav"', html, name)
            self.assertNotIn(">Hem</a>", html, name)
        css = (root / "web" / "static" / "app.css").read_text(encoding="utf-8")
        self.assertIn(".chips-scroll", css)
        self.assertIn("movie-poster-ph--compact", css)
        self.assertIn("posterPhHtml", js)
        self.assertIn("mediaUrl", js)
        result = (root / "web" / "result.html").read_text(encoding="utf-8")
        self.assertIn("chips-scroll", result)

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
        self.assertTrue(
            (pres.get("dish_image_url") or "").startswith("/api/media/"),
            msg=pres.get("dish_image_url"),
        )
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

    def test_guest_does_not_wipe_authenticated_session(self) -> None:
        from api.session_store import COOKIE_NAME, STORE

        self.client.post("/api/auth/guest")
        sid = self.client.cookies.get(COOKIE_NAME)
        self.assertTrue(sid)
        sess = STORE.get(sid)
        self.assertIsNotNone(sess)
        assert sess is not None
        sess.guest_mode = False
        sess.access_token = "test-access-token"
        sess.refresh_token = "test-refresh-token"
        sess.email = "user@example.com"
        STORE.save(sess)

        again = self.client.post("/api/auth/guest")
        self.assertEqual(again.status_code, 200)
        body = again.json()
        self.assertFalse(body.get("guest_mode"))
        self.assertTrue(body.get("authenticated"))
        self.assertEqual(body.get("email"), "user@example.com")

    def test_merge_list_empty_selection_adds_nothing(self) -> None:
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
        if data.get("page") != "result":
            self.skipTest("decide did not return result")
        acc = self.client.post("/api/decision/accept", json={"open_execute": True})
        self.assertEqual(acc.status_code, 200, acc.text)
        exe = self.client.get("/api/decision/execute")
        self.assertEqual(exe.status_code, 200, exe.text)
        shopping = (exe.json().get("shopping") or {}).get("to_buy") or {}
        flat = [i for items in shopping.values() for i in (items or [])]
        if not flat:
            self.skipTest("no shopping items to merge")
        merged = self.client.post(
            "/api/decision/execute/merge-list",
            json={"item_names": []},
        )
        self.assertEqual(merged.status_code, 200, merged.text)
        self.assertEqual(merged.json().get("added"), 0)

    def test_history_open_keeps_favorite_and_execution(self) -> None:
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
        if data.get("page") != "result":
            self.skipTest("decide did not return result")
        decision = data["decision"]
        did = decision.get("decision_id")
        if not did:
            self.skipTest("no decision_id")
        self.client.post("/api/decision/favorite")
        opened = self.client.post(f"/api/history/{did}/open")
        self.assertEqual(opened.status_code, 200, opened.text)
        cur = opened.json().get("decision") or {}
        self.assertIn("favorite", cur)
        self.assertTrue(cur.get("favorite"))
        # Food history open should land on execute page
        self.assertEqual(opened.json().get("page"), "execute")

    def test_cta_and_logo_spark_layout(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parent
        css = (root / "web" / "static" / "app.css").read_text(encoding="utf-8")
        html = (root / "web" / "index.html").read_text(encoding="utf-8")
        result = (root / "web" / "result.html").read_text(encoding="utf-8")
        execute = (root / "web" / "execute.html").read_text(encoding="utf-8")
        self.assertIn(".cta-inner", css)
        self.assertIn("flex-direction: row", css)
        self.assertIn("body.page-home", css)
        self.assertIn("body::before", css)
        self.assertIn(".home-logo", css)
        self.assertIn(".home-tile", css)
        self.assertIn('class="page-home"', html)
        self.assertIn("home-logo", html)
        self.assertIn("home-hero.jpg", css)
        self.assertIn("--oc-glass", css)
        self.assertNotIn('id="heroCta"', html)
        self.assertIn("Välj vad du vill ha hjälp med.", html)
        self.assertIn("Saknar du en kategori? Tipsa oss", html)
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
