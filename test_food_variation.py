# -*- coding: utf-8 -*-
"""Food variation engine — hard exclusion, pref clamp, expanded packs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import food_local_packs as flp
import pipeline


class FoodVariationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "var.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)
        self.uid = self.user["id"]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fake_grok(self, *_a, **_k):  # noqa: ANN001
        # Return full dinner pack so ranking can hard-exclude recent
        return [dict(c) for c in flp.dinner_pack("sv")]

    def test_dinner_pack_size(self) -> None:
        pack = flp.dinner_pack("sv")
        self.assertGreaterEqual(len(pack), 15)
        self.assertGreaterEqual(sum(1 for c in pack if c.get("wildcard")), 3)
        cats = {
            (c.get("meta") or {}).get("dish_category")
            for c in pack
            if (c.get("meta") or {}).get("dish_category")
        }
        self.assertGreaterEqual(len(cats), 5)

    def test_lunch_pack_size(self) -> None:
        pack = flp.lunch_pack("sv")
        self.assertGreaterEqual(len(pack), 10)
        self.assertGreaterEqual(sum(1 for c in pack if c.get("wildcard")), 3)

    def test_seven_middag_accepts_are_distinct(self) -> None:
        seen: list[str] = []
        with mock.patch.object(pipeline, "_grok_candidates", side_effect=self._fake_grok):
            with mock.patch.object(pipeline.random, "random", return_value=0.5):
                # force safe (non-explore) path — random > SAFE_RATIO would explore
                for _ in range(7):
                    r = pipeline.decide(
                        self.uid,
                        "Vad ska jag äta?",
                        domain_hint="food",
                        language="sv",
                        db_path=self.db_path,
                        grok_api_key="xai-fake-key-for-test-12345",
                        context_extra={"meal_type": "middag"},
                    )
                    self.assertTrue(r.ok, r)
                    title = str(r.suggestion or "").strip()
                    self.assertTrue(title)
                    self.assertNotIn(title.lower(), {s.lower() for s in seen})
                    seen.append(title)
                    pipeline.accept_decision(r.decision_id, db_path=self.db_path)
        self.assertEqual(len(seen), 7)

    def test_dish_returns_after_repeat_window(self) -> None:
        """After window expires (mock recent empty), a prior dish may return."""
        with mock.patch.object(pipeline, "_grok_candidates", side_effect=self._fake_grok):
            with mock.patch.object(pipeline.random, "random", return_value=0.5):
                r1 = pipeline.decide(
                    self.uid,
                    "Vad ska jag äta?",
                    domain_hint="food",
                    language="sv",
                    db_path=self.db_path,
                    grok_api_key="xai-fake-key-for-test-12345",
                    context_extra={"meal_type": "middag"},
                )
                pipeline.accept_decision(r1.decision_id, db_path=self.db_path)
                first = str(r1.suggestion)
                # Pretend the repeat window is empty
                with mock.patch.object(db, "recent_suggestions", return_value=[]):
                    r2 = pipeline.decide(
                        self.uid,
                        "Vad ska jag äta?",
                        domain_hint="food",
                        language="sv",
                        db_path=self.db_path,
                        grok_api_key="xai-fake-key-for-test-12345",
                        context_extra={"meal_type": "middag"},
                    )
        # With empty recent + high pref for first, it should be eligible again
        titles = {c["suggestion"] for c in self._fake_grok()}
        self.assertIn(first, titles)
        self.assertTrue(r2.ok)

    def test_pref_clamp_after_many_accepts(self) -> None:
        dish = "krämig tomatsås-pasta"
        for _ in range(10):
            db.upsert_preference(
                self.uid, "food", "suggestion", dish, 1.0, path=self.db_path
            )
        prefs = db.get_preferences(self.uid, "food", path=self.db_path)
        hit = next(p for p in prefs if p["value"] == dish)
        self.assertLessEqual(float(hit["score"]), pipeline.PREF_SCORE_MAX)
        self.assertGreaterEqual(float(hit["score"]), pipeline.PREF_SCORE_MIN)
        self.assertEqual(float(hit["score"]), 3.0)

    def test_hard_exclusion_in_rank(self) -> None:
        cands = flp.dinner_pack("sv")
        recent = [cands[0]["suggestion"], cands[1]["suggestion"]]
        ranked = pipeline._rank_candidates(
            cands,
            preferences=[],
            recent=recent,
            explore=False,
        )
        top_titles = {str(c["suggestion"]).lower() for c in ranked}
        self.assertNotIn(recent[0].lower(), top_titles)
        self.assertNotIn(recent[1].lower(), top_titles)

    def test_favorite_bonus_still_excluded_when_recent(self) -> None:
        cands = flp.dinner_pack("sv")
        fav = cands[0]["suggestion"]
        ranked = pipeline._rank_candidates(
            cands,
            preferences=[],
            recent=[fav],
            explore=False,
            favorite_suggestions=[fav],
        )
        self.assertTrue(ranked)
        self.assertNotEqual(str(ranked[0]["suggestion"]).lower(), fav.lower())


class FoodLocalFirstScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "fast.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_frukost_skips_grok(self) -> None:
        with mock.patch.object(pipeline, "_grok_candidates") as grok:
            grok.side_effect = AssertionError("Grok must not run on frukost")
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag äta?",
                domain_hint="food",
                language="sv",
                db_path=self.db_path,
                grok_api_key="xai-fake-key-for-test-12345",
                context_extra={"meal_type": "frukost"},
            )
        self.assertTrue(r.ok)
        grok.assert_not_called()

    def test_middag_calls_grok(self) -> None:
        called = {"n": 0}

        def fake(*_a, **_k):  # noqa: ANN001
            called["n"] += 1
            return [dict(c) for c in flp.dinner_pack("sv")]

        with mock.patch.object(pipeline, "_grok_candidates", side_effect=fake):
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag äta?",
                domain_hint="food",
                language="sv",
                db_path=self.db_path,
                grok_api_key="xai-fake-key-for-test-12345",
                context_extra={"meal_type": "middag"},
            )
        self.assertTrue(r.ok)
        self.assertEqual(called["n"], 1)


if __name__ == "__main__":
    unittest.main()
