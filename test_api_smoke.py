# -*- coding: utf-8 -*-
"""FastAPI smoke tests (TestClient)."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_health(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_home(self) -> None:
        res = self.client.get("/v1/home", params={"language": "sv"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("headline", body)
        self.assertIn("domains", body)
        self.assertEqual(len(body["domains"]), 6)

    def test_decide_food(self) -> None:
        res = self.client.post(
            "/v1/decide",
            json={
                "question": "",
                "domain_hint": "food",
                "meal_type": "middag",
                "language": "sv",
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIn("suggestion", body)
        self.assertTrue(body.get("ok") or body.get("refused") or body.get("ui_message"))


if __name__ == "__main__":
    unittest.main()
