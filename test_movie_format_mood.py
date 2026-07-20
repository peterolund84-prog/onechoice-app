# -*- coding: utf-8 -*-
"""Movie format + mood chips — inferred, confirmable, logged (LLM required)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import feasibility
import movie_domain as md
import pipeline


class MovieFormatMoodInferTests(unittest.TestCase):
    def test_format_time_windows(self) -> None:
        self.assertEqual(md.default_format(21, weekday=True), "avsnitt")
        self.assertEqual(md.default_format(20, weekday=False), "film")
        self.assertEqual(md.default_format(14, weekday=False), "ny_serie")

    def test_mood_weekday_vs_weekend(self) -> None:
        self.assertEqual(md.default_mood(20, weekday=True), "avkopplat")
        self.assertEqual(md.default_mood(20, weekday=False), "spanning")

    def test_mood_from_history_slot(self) -> None:
        history = [
            {
                "status": "accepted",
                "suggestion": "Seinfeld",
                "context": {"mood": "skratta", "hour": 20, "weekday": True},
            },
            {
                "status": "accepted",
                "suggestion": "Vänner",
                "context": {"mood": "skratta", "hour": 21, "weekday": True},
            },
            {
                "status": "accepted",
                "suggestion": "Andor",
                "context": {"mood": "spanning", "hour": 20, "weekday": True},
            },
        ]
        self.assertEqual(
            md.default_mood(20, weekday=True, history=history),
            "skratta",
        )

    def test_in_progress_series_label(self) -> None:
        history = [
            {
                "status": "accepted",
                "suggestion": "Wednesday",
                "context": {
                    "format": "ny_serie",
                    "kind": "series",
                    "meta": {"title": "wednesday", "kind": "series"},
                },
            }
        ]
        name = md.find_in_progress_series(history)
        self.assertTrue(name)
        self.assertIn("Wednesday", name)
        label = md.format_label("avsnitt", "sv", in_progress_series=name)
        self.assertEqual(label, f"Nästa avsnitt av {name}")
        history[0]["context"]["series_completed"] = True
        self.assertIsNone(md.find_in_progress_series(history))

    def test_two_chip_rows_only(self) -> None:
        self.assertEqual(len(md.FORMAT_ORDER), 3)
        self.assertEqual(len(md.MOOD_ORDER), 5)
        self.assertNotIn("thriller", md.MOODS)
        self.assertNotIn("comedy", md.MOODS)

    def test_mood_guidance_not_for_ui(self) -> None:
        g = md.mood_guidance("avkopplat", "sv")
        self.assertIn("cognitive", g.lower())
        # Must never be used as justification
        self.assertFalse(md.is_named_title("En film under två timmar", {}))


class MovieDecideLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "m.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _mock_pack(self) -> list[dict]:
        return [
            {
                "suggestion": "Seinfeld",
                "justification": "Lugn bekant sitcom — perfekt måndagssoffa.",
                "meta": {"title": "seinfeld", "kind": "series"},
                "wildcard": False,
            }
        ] * 5

    def test_decide_logs_format_and_mood(self) -> None:
        with mock.patch.object(pipeline, "_generate_candidates", return_value=self._mock_pack()):
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag titta på?",
                domain_hint="movie",
                language="sv",
                db_path=self.path,
                grok_api_key="xai-test-key-long",
                context_extra={"format": "avsnitt", "mood": "avkopplat"},
            )
        self.assertTrue(r.ok, r.refusal_message)
        ctx = r.context or {}
        self.assertEqual(ctx.get("format"), "avsnitt")
        self.assertEqual(ctx.get("mood"), "avkopplat")
        self.assertEqual(ctx.get("kind"), "series")
        row = next(
            x
            for x in db.list_decisions(self.user["id"], path=self.path)
            if x["id"] == r.decision_id
        )
        stored = row.get("context") or {}
        self.assertEqual(stored.get("format"), "avsnitt")
        self.assertEqual(stored.get("mood"), "avkopplat")

    def test_no_llm_does_not_fake_title(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "film",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            grok_api_key="",
            context_extra={"format": "film", "mood": "spanning"},
        )
        self.assertFalse(r.ok)
        self.assertTrue((r.context or {}).get("llm_offline"))
        self.assertNotIn("två timmar", (r.suggestion or "").lower())

    def test_med_barnen_rejects_adult_titles(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {
                "streaming_services": ["netflix"],
                "kids_ages": [6],
                "mood": "med_barnen",
                "format": "film",
                "available_minutes": 140,
            },
        )
        bad = {
            "suggestion": "The Night Agent",
            "justification": "Spänning.",
            "meta": {"title": "the night agent", "kind": "series"},
        }
        r = feasibility.feasibility_check(
            bad,
            domain="movie",
            profile=profile,
            context={"mood": "med_barnen", "format": "avsnitt", "available_minutes": 50},
        )
        self.assertFalse(r.ok)

    def test_ui_has_format_mood_chip_renderer(self) -> None:
        import inspect

        import app as app_mod

        self.assertTrue(hasattr(app_mod, "render_movie_format_mood_chips"))
        src = inspect.getsource(app_mod.page_result)
        self.assertIn("render_movie_format_mood_chips", src)
        self.assertIn("movie_offline", src)
        chip_src = inspect.getsource(app_mod.render_movie_format_mood_chips)
        self.assertIn("movie_format_pills", chip_src)
        self.assertIn("movie_mood_pills", chip_src)
        self.assertNotIn("genre", chip_src.lower())


class MovieUiChipTests(unittest.TestCase):
    def test_movie_offline_shows_format_mood_and_retry(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["movie_format"] = "avsnitt"
        at.session_state["movie_mood"] = "avkopplat"
        at.query_params["domain"] = "movie"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        cur = at.session_state["current"] or {}
        # Without LLM → honest offline
        self.assertTrue(cur.get("refused") or cur.get("llm_offline") or (cur.get("context") or {}).get("llm_offline"))
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Format", body)
        self.assertIn("Läge", body)
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("Försök igen" in lab for lab in labels), labels)
        self.assertNotIn("En film under två timmar", body)


if __name__ == "__main__":
    unittest.main()
