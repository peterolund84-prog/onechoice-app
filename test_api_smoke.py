# -*- coding: utf-8 -*-
"""FastAPI smoke tests (TestClient) — home, decide, shopping, historik, me."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from api.main import app


class ApiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        cls.uid = "guest-apitest01"

    def test_health(self) -> None:
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "ok")

    def test_home(self) -> None:
        res = self.client.get("/v1/home", params={"language": "sv"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("headline", body)
        self.assertEqual(len(body["domains"]), 6)

    def test_decide_food(self) -> None:
        res = self.client.post(
            "/v1/decide",
            json={
                "question": "",
                "domain_hint": "food",
                "meal_type": "middag",
                "language": "sv",
                "user_id": self.uid,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIn("suggestion", body)
        self.assertEqual(body.get("user_id"), self.uid)

    def test_shopping_roundtrip(self) -> None:
        add = self.client.post(
            "/v1/shopping",
            json={"name": "gul lök", "user_id": self.uid},
        )
        self.assertEqual(add.status_code, 200, add.text)
        item = add.json()["item"]
        self.assertEqual(item["name"], "gul lök")

        listed = self.client.get("/v1/shopping", params={"user_id": self.uid})
        self.assertEqual(listed.status_code, 200)
        ids = [i["id"] for i in listed.json()["items"]]
        self.assertIn(item["id"], ids)

        toggled = self.client.patch(
            f"/v1/shopping/{item['id']}",
            json={"checked": True, "user_id": self.uid},
        )
        self.assertEqual(toggled.status_code, 200)
        self.assertTrue(toggled.json()["item"]["checked"])

        cleared = self.client.request(
            "DELETE",
            "/v1/shopping/checked",
            json={"user_id": self.uid, "item_ids": [item["id"]]},
        )
        self.assertEqual(cleared.status_code, 200)

    def test_me_and_history(self) -> None:
        me = self.client.get("/v1/me", params={"user_id": self.uid})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user_id"], self.uid)

        hist = self.client.get("/v1/decisions", params={"user_id": self.uid})
        self.assertEqual(hist.status_code, 200)
        self.assertIn("items", hist.json())


if __name__ == "__main__":
    unittest.main()
