# -*- coding: utf-8 -*-
"""Movie TMDB metadata integration + card rendering behavior."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import feasibility


class MovieTmdbValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_tmdb_match_attaches_poster_rating_year(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"streaming_services": ["netflix"], "available_minutes": 45},
        )
        candidate = {
            "suggestion": "Seinfeld",
            "justification": "Enkelt ikväll.",
            "meta": {"title": "seinfeld", "kind": "series"},
        }
        with mock.patch("tmdb.lookup_title") as lookup:
            lookup.return_value = {
                "tmdb_id": 123,
                "title": "Seinfeld",
                "year": 1989,
                "poster_url": "https://example.com/poster.jpg",
                "vote_average": 7.8,
            }
            r = feasibility.feasibility_check(
                candidate,
                domain="movie",
                profile=profile,
                context={"format": "avsnitt", "mood": "avkopplat", "available_minutes": 50},
            )

        self.assertTrue(r.ok)
        meta = ((r.enriched or {}).get("meta") or {})
        self.assertEqual(meta.get("poster_url"), "https://example.com/poster.jpg")
        self.assertEqual(meta.get("vote_average"), 7.8)
        self.assertEqual(meta.get("year"), 1989)

    def test_tmdb_unmatched_rejects(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"streaming_services": ["netflix"], "available_minutes": 45},
        )
        candidate = {
            "suggestion": "Some Unknown Title",
            "justification": "En slump.",
            "meta": {"title": "some unknown title", "kind": "series"},
        }
        with mock.patch("tmdb.lookup_title", return_value=None):
            r = feasibility.feasibility_check(
                candidate,
                domain="movie",
                profile=profile,
                context={"format": "avsnitt", "mood": "avkopplat", "available_minutes": 50},
            )
        self.assertFalse(r.ok)
        self.assertIn("tmdb_no_match", r.reasons or [])

    def test_low_rating_rejects_llm_candidate(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"streaming_services": ["netflix"], "available_minutes": 45},
        )
        candidate = {
            "suggestion": "Seinfeld",
            "justification": "En slump.",
            # Simulate an LLM candidate (not local pack)
            "meta": {"title": "seinfeld", "kind": "series", "local_pack": False},
        }
        with mock.patch("tmdb.lookup_title") as lookup:
            lookup.return_value = {
                "tmdb_id": 123,
                "title": "Seinfeld",
                "year": 1989,
                "poster_url": "https://example.com/poster.jpg",
                "vote_average": 6.0,
            }
            r = feasibility.feasibility_check(
                candidate,
                domain="movie",
                profile=profile,
                context={"format": "avsnitt", "mood": "avkopplat", "available_minutes": 50},
            )
        self.assertFalse(r.ok)
        self.assertIn("low_rating", r.reasons or [])

    def test_low_rating_allows_local_pack(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"streaming_services": ["netflix"], "available_minutes": 45},
        )
        candidate = {
            "suggestion": "Seinfeld",
            "justification": "En slump.",
            "meta": {"title": "seinfeld", "kind": "series", "local_pack": True},
        }
        with mock.patch("tmdb.lookup_title") as lookup:
            lookup.return_value = {
                "tmdb_id": 123,
                "title": "Seinfeld",
                "year": 1989,
                "poster_url": "https://example.com/poster.jpg",
                "vote_average": 6.0,
            }
            r = feasibility.feasibility_check(
                candidate,
                domain="movie",
                profile=profile,
                context={"format": "avsnitt", "mood": "avkopplat", "available_minutes": 50},
            )
        self.assertTrue(r.ok)


class MovieTmdbUiTests(unittest.TestCase):
    def test_poster_missing_renders_text_only(self) -> None:
        from streamlit.testing.v1 import AppTest

        # Force TMDB to return match but no poster_url.
        with mock.patch("tmdb.lookup_title") as lookup:
            lookup.return_value = {
                "tmdb_id": 123,
                "title": "Seinfeld",
                "year": 1989,
                "poster_url": None,
                "vote_average": 7.8,
            }

            at = AppTest.from_file("app.py", default_timeout=90)
            at.run()
            at.session_state["movie_format"] = "avsnitt"
            at.session_state["movie_mood"] = "avkopplat"
            at.query_params["domain"] = "movie"
            at.run()

            cur = at.session_state["current"] or {}
            ctx = cur.get("context") if isinstance(cur, dict) else {}
            ctx = ctx or {}
            import app as app_mod

            card = app_mod._render_movie_card_html(
                language="sv",
                suggestion=str(cur.get("suggestion") or ""),
                justification=str(cur.get("justification") or ""),
                ctx=ctx,
            )
            self.assertNotIn('<img class="oc-movie-poster"', card)
            self.assertIn("★", card)


if __name__ == "__main__":
    unittest.main()

