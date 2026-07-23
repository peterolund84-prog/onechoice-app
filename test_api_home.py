# -*- coding: utf-8 -*-
"""API home hero — no Streamlit dependency."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from api.home import infer_home_hero


class ApiHomeHeroTests(unittest.TestCase):
    def test_lunch_window_sv(self) -> None:
        now = datetime(2026, 7, 22, 12, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        data = infer_home_hero(now, language="sv")
        self.assertTrue(data["headline"].endswith("?"))
        self.assertEqual(data["domain"], "food")
        self.assertEqual(data["sub"], "Ett tryck — jag tar beslutet.")
        self.assertEqual(data["cta"], "Bestäm åt mig")
        self.assertEqual(len(data["domains"]), 6)
        ids = [d["id"] for d in data["domains"]]
        self.assertEqual(ids, ["food", "clothes", "movie", "workout", "weekend", "fridge"])

    def test_weekend_flag(self) -> None:
        sat = datetime(2026, 7, 25, 10, 0, tzinfo=ZoneInfo("Europe/Stockholm"))
        data = infer_home_hero(sat, language="sv")
        self.assertTrue(data["weekend_alternate"])


if __name__ == "__main__":
    unittest.main()
