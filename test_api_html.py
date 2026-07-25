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
            cur = self.client.get("/api/decision/current")
            self.assertEqual(cur.status_code, 200)
            acc = self.client.post(
                "/api/decision/accept", json={"open_execute": True}
            )
            self.assertEqual(acc.status_code, 200)
            self.assertEqual(acc.json()["page"], "execute")
            ex = self.client.get("/api/decision/execute")
            self.assertEqual(ex.status_code, 200)

    def test_lista_and_profile(self) -> None:
        self.client.post("/api/auth/guest")
        lista = self.client.get("/api/lista")
        self.assertEqual(lista.status_code, 200)
        self.assertIn("items", lista.json())
        prof = self.client.get("/api/profile")
        self.assertEqual(prof.status_code, 200)
        self.assertIn("html+fastapi", prof.json()["stack"])
        self.assertIn("ai_status", prof.json())

    def test_cta_stack_centered_in_css(self) -> None:
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "web" / "static" / "app.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".cta {", css)
        self.assertIn("align-items: center", css)
        self.assertIn("justify-content: center", css)
        self.assertIn(".cta-stack", css)
        self.assertIn("text-align: center", css)
        html = (Path(__file__).resolve().parent / "web" / "index.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("cta-stack", html)
        self.assertIn("cta-spark-wrap", html)
        self.assertIn("cta-title", html)
        self.assertIn("cta-sub", html)


if __name__ == "__main__":
    unittest.main()
