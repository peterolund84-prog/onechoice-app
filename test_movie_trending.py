# -*- coding: utf-8 -*-
"""Trendar nu — grounded web-search movie mode."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import db
import movie_trending as mt
import pipeline


def _fresh_date(days_ago: int = 3) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def _hit(
    title: str,
    *,
    kind: str = "series",
    why: str = "Snackas överallt just nu — nya säsongen släpptes i veckan.",
    dated: bool = True,
    days_ago: int = 3,
) -> dict:
    sources = []
    if dated:
        sources.append(
            {
                "name": "SVT Nyheter",
                "url": f"https://www.svt.se/kultur/{title.lower().replace(' ', '-')}",
                "date": _fresh_date(days_ago),
            }
        )
    else:
        sources.append(
            {
                "name": "Random blog",
                "url": "https://example.com/undated",
                # no date → not grounded
            }
        )
    return {"title": title, "kind": kind, "why": why, "sources": sources}


class GroundingFilterTests(unittest.TestCase):
    def test_source_less_candidate_rejected(self) -> None:
        hits = [_hit("Wednesday", dated=False), _hit("Andor", dated=True)]
        grounded = mt.filter_grounded_hits(hits, now=date.today())
        titles = {g["title"] for g in grounded}
        self.assertNotIn("Wednesday", titles)
        self.assertIn("Andor", titles)

    def test_stale_source_rejected(self) -> None:
        hits = [_hit("Seinfeld", days_ago=60)]
        grounded = mt.filter_grounded_hits(hits, now=date.today())
        self.assertEqual(grounded, [])


class TrendingPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)
        mt.set_search_override(None)

    def tearDown(self) -> None:
        mt.set_search_override(None)
        self.tmp.cleanup()

    def test_mocked_search_grounded_pick_with_tmdb(self) -> None:
        hits = [
            _hit(
                "Wednesday",
                why="Snackas överallt just nu — nya säsongen släpptes i veckan.",
            ),
            _hit("Andor", why="Het i feeden efter senaste avsnittet."),
        ]
        mt.set_search_override(lambda _q: hits)
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={
                "mode": "trendar",
                "format": "avsnitt",
                "mood": "avkopplat",
                "streaming_services": ["netflix"],
            },
        )
        self.assertTrue(r.ok, msg=r.refusal_message)
        self.assertFalse(r.refused)
        self.assertEqual((r.context or {}).get("mode"), "trendar")
        # Netflix-available trending title should win (Wednesday is on Netflix)
        self.assertEqual(str(r.suggestion).strip().lower(), "wednesday")
        self.assertIn("Snackas", r.justification or "")
        self.assertTrue((r.context or {}).get("movie_tmdb_vote_average") or (r.context or {}).get("movie_tmdb_year"))

    def test_paywalled_title_deprioritised(self) -> None:
        # Andor = Disney+ only in mocks; Wednesday = Netflix
        hits = [
            _hit("Andor", why="Trendig men bakom annan paywall."),
            _hit("Wednesday", why="Snackas på Netflix just nu."),
        ]
        mt.set_search_override(lambda _q: hits)
        cands = mt.build_trending_candidates(
            language="sv",
            fmt="avsnitt",
            user_services=["netflix"],
            search_hits=hits,
            use_cache=False,
        )
        pick = mt.pick_trending_candidate(cands)
        self.assertIsNotNone(pick)
        self.assertEqual(str(pick["suggestion"]).lower(), "wednesday")
        # Andor present but marked paywalled / after available
        andor = next(
            (c for c in cands if "andor" in str(c.get("suggestion") or "").lower()),
            None,
        )
        self.assertIsNotNone(andor)
        self.assertTrue((andor.get("meta") or {}).get("paywalled"))

        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={
                "mode": "trendar",
                "format": "avsnitt",
                "streaming_services": ["netflix"],
            },
        )
        self.assertTrue(r.ok)
        self.assertNotEqual(str(r.suggestion).strip().lower(), "andor")

    def test_empty_search_uses_tmdb_chart_fallback(self) -> None:
        """No web hits → still pick from TMDB week chart (button must work)."""
        mt.set_search_override(lambda _q: [])
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={"mode": "trendar", "format": "avsnitt"},
        )
        self.assertTrue(r.ok, msg=r.refusal_message)
        self.assertFalse(r.refused)
        self.assertEqual((r.context or {}).get("mode"), "trendar")
        self.assertTrue(str(r.suggestion or "").strip())

    def test_empty_search_and_empty_chart_honest_state(self) -> None:
        mt.set_search_override(lambda _q: [])
        with patch("tmdb.trending_titles", return_value=[]):
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag titta på?",
                domain_hint="movie",
                language="sv",
                db_path=self.path,
                context_extra={"mode": "trendar", "format": "avsnitt"},
            )
        self.assertFalse(r.ok)
        self.assertTrue(r.refused)
        self.assertIn("trender", (r.refusal_message or "").lower())
        self.assertIn("humör", (r.refusal_message or "").lower())
        self.assertTrue((r.context or {}).get("trending_empty"))

    def test_source_less_falls_back_to_chart(self) -> None:
        mt.set_search_override(lambda _q: [_hit("Wednesday", dated=False)])
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={"mode": "trendar", "format": "avsnitt"},
        )
        self.assertTrue(r.ok, msg=r.refusal_message)
        self.assertFalse(r.refused)

    def test_tmdb_miss_dropped(self) -> None:
        hits = [_hit("Totally Fake Show XYZ123", why="Fake buzz.")]
        mt.set_search_override(lambda _q: hits)
        with patch("movie_trending.verify_tmdb", return_value=None):
            with patch("tmdb.trending_titles", return_value=[]):
                cands = mt.build_trending_candidates(
                    language="sv",
                    search_hits=hits,
                    user_services=["netflix"],
                    use_cache=False,
                )
        self.assertEqual(cands, [])


class ModeHelpersTests(unittest.TestCase):
    def test_normalize_and_labels(self) -> None:
        import movie_domain as md

        self.assertEqual(md.normalize_mode("Trending"), "trendar")
        self.assertEqual(md.normalize_mode("mood"), "mood")
        self.assertEqual(md.mode_label("trendar", "sv"), "Trendar nu")
        self.assertEqual(md.mode_label("trendar", "en"), "Trending")
        self.assertIn("trendar", md.MODE_ORDER)


if __name__ == "__main__":
    unittest.main()
