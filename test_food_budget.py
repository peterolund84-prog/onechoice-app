# -*- coding: utf-8 -*-
"""Food meal budget: constraint + recipe-only ca cost display."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import feasibility
import food_budget as fbud
import pipeline
from fastapi.testclient import TestClient

from api.main import app
from api.presentation import enrich_decision


class FoodBudgetUnitTests(unittest.TestCase):
    def test_ceilings_and_labels(self) -> None:
        self.assertIsNone(fbud.ceiling_sek("any"))
        self.assertEqual(fbud.ceiling_sek("billigt"), 45)
        self.assertEqual(fbud.ceiling_sek("snålt"), 30)
        self.assertTrue(fbud.format_cost_label(48).startswith("ca "))
        self.assertEqual(fbud.round_cost_sek(48), 50)
        self.assertEqual(fbud.round_cost_sek(47), 45)

    def test_ensure_recipe_cost_single_field(self) -> None:
        recipe = fbud.ensure_recipe_cost(
            {
                "title": "Kycklingwok",
                "ingredients": ["kycklingfilé", "broccoli", "ris", "sojasås"],
                "portioner": 2,
            }
        )
        self.assertIn("cost_per_portion_sek", recipe)
        self.assertEqual(recipe["cost_per_portion_sek"] % 5, 0)
        self.assertEqual(recipe.get("cost_label"), "ca")


class FoodBudgetFeasibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_snalt_excludes_over_ceiling(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"meal_budget": "snalt", "meal_type": "middag"},
        )
        self.assertEqual(profile["food"]["meal_budget"], "snalt")
        expensive = {
            "suggestion": "Lyxig laxkväll",
            "justification": "Dyrt.",
            "meta": {
                "meal_type": "middag",
                "active_minutes": 25,
                "ingredients": ["lax", "grädde", "parmesan", "avokado"],
                "cost_per_portion_sek": 80,
            },
        }
        cheap = {
            "suggestion": "Äggröra med knäcke",
            "justification": "Billigt.",
            "meta": {
                "meal_type": "middag",
                "active_minutes": 10,
                "ingredients": ["ägg", "smör", "knäckebröd"],
                "cost_per_portion_sek": 20,
                "assume_at_home_only": True,
            },
        }
        r_bad = feasibility.feasibility_check(
            expensive, domain="food", profile=profile, context={"meal_type": "middag"}
        )
        r_ok = feasibility.feasibility_check(
            cheap, domain="food", profile=profile, context={"meal_type": "middag"}
        )
        self.assertFalse(r_bad.ok)
        self.assertIn("over_budget", r_bad.reasons)
        self.assertTrue(r_ok.ok, msg=r_ok.reasons)

    def test_cost_stored_on_accepted_decision_context(self) -> None:
        db.update_user(
            self.user["id"],
            profile_json={"food": {"meal_budget": "billigt", "show_nutrition": True}},
            path=self.path,
        )
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=self.path,
            context_extra={"meal_type": "middag", "meal_budget": "billigt"},
            grok_api_key="",
        )
        self.assertTrue(r.ok, msg=r.refusal_message)
        ctx = r.context or {}
        # Field present for week-planning later
        self.assertIn("cost_per_portion_sek", ctx)
        cost = ctx.get("cost_per_portion_sek")
        if cost is not None:
            self.assertEqual(int(cost) % 5, 0)
            self.assertLessEqual(int(cost), 45)
        self.assertEqual(ctx.get("meal_budget"), "billigt")
        recipe = ctx.get("recipe") or {}
        if isinstance(recipe, dict) and recipe:
            self.assertIn("cost_per_portion_sek", recipe)


class FoodBudgetApiUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_profile_budget_patch_and_options(self) -> None:
        self.client.post("/api/auth/guest")
        p = self.client.get("/api/profile")
        self.assertEqual(p.status_code, 200)
        body = p.json()
        self.assertIn("food", body)
        self.assertEqual(body["food"]["meal_budget"], "any")
        patched = self.client.patch("/api/profile", json={"meal_budget": "snålt"})
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertEqual(patched.json()["meal_budget"], "snalt")
        again = self.client.get("/api/profile").json()
        self.assertEqual(again["meal_budget"], "snalt")

    def test_cost_on_execute_not_on_decision_presentation(self) -> None:
        self.client.post("/api/auth/guest")
        self.client.patch("/api/profile", json={"meal_budget": "billigt"})
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
        self.assertIsNone(pres.get("cost"))
        # Decision card must not surface cost fields in HTML result template
        from pathlib import Path

        result_html = (Path(__file__).resolve().parent / "web" / "result.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("cost.label", result_html)
        self.assertNotIn("show_cost", result_html)
        self.assertNotIn("/ PORTION", result_html)

        acc = self.client.post("/api/decision/accept", json={"open_execute": True})
        self.assertEqual(acc.status_code, 200, acc.text)
        exe = self.client.get("/api/decision/execute")
        self.assertEqual(exe.status_code, 200, exe.text)
        body = exe.json()
        self.assertTrue(body.get("show_cost"))
        cost = body.get("cost") or {}
        self.assertIn("sek", cost)
        self.assertTrue(str(cost.get("label") or "").startswith("ca "))
        recipe = body.get("recipe") or {}
        self.assertIn("cost_per_portion_sek", recipe)

        # enrich_decision must never put cost on presentation for the card
        enriched = enrich_decision(decision, language="sv") or {}
        self.assertIsNone((enriched.get("presentation") or {}).get("cost"))

    def test_execute_html_renders_ca_cost_stat(self) -> None:
        from pathlib import Path

        html = (Path(__file__).resolve().parent / "web" / "execute.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("show_cost", html)
        self.assertIn("cost.label", html)
        self.assertIn("/ PORTION", html)


if __name__ == "__main__":
    unittest.main()
