# -*- coding: utf-8 -*-
"""Movie format + mood chips — inferred, confirmable, logged."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import db
import feasibility
import movie_domain as md
import pipeline


class MovieFormatMoodInferTests(unittest.TestCase):
    def test_format_time_windows(self) -> None:
        # Weekday late → Avsnitt
        self.assertEqual(
            md.default_format(21, weekday=True),
            "avsnitt",
        )
        # Fri/Sat evening → Film
        self.assertEqual(
            md.default_format(20, weekday=False),
            "film",
        )
        # Weekend afternoon → Ny serie
        self.assertEqual(
            md.default_format(14, weekday=False),
            "ny_serie",
        )

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
        # Completed flag clears it
        history[0]["context"]["series_completed"] = True
        self.assertIsNone(md.find_in_progress_series(history))

    def test_two_chip_rows_only(self) -> None:
        self.assertEqual(len(md.FORMAT_ORDER), 3)
        self.assertEqual(len(md.MOOD_ORDER), 5)
        # No genre row — moods are not genres
        self.assertNotIn("thriller", md.MOODS)
        self.assertNotIn("comedy", md.MOODS)


class MovieDecideLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "m.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_decide_logs_format_and_mood(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={"format": "avsnitt", "mood": "avkopplat"},
        )
        self.assertTrue(r.ok)
        ctx = r.context or {}
        self.assertEqual(ctx.get("format"), "avsnitt")
        self.assertEqual(ctx.get("mood"), "avkopplat")
        self.assertEqual(ctx.get("kind"), "series")
        self.assertLessEqual(int(ctx.get("available_minutes") or 99), 50)
        row = next(
            x
            for x in db.list_decisions(self.user["id"], path=self.path)
            if x["id"] == r.decision_id
        )
        stored = row.get("context") or {}
        self.assertEqual(stored.get("format"), "avsnitt")
        self.assertEqual(stored.get("mood"), "avkopplat")

    def test_film_format_prefers_film_kind(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "film ikväll",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={"format": "film", "mood": "spanning"},
        )
        self.assertTrue(r.ok)
        self.assertEqual((r.context or {}).get("format"), "film")
        # Local pack for spanning+film includes Dune when services allow
        # (default profile includes hbo/prime — Dune should be feasible).
        self.assertTrue(r.suggestion)

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
        good = {
            "suggestion": "Hilda",
            "justification": "Med barnen — äventyr i lagom dos.",
            "meta": {"title": "hilda", "kind": "series", "kids_ok": True, "max_age_rating": 7},
        }
        r2 = feasibility.feasibility_check(
            good,
            domain="movie",
            profile=profile,
            context={"mood": "med_barnen", "format": "avsnitt", "available_minutes": 50},
        )
        self.assertTrue(r2.ok)

    def test_lar_mig_rejects_vague_placeholder(self) -> None:
        profile = feasibility.parse_profile(
            self.user,
            {"streaming_services": ["netflix"], "available_minutes": 50},
        )
        vague = {
            "suggestion": "Ett kort dokumentäravsnitt",
            "justification": "Lär mig något.",
            "meta": {"kind": "series", "genres": ["documentary"]},
        }
        r = feasibility.feasibility_check(
            vague,
            domain="movie",
            profile=profile,
            context={"mood": "lar_mig", "format": "avsnitt", "available_minutes": 50},
        )
        self.assertFalse(r.ok)
        self.assertIn("no_catalog_title", r.reasons or [])

    def test_lar_mig_decide_returns_named_title(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={"format": "avsnitt", "mood": "lar_mig"},
        )
        self.assertTrue(r.ok)
        self.assertNotIn("dokumentäravsnitt", (r.suggestion or "").lower())
        ctx = r.context or {}
        self.assertTrue(ctx.get("movie_poster_url") or ctx.get("movie_tmdb_vote_average"))

    def test_lar_mig_reroll_changes_suggestion(self) -> None:
        first = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            context_extra={"format": "avsnitt", "mood": "lar_mig"},
        )
        self.assertTrue(first.ok)
        second = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            reroll=True,
            reroll_index=1,
            previous_decision_id=first.decision_id,
            context_extra={
                "format": "avsnitt",
                "mood": "lar_mig",
                "previous_suggestion": first.suggestion,
            },
        )
        self.assertTrue(second.ok)
        self.assertNotEqual(
            str(second.suggestion or "").strip().lower(),
            str(first.suggestion or "").strip().lower(),
        )

    def test_ui_has_format_mood_chip_renderer(self) -> None:
        import inspect

        import app as app_mod

        self.assertTrue(hasattr(app_mod, "render_movie_format_mood_chips"))
        src = inspect.getsource(app_mod.page_result)
        self.assertIn("render_movie_format_mood_chips", src)
        chip_src = inspect.getsource(app_mod.render_movie_format_mood_chips)
        self.assertIn("movie_format_pills", chip_src)
        self.assertIn("movie_mood_pills", chip_src)
        # Two rows only — no genre pills
        self.assertNotIn("genre", chip_src.lower())


class MovieUiChipTests(unittest.TestCase):
    def test_movie_result_shows_format_and_mood_labels(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["movie_format"] = "avsnitt"
        at.session_state["movie_mood"] = "avkopplat"
        at.query_params["domain"] = "movie"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("Format", body)
        self.assertIn("Läge", body)
        # Never paint "Sök Title · Netflix" under the card — CTA is enough
        self.assertNotRegex(body, r"Sök\s+.+\s*[·•-]\s*Netflix")
        self.assertNotIn("Sök ", body)
        # Card is painted via st.html (not markdown) — assert the renderer + session ctx.
        cur = at.session_state["current"] or {}
        ctx = cur.get("context") if isinstance(cur, dict) else {}
        ctx = ctx or {}
        self.assertEqual(ctx.get("format"), "avsnitt")
        self.assertEqual(ctx.get("mood"), "avkopplat")
        import app as app_mod

        card = app_mod._render_movie_card_html(
            language="sv",
            suggestion=str(cur.get("suggestion") or ""),
            justification=str(cur.get("justification") or ""),
            ctx=ctx,
        )
        self.assertIn("AVSNITT", card)
        self.assertNotIn(">FILM<", card)
        self.assertNotIn('class="label oc-movie-kind">FILM', card)

    def test_movie_result_skips_execution_detail_meta(self) -> None:
        """page_result must not render movie execution_detail (Sök …)."""
        import inspect

        import app as app_mod

        src = inspect.getsource(app_mod.page_result)
        self.assertIn('domain not in ("food", "movie")', src)
        chip_src = inspect.getsource(app_mod.render_movie_format_mood_chips)
        self.assertIn('key="movie_chips"', chip_src)

    def test_movie_chips_css_prevents_label_overlap(self) -> None:
        from pathlib import Path

        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".st-key-movie_chips", css)
        self.assertIn(".st-key-movie_chips .oc-sec-label", css)
        self.assertIn(
            '.st-key-movie_chips [data-testid="stWidgetLabel"]',
            css,
        )


if __name__ == "__main__":
    unittest.main()
