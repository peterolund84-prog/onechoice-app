# -*- coding: utf-8 -*-
"""Central validate_output gate + movie offline honesty."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db
import movie_domain as md
import pipeline


class ValidateOutputTests(unittest.TestCase):
    def test_rejects_instruction_leak(self) -> None:
        bad = {
            "domain": "movie",
            "suggestion": "Seinfeld",
            "justification": "low cognitive load, familiar, comfort rewatch OK",
            "meta": {"title": "seinfeld"},
        }
        ok, reason = pipeline.validate_output(bad, "sv")
        self.assertFalse(ok)
        self.assertIn("instruction_leak", reason)

    def test_rejects_english_justification_for_sv(self) -> None:
        bad = {
            "domain": "food",
            "suggestion": "Pasta",
            "justification": "This is the best dinner with your friends and the family",
        }
        ok, reason = pipeline.validate_output(bad, "sv")
        self.assertFalse(ok)
        self.assertIn("language_mismatch", reason)

    def test_rejects_swedish_justification_for_en(self) -> None:
        bad = {
            "domain": "food",
            "suggestion": "Pasta",
            "justification": "Det här är en varm rätt med ost och pasta för kvällen",
        }
        ok, reason = pipeline.validate_output(bad, "en")
        self.assertFalse(ok)
        self.assertIn("language_mismatch", reason)

    def test_accepts_swedish_mood_line(self) -> None:
        good = {
            "domain": "movie",
            "suggestion": "Seinfeld",
            "justification": "Lugn bekant sitcom — perfekt måndagssoffa.",
            "meta": {"title": "seinfeld", "kind": "series"},
        }
        ok, reason = pipeline.validate_output(good, "sv")
        self.assertTrue(ok, reason)

    def test_rejects_fake_movie_title(self) -> None:
        bad = {
            "domain": "movie",
            "suggestion": "En film under två timmar",
            "justification": "Lätt kväll.",
            "meta": {"kind": "film"},
        }
        ok, reason = pipeline.validate_output(bad, "sv")
        self.assertFalse(ok)
        self.assertEqual(reason, "movie_fake_title")

    def test_rejects_ungrounded_leftover(self) -> None:
        bad = {
            "domain": "food",
            "suggestion": "Matlåda från gårdagens kyckling",
            "justification": "Värm resterna.",
            "context": {},
            "meta": {},
        }
        ok, reason = pipeline.validate_output(bad, "sv")
        self.assertFalse(ok)
        self.assertEqual(reason, "ungrounded_leftover")


class MovieOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "m.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_movie_without_llm_is_honest_offline(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad ska jag titta på?",
            domain_hint="movie",
            language="sv",
            db_path=self.path,
            grok_api_key="",  # unreachable / missing
            context_extra={"format": "film", "mood": "avkopplat"},
        )
        self.assertFalse(r.ok)
        self.assertTrue(r.refused)
        self.assertIn("Kan inte välja film", r.refusal_message or "")
        self.assertTrue((r.context or {}).get("llm_offline"))
        self.assertFalse(r.suggestion)
        # No fake category cards
        self.assertNotIn("två timmar", (r.suggestion or "").lower())

    def test_local_candidates_empty(self) -> None:
        self.assertEqual(
            md.local_candidates(fmt="film", mood="avkopplat", language="sv"),
            [],
        )

    def test_instruction_leak_triggers_retry_then_offline(self) -> None:
        leak = [
            {
                "suggestion": "Seinfeld",
                "justification": "cognitive load is low — reference the mood",
                "meta": {"title": "seinfeld", "kind": "series"},
                "wildcard": False,
            }
        ] * 5
        calls = {"n": 0}

        def fake_gen(**kwargs):  # noqa: ANN003
            calls["n"] += 1
            return list(leak)

        with mock.patch.object(pipeline, "_generate_candidates", side_effect=fake_gen):
            r = pipeline.decide(
                self.user["id"],
                "film",
                domain_hint="movie",
                language="sv",
                db_path=self.path,
                grok_api_key="xai-test-key-long",
                context_extra={"format": "avsnitt", "mood": "avkopplat"},
            )
        self.assertGreaterEqual(calls["n"], 2)  # first + corrective retry
        self.assertFalse(r.ok)
        self.assertTrue(r.refused)
        self.assertTrue((r.context or {}).get("llm_offline") or (r.context or {}).get("validation_reason"))

    def test_mocked_llm_named_title_passes(self) -> None:
        good = [
            {
                "suggestion": "Seinfeld",
                "justification": "Lugn bekant sitcom — perfekt måndagssoffa.",
                "meta": {"title": "seinfeld", "kind": "series"},
                "wildcard": False,
            },
            {
                "suggestion": "Vänner",
                "justification": "Varm och lätt efter jobbet.",
                "meta": {"title": "vänner", "kind": "series"},
                "wildcard": False,
            },
            {
                "suggestion": "Wednesday",
                "justification": "Mörk humor i lagom dos för soffan.",
                "meta": {"title": "wednesday", "kind": "series"},
                "wildcard": True,
            },
            {
                "suggestion": "The Night Agent",
                "justification": "Högt tempo när du vill bli uppslukad.",
                "meta": {"title": "the night agent", "kind": "series"},
                "wildcard": False,
            },
            {
                "suggestion": "Andor",
                "justification": "Tät spänning i ett avsnitt.",
                "meta": {"title": "andor", "kind": "series"},
                "wildcard": False,
            },
        ]

        with mock.patch.object(pipeline, "_generate_candidates", return_value=good):
            r = pipeline.decide(
                self.user["id"],
                "Vad ska jag titta på?",
                domain_hint="movie",
                language="sv",
                db_path=self.path,
                grok_api_key="xai-test-key-long",
                context_extra={"format": "avsnitt", "mood": "avkopplat"},
            )
        self.assertTrue(r.ok, (r.refusal_message, r.context))
        self.assertTrue(md.is_named_title(r.suggestion, {"title": "seinfeld"}))
        self.assertNotIn("cognitive", (r.justification or "").lower())
        self.assertTrue(r.execution_url or r.execution_label)

    def test_validation_failure_logged(self) -> None:
        db.log_validation_failure(
            decision_domain="movie",
            reason="instruction_leak:cognitive load",
            source="test",
            language="sv",
            path=self.path,
        )
        with db.get_conn(self.path) as conn:
            n = conn.execute("SELECT COUNT(*) AS c FROM validation_failures").fetchone()["c"]
        self.assertGreaterEqual(int(n), 1)


class CrossDomainLanguageTests(unittest.TestCase):
    """Mocked local-ish decisions must pass language gate for sv/en."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "x.db")
        db.init_db(self.path)
        self.user = db.ensure_user(language="sv", path=self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _assert_lang(self, language: str, domain: str, pack: list[dict]) -> None:
        with mock.patch.object(pipeline, "_generate_candidates", return_value=pack):
            # Movie needs key path; others can be empty key with local — force gen mock
            r = pipeline.decide(
                self.user["id"],
                pipeline._default_question(domain, language),
                domain_hint=domain,
                language=language,
                db_path=self.path,
                grok_api_key="xai-test-key-long" if domain == "movie" else "",
                context_extra=(
                    {"format": "avsnitt", "mood": "avkopplat"}
                    if domain == "movie"
                    else {"meal_type": "middag"}
                    if domain == "food"
                    else {"occasion": "vardag"}
                    if domain == "clothes"
                    else None
                ),
                skip_feasibility=(domain == "weekend"),  # loosen for mock titles
            )
        if domain == "movie" and not r.ok:
            # Feasibility may reject unsubscribed titles — still must not leak EN
            self.assertNotRegex(
                (r.refusal_message or "") + (r.justification or ""),
                r"\b(the|and|with|your)\b",
            )
            return
        self.assertTrue(r.ok, (domain, language, r.refusal_message, r.suggestion))
        ok, reason = pipeline.validate_output(
            {
                "domain": domain,
                "suggestion": r.suggestion,
                "justification": r.justification,
                "meta": (r.context or {}).get("meta") or {},
                "context": r.context or {},
            },
            language,
        )
        self.assertTrue(ok, (domain, language, reason, r.suggestion, r.justification))

    def test_sv_ten_per_domain(self) -> None:
        packs = {
            "food": [
                {
                    "suggestion": f"Kycklingwok {i}",
                    "justification": "Varm och klar på trettio minuter med ris.",
                    "meta": {"active_minutes": 25, "ingredients": ["kyckling", "ris", "grönsaker"]},
                    "wildcard": False,
                }
                for i in range(5)
            ],
            "clothes": [
                {
                    "suggestion": "Mörka jeans + vit t-shirt + sneakers",
                    "justification": "Rent och säkert för vardagen på stan.",
                    "meta": {"occasion": "vardag"},
                    "wildcard": False,
                }
            ]
            * 5,
            "movie": [
                {
                    "suggestion": "Seinfeld",
                    "justification": "Lugn bekant sitcom — perfekt måndagssoffa.",
                    "meta": {"title": "seinfeld", "kind": "series"},
                    "wildcard": False,
                }
            ]
            * 5,
            "workout": [
                {
                    "suggestion": "30 minuters helkroppsstyrka hemma",
                    "justification": "Effektivt och klart innan motivationen sviktar.",
                    "meta": {"minutes": 30},
                    "wildcard": False,
                }
            ]
            * 5,
            "weekend": [
                {
                    "suggestion": "Kaffepromenad + en bokhandel",
                    "justification": "Enkelt och lagom socialt för helgen.",
                    "meta": {},
                    "wildcard": False,
                }
            ]
            * 5,
        }
        for domain in ("food", "clothes", "movie", "workout", "weekend"):
            for _ in range(2):  # 2 decides × 5 candidates ≈ coverage without 10 full LLM rounds
                self._assert_lang("sv", domain, packs[domain])

    def test_en_ten_per_domain(self) -> None:
        packs = {
            "food": [
                {
                    "suggestion": f"Chicken stir-fry {i}",
                    "justification": "Warm and done in thirty minutes with rice.",
                    "meta": {"active_minutes": 25, "ingredients": ["chicken", "rice", "veg"]},
                    "wildcard": False,
                }
                for i in range(5)
            ],
            "clothes": [
                {
                    "suggestion": "Dark jeans + white tee + sneakers",
                    "justification": "Clean and safe for a weekday in town.",
                    "meta": {"occasion": "vardag"},
                    "wildcard": False,
                }
            ]
            * 5,
            "movie": [
                {
                    "suggestion": "Seinfeld",
                    "justification": "Familiar comfort sitcom for a quiet evening sofa.",
                    "meta": {"title": "seinfeld", "kind": "series"},
                    "wildcard": False,
                }
            ]
            * 5,
            "workout": [
                {
                    "suggestion": "30-minute full-body strength at home",
                    "justification": "Efficient — done before motivation dips for you.",
                    "meta": {"minutes": 30},
                    "wildcard": False,
                }
            ]
            * 5,
            "weekend": [
                {
                    "suggestion": "Coffee walk + one bookstore",
                    "justification": "Simple and social enough for the weekend.",
                    "meta": {},
                    "wildcard": False,
                }
            ]
            * 5,
        }
        for domain in ("food", "clothes", "movie", "workout", "weekend"):
            for _ in range(2):
                self._assert_lang("en", domain, packs[domain])


if __name__ == "__main__":
    unittest.main()
