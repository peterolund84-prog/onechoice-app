# -*- coding: utf-8 -*-
"""Decision engine architecture: AI generates, real data verifies, pack is fallback."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db
import feasibility
import movie_trending as mt
import pipeline
import tmdb


class TmdbSeProvidersTests(unittest.TestCase):
    def tearDown(self) -> None:
        tmdb.set_providers_override(None)
        tmdb.watch_providers.cache_clear()

    def test_offline_wednesday_on_netflix_se(self) -> None:
        row = tmdb.lookup_title("Wednesday", kind="series")
        self.assertIsNotNone(row)
        assert row is not None
        prov = tmdb.watch_providers(int(row["tmdb_id"]), kind="series", region="SE")
        self.assertIsNotNone(prov)
        assert prov is not None
        self.assertIn("netflix", prov.get("services") or [])
        self.assertEqual(prov.get("source"), "offline")

    def test_grok_title_verified_via_tmdb_se_providers(self) -> None:
        """LLM-shaped candidate: service + deep link come from TMDB SE, not the model."""
        tmdb.set_providers_override(
            lambda _id, _kind, _region: {
                "services": ["netflix"],
                "flatrate": [{"provider_id": 8, "provider_name": "Netflix"}],
                "link": "https://www.themoviedb.org/tv/1/watch?locale=SE",
                "source": "override",
            }
        )
        profile = feasibility.parse_profile(
            {"profile_json": "{}"},
            {"streaming_services": ["netflix"], "available_minutes": 60},
        )
        cand = {
            "suggestion": "Wednesday",
            "justification": "Grok free invent — spooky and funny.",
            "meta": {"title": "wednesday", "kind": "series", "local_pack": False},
        }
        r = feasibility.feasibility_check(cand, domain="movie", profile=profile)
        self.assertTrue(r.ok, msg=r.reasons)
        self.assertEqual((r.enriched or {}).get("meta", {}).get("service"), "netflix")
        self.assertEqual(
            (r.enriched or {}).get("meta", {}).get("availability_source"),
            "tmdb_watch_providers",
        )
        self.assertIn("netflix", (r.execution or {}).get("url") or "")

    def test_no_se_provider_rejects_llm_title(self) -> None:
        tmdb.set_providers_override(
            lambda _id, _kind, _region: {
                "services": [],
                "flatrate": [],
                "link": None,
                "source": "override",
            }
        )
        profile = feasibility.parse_profile(
            {"profile_json": "{}"},
            {"streaming_services": ["netflix"], "available_minutes": 60},
        )
        cand = {
            "suggestion": "Wednesday",
            "justification": "Hallucinated availability.",
            "meta": {"title": "wednesday", "kind": "series"},
        }
        r = feasibility.feasibility_check(cand, domain="movie", profile=profile)
        self.assertFalse(r.ok)
        self.assertIn("unavailable_se", r.reasons)


class TrendingFunnelTests(unittest.TestCase):
    def setUp(self) -> None:
        mt.set_search_override(None)
        tmdb.set_providers_override(None)
        tmdb.watch_providers.cache_clear()

    def tearDown(self) -> None:
        mt.set_search_override(None)
        tmdb.set_providers_override(None)

    def test_funnel_counts_grounded_tmdb_se_and_paywalled(self) -> None:
        def _hit(title: str, *, days_ago: int = 3) -> dict:
            from datetime import date, timedelta

            return {
                "title": title,
                "kind": "series",
                "why": "Snackas just nu.",
                "sources": [
                    {
                        "name": "SVT",
                        "url": "https://www.svt.se/x",
                        "date": (date.today() - timedelta(days=days_ago)).isoformat(),
                    }
                ],
            }

        hits = [_hit("Andor"), _hit("Wednesday"), _hit("NotARealShow999")]
        cands = mt.build_trending_candidates(
            language="sv",
            fmt="avsnitt",
            user_services=["netflix"],
            search_hits=hits,
            use_cache=False,
        )
        funnel = mt.last_trending_funnel()
        self.assertEqual(funnel.get("raw_n"), 3)
        self.assertEqual(funnel.get("grounded_n"), 3)
        self.assertGreaterEqual(int(funnel.get("tmdb_ok_n") or 0), 2)
        self.assertGreaterEqual(int(funnel.get("se_available_n") or 0), 2)
        self.assertGreaterEqual(int(funnel.get("dropped_no_tmdb") or 0), 1)
        # Andor (Disney+) paywalled for Netflix-only user; Wednesday available
        titles = [str(c.get("suggestion") or "").lower() for c in cands]
        self.assertTrue(any("wednesday" in t for t in titles))
        pick = mt.pick_trending_candidate(cands)
        self.assertIsNotNone(pick)
        assert pick is not None
        self.assertIn("wednesday", str(pick.get("suggestion") or "").lower())


class MovieAntiRepetitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_movie_decisions_feed_recent_suggestions_log(self) -> None:
        """HTML/FastAPI path uses pipeline.decide → same decisions log as food."""
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={
                "mode": "mood",
                "format": "avsnitt",
                "mood": "avkopplat",
                "streaming_services": ["netflix"],
            },
            grok_api_key="",  # local pack path — still must log
        )
        self.assertTrue(r.ok, msg=r.refusal_message)
        recent = db.recent_suggestions(
            self.user["id"], "movie", days=pipeline.MOVIE_REPEAT_DAYS, path=self.path
        )
        self.assertTrue(recent)
        self.assertTrue(
            any(
                str(r.suggestion).strip().lower() == str(x).strip().lower()
                for x in recent
            )
        )

    def test_repeated_movie_title_excluded_across_sessions(self) -> None:
        first = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={
                "mode": "mood",
                "format": "avsnitt",
                "mood": "avkopplat",
                "streaming_services": ["netflix"],
            },
            grok_api_key="",
        )
        self.assertTrue(first.ok)
        title = str(first.suggestion).strip().lower()
        # Force ranking to see only the previous title as recent — second decide
        # must not surface the same suggestion when alternatives exist.
        with patch.object(db, "recent_suggestions", return_value=[first.suggestion]):
            second = pipeline.decide(
                self.user["id"],
                "Vad ska jag titta på?",
                domain_hint="movie",
                language="sv",
                db_path=self.path,
                context_extra={
                    "mode": "mood",
                    "format": "avsnitt",
                    "mood": "avkopplat",
                    "streaming_services": ["netflix"],
                },
                grok_api_key="",
            )
        if second.ok:
            self.assertNotEqual(str(second.suggestion).strip().lower(), title)
        else:
            # Honest refuse is acceptable when every survivor was recent.
            self.assertTrue(second.refused)

    def test_movie_repeat_window_is_fourteen_days(self) -> None:
        self.assertEqual(pipeline.MOVIE_REPEAT_DAYS, 14)


class MovieHonestFallbackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()
        tmdb.set_providers_override(None)

    def test_no_verified_movie_refuses_instead_of_seinfeld(self) -> None:
        tmdb.set_providers_override(
            lambda *_a, **_k: {
                "services": [],
                "flatrate": [],
                "link": None,
                "source": "override",
            }
        )
        with patch.object(pipeline, "_generate_candidates", return_value=[]):
            with patch.object(pipeline, "_local_candidates", return_value=[]):
                r = pipeline.decide(
                    self.user["id"],
                    "Vad ska jag titta på?",
                    domain_hint="movie",
                    language="sv",
                    db_path=self.path,
                    context_extra={
                        "mode": "mood",
                        "format": "avsnitt",
                        "mood": "avkopplat",
                        "streaming_services": ["netflix"],
                    },
                    grok_api_key="test-key-long-enough",
                )
        self.assertFalse(r.ok)
        self.assertTrue(r.refused)
        self.assertNotIn("seinfeld", (r.suggestion or "").lower())
        self.assertIn("försök igen", (r.refusal_message or "").lower())


if __name__ == "__main__":
    unittest.main()
