# -*- coding: utf-8 -*-
"""AI dish image search + fallback chain + used-amount cost sanity."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import food_budget as fbud
import food_image_search as fis
from api.presentation import dish_image_url, enrich_decision


class FoodImageSearchUnitTests(unittest.TestCase):
    def tearDown(self) -> None:
        fis.set_search_override(None)
        fis.reset_ai_image_search_state()

    def test_extract_markdown_image_urls(self) -> None:
        text = "Here ![dish](https://images.unsplash.com/photo-x.jpg) and done"
        urls = fis.extract_markdown_image_urls(text)
        self.assertEqual(urls[0], "https://images.unsplash.com/photo-x.jpg")

    def test_ai_source_when_search_returns_validated_url(self) -> None:
        remote = "https://images.unsplash.com/photo-omelette.jpg"

        def _fake(_title: str) -> str | None:
            return remote

        fis.set_search_override(_fake)
        with patch.object(fis, "validate_image_url", return_value=True):
            resolved = fis.resolve_food_image(
                "Proteinomelett med frukt",
                "omelett",
                api_key="xai-test",
                use_cache=False,
            )
        self.assertEqual(resolved["source"], "ai")
        self.assertEqual(resolved["remote_url"], remote)
        self.assertTrue(resolved["url"].startswith("/api/media/food?url="))

    def test_fallback_local_when_ai_misses(self) -> None:
        fis.set_search_override(lambda _t: None)
        resolved = fis.resolve_food_image(
            "Spaghetti carbonara",
            "pasta",
            api_key="xai-test",
            use_cache=False,
        )
        self.assertEqual(resolved["source"], "local")
        self.assertTrue(resolved["url"].startswith("/api/media/dish?"))

    def test_placeholder_when_no_ai_no_local(self) -> None:
        fis.set_search_override(lambda _t: None)
        resolved = fis.resolve_food_image(
            "Xylophone nebula special",
            None,
            api_key="xai-test",
            use_cache=False,
        )
        self.assertEqual(resolved["source"], "placeholder")
        self.assertIsNone(resolved["url"])

    def test_recipe_image_url_preferred(self) -> None:
        remote = "https://images.unsplash.com/photo-pasta.jpg"
        with patch.object(fis, "validate_image_url", return_value=True):
            resolved = fis.resolve_food_image(
                "Kycklingpasta med tomat",
                "pasta",
                recipe_image_url=remote,
                api_key="",
            )
        self.assertEqual(resolved["source"], "ai")
        self.assertIn("food?url=", resolved["url"] or "")

    def test_enrich_decision_uses_recipe_display_url(self) -> None:
        decision = {
            "domain": "food",
            "suggestion": "Proteinomelett med frukt",
            "context": {
                "dish_category": "omelett",
                "recipe": {
                    "title": "Proteinomelett med frukt",
                    "image_url": "https://images.unsplash.com/photo-x.jpg",
                    "image_source": "ai",
                    "image_display_url": "/api/media/food?url=https%3A%2F%2Fimages.unsplash.com%2Fphoto-x.jpg",
                },
            },
        }
        enriched = enrich_decision(decision, language="sv") or {}
        pres = enriched.get("presentation") or {}
        self.assertTrue(pres.get("dish_image_url", "").startswith("/api/media/food"))
        self.assertEqual(pres.get("dish_image_source"), "ai")

    def test_dish_image_url_helper_prefers_context(self) -> None:
        url = dish_image_url(
            "Whatever",
            context={"dish_image_url": "/api/media/food?url=abc"},
        )
        self.assertEqual(url, "/api/media/food?url=abc")

    def test_resolve_never_raises_when_ai_explodes(self) -> None:
        def boom(_title: str) -> str | None:
            raise RuntimeError("image API exploded")

        fis.set_search_override(boom)
        resolved = fis.resolve_food_image(
            "Spaghetti carbonara",
            "pasta",
            api_key="xai-test",
            use_cache=False,
        )
        self.assertIn(resolved["source"], ("local", "placeholder"))
        self.assertIsInstance(resolved, dict)

    def test_unsupported_image_search_disables_without_retry_crash(self) -> None:
        calls = {"n": 0}

        class FakeResp:
            status_code = 400
            text = '{"error":"Unknown parameter enable_image_search"}'

            def json(self):
                return {"error": "Unknown parameter enable_image_search"}

        def fake_post(*_a, **_k):
            calls["n"] += 1
            return FakeResp()

        with (
            patch.object(fis, "_SEARCH_OVERRIDE", None),
            patch("food_image_search.requests.post", side_effect=fake_post),
            patch("llm_config.text_model", return_value="grok-4-fast"),
        ):
            fis.reset_ai_image_search_state()
            a = fis.search_dish_image_url(
                "omelett", api_key="xai-test-key", use_cache=False
            )
            self.assertIsNone(a)
            self.assertFalse(fis.ai_image_search_enabled())
            b = fis.search_dish_image_url(
                "pasta", api_key="xai-test-key", use_cache=False
            )
            self.assertIsNone(b)
            # Second call must not hit the network again
            self.assertEqual(calls["n"], 1)

        # Resolve still falls back to local
        fis.reset_ai_image_search_state()
        with (
            patch.object(fis, "_SEARCH_OVERRIDE", None),
            patch("food_image_search.requests.post", side_effect=fake_post),
            patch("llm_config.text_model", return_value="grok-4-fast"),
        ):
            fis._disable_ai_image_search("test")
            resolved = fis.resolve_food_image(
                "Spaghetti carbonara",
                "pasta",
                api_key="xai-test-key",
                use_cache=False,
                prefer_ai=True,
            )
        self.assertEqual(resolved["source"], "local")

    def test_enrich_survives_resolve_explosion(self) -> None:
        with patch.object(
            fis, "resolve_food_image", side_effect=RuntimeError("boom")
        ):
            enriched = enrich_decision(
                {
                    "domain": "food",
                    "suggestion": "Tacos",
                    "context": {"dish_category": "tacos"},
                },
                language="sv",
            )
        self.assertIsInstance(enriched, dict)
        pres = enriched.get("presentation") or {}
        self.assertIsNone(pres.get("dish_image_url"))


class FoodDecideImageNonBlockingTests(unittest.TestCase):
    def tearDown(self) -> None:
        fis.set_search_override(None)
        fis.reset_ai_image_search_state()

    def test_decide_does_not_call_ai_image_on_critical_path(self) -> None:
        """Grok image search must not run inside /api/decide (20s client abort)."""
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from api.main import app
        import api.services.decide_service as ds

        calls: list[dict] = []

        def track_search(*_a, **_k):
            calls.append({"fn": "search"})
            return "https://images.unsplash.com/photo-x.jpg"

        client = TestClient(app)
        client.post("/api/auth/guest")
        with (
            patch.object(ds, "grok_api_key", return_value="xai-test-key-long"),
            patch.object(fis, "search_dish_image_url", side_effect=track_search),
            patch.object(fis, "validate_image_url", return_value=True),
        ):
            t0 = __import__("time").time()
            r = client.post(
                "/api/decide",
                json={"domain_hint": "food", "context_extra": {"meal_type": "frukost"}},
            )
            elapsed = __import__("time").time() - t0
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("page"), "result")
        self.assertLess(elapsed, 5.0, msg="decide must stay fast without AI image")
        self.assertEqual(calls, [], msg="AI image search must be lazy, not in decide")
        pres = (r.json().get("decision") or {}).get("presentation") or {}
        self.assertTrue(pres.get("image_pending"))
        self.assertIn(pres.get("dish_image_source"), ("placeholder", None))

        # Lazy upgrade endpoint may call AI search
        with (
            patch.object(ds, "grok_api_key", return_value="xai-test-key-long"),
            patch.object(fis, "search_dish_image_url", side_effect=track_search),
            patch.object(fis, "validate_image_url", return_value=True),
        ):
            # Also patch secrets used by the route
            with patch("api.secrets.grok_api_key", return_value="xai-test-key-long"):
                up = client.post("/api/decision/dish-image")
        self.assertEqual(up.status_code, 200, up.text)
        body = up.json()
        self.assertEqual(body.get("source"), "ai")
        self.assertTrue((body.get("url") or "").startswith("/api/media/food"))
        self.assertTrue(calls)

    def test_slow_grok_falls_back_to_local_under_deadline(self) -> None:
        """Hung Grok must not block food decide past the hard candidate deadline."""
        import time
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from api.main import app
        import api.services.decide_service as ds
        import pipeline as pl

        def hang(*_a, **_k):
            time.sleep(30)
            return [{"suggestion": "LLM-rätt", "justification": "x", "meta": {}}]

        client = TestClient(app)
        client.post("/api/auth/guest")
        with (
            patch.object(ds, "grok_api_key", return_value="xai-test-key-long"),
            patch.object(pl, "_grok_candidates", side_effect=hang),
        ):
            t0 = time.time()
            r = client.post(
                "/api/decide",
                json={
                    "domain_hint": "food",
                    "context_extra": {"meal_type": "lunch"},
                },
            )
            elapsed = time.time() - t0
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json().get("page"), "result")
        self.assertTrue((r.json().get("decision") or {}).get("suggestion"))
        # Hard deadline ~10s + small overhead — never approach client 35s abort
        self.assertLess(elapsed, 14.0, msg=f"decide hung {elapsed:.1f}s on slow Grok")

class FoodCostUsedAmountTests(unittest.TestCase):
    def test_two_egg_omelette_single_or_low_double_digits(self) -> None:
        recipe = {
            "title": "Proteinomelett",
            "meal_type": "frukost",
            "portioner": 1,
            "ingredients": [
                {"name": "ägg", "amount": "2", "unit": "st"},
                {"name": "smör", "amount": "1", "unit": "msk"},
                {"name": "salt", "amount": "1", "unit": "krm"},
                {"name": "peppar", "amount": "1", "unit": "krm"},
                {"name": "olja", "amount": "1", "unit": "msk"},
            ],
        }
        out = fbud.ensure_recipe_cost(recipe, allow_estimate=True, meal_type="frukost")
        sek = out["cost_per_portion_sek"]
        self.assertLessEqual(sek, 25)
        self.assertGreaterEqual(sek, 5)
        self.assertNotEqual(sek, 85)

    def test_package_price_rejected_by_sanity_bound(self) -> None:
        recipe = {
            "title": "Äggomelett",
            "meal_type": "frukost",
            "portioner": 1,
            "cost_per_portion_sek": 85,  # whole-package LLM guess
            "ingredients": [
                {"name": "ägg", "amount": "2", "unit": "st"},
                {"name": "mjölk", "amount": "2", "unit": "msk"},
                {"name": "smör", "amount": "1", "unit": "tsk"},
            ],
        }
        out = fbud.ensure_recipe_cost(recipe, allow_estimate=True, meal_type="frukost")
        self.assertTrue(out.get("cost_regenerated"))
        self.assertLessEqual(out["cost_per_portion_sek"], 30)
        self.assertTrue(fbud.cost_exceeds_sanity(85, meal_type="frukost"))

    def test_used_amount_not_carton(self) -> None:
        # Name-only eggs must not price a whole carton into one portion
        per = fbud.estimate_cost_per_portion(
            ["ägg", "smör", "salt"],
            servings=1,
            meal_type="frukost",
        )
        self.assertLessEqual(per, 25)

    def test_prompt_mentions_used_amounts(self) -> None:
        import pipeline

        rules = pipeline._domain_prompt_rules(
            "food", {"food": {"meal_budget": "any"}}
        )
        self.assertIn("ONLY the amount", rules)
        self.assertIn("Pantry staples", rules)


if __name__ == "__main__":
    unittest.main()
