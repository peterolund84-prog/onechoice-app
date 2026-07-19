# -*- coding: utf-8 -*-
"""Fridge photo → inventory confirm → cook-from-what-you-have."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import fridge_domain as fr
import pipeline


class FridgeDomainUnitTests(unittest.TestCase):
    def test_parse_inventory_json(self) -> None:
        raw = '{"ingredients":[{"name":"Ägg","confidence":0.9},{"name":"paprika","confidence":0.8}]}'
        items = fr.parse_inventory_json(raw)
        self.assertEqual([i["name"] for i in items], ["ägg", "paprika"])

    def test_can_cook_only_available_plus_staples(self) -> None:
        avail = ["ägg", "paprika", "ost"]
        self.assertTrue(fr.can_cook(["ägg", "paprika", "ost", "smör", "salt"], avail))
        self.assertFalse(fr.can_cook(["ägg", "paprika", "ost", "kyckling"], avail))

    def test_omelette_candidate_from_inventory(self) -> None:
        cands = fr.fridge_candidates(["ägg", "paprika", "ost"], language="sv")
        self.assertTrue(cands)
        top = cands[0]
        self.assertIn("omelett", top["suggestion"].lower())
        self.assertIn("ägg", top["justification"].lower())
        self.assertEqual(top["meta"]["source"], fr.SOURCE)

    def test_fallback_with_eggs_no_bread_is_scramble(self) -> None:
        fb = fr.fridge_fallback(["ägg"], language="sv")
        self.assertEqual(fb["suggestion"], "Äggröra")
        self.assertNotIn("bröd", fb["meta"]["ingredients"])
        self.assertTrue(fb["meta"]["offers_shopping"])
        self.assertIn("inköpslista", fb["justification"])

    def test_fallback_eggs_and_bread_is_sandwich(self) -> None:
        fb = fr.fridge_fallback(["ägg", "bröd"], language="sv")
        self.assertEqual(fb["suggestion"], "Äggmackor")
        self.assertIn("bröd", fb["meta"]["ingredients"])

    def test_yoghurt_jam_candidate(self) -> None:
        cands = fr.fridge_candidates(
            ["yoghurt", "ägg", "sylt", "smör", "saft"], language="sv"
        )
        names = [c["suggestion"].lower() for c in cands]
        self.assertTrue(any("yoghurt" in n and "sylt" in n for n in names), names)
        self.assertFalse(any("ost" in n for n in names), names)
        self.assertFalse(any("macka" in n for n in names), names)

    def test_title_cues_require_cheese(self) -> None:
        self.assertIn("ost", fr.ingredients_cued_by_text("Macka med ost"))
        self.assertIn("bröd", fr.ingredients_cued_by_text("Macka med ost"))
        self.assertFalse(
            fr.can_cook(
                fr.fridge_required_ingredients("Macka med ost", ["ägg", "smör"]),
                ["yoghurt", "ägg", "sylt", "smör", "saft"],
            )
        )

    def test_fallback_empty_pantry(self) -> None:
        fb = fr.fridge_fallback(["diskmedel"], language="sv")
        self.assertTrue(fb["meta"]["fridge_fallback"])
        self.assertTrue(fb["meta"]["offers_shopping"])


class FridgePipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "t.db")
        db.init_db(self.db_path)
        self.user = db.ensure_user(language="sv", path=self.db_path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_decide_fridge_no_shopping_logs_source(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad laga från kylen?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={
                "source": fr.SOURCE,
                "available_ingredients": ["ägg", "paprika", "ost"],
                "meal_type": "middag",
            },
        )
        self.assertTrue(r.ok)
        self.assertEqual((r.context or {}).get("source"), fr.SOURCE)
        self.assertIsNone((r.context or {}).get("shopping"))
        self.assertNotEqual(r.execution_label, "Handla & laga")
        self.assertIn("ägg", (r.justification or "").lower())
        # Must not require ingredients outside inventory
        recipe = (r.context or {}).get("recipe") or {}
        ings = [str(x).lower() for x in (recipe.get("ingredients") or [])]
        for item in ings:
            if fr._is_staple(item):
                continue
            self.assertTrue(
                fr._covers(item, {"ägg", "paprika", "ost"}),
                f"recipe requires missing {item}",
            )

    def test_decide_fridge_rejects_impossible_via_fallback(self) -> None:
        r = pipeline.decide(
            self.user["id"],
            "Vad laga?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={
                "source": fr.SOURCE,
                "available_ingredients": ["citron"],
                "meal_type": "middag",
            },
        )
        self.assertTrue(r.ok)
        self.assertTrue((r.context or {}).get("fridge_fallback") or (r.context or {}).get("offers_shopping"))
        self.assertIsNone((r.context or {}).get("shopping"))

    def test_misread_cannot_force_missing_protein(self) -> None:
        """Feasibility must drop dishes that need kyckling when inventory lacks it."""
        import feasibility

        profile = feasibility.parse_profile(self.user, {"source": fr.SOURCE})
        ctx = {
            "source": fr.SOURCE,
            "available_ingredients": ["ägg", "mjölk"],
            "meal_type": "middag",
            "language": "sv",
        }
        bad = {
            "suggestion": "Kycklinggryta",
            "justification": "Gott",
            "meta": {
                "ingredients": ["kyckling", "grädde", "lök"],
                "source": fr.SOURCE,
                "available_ingredients": ["ägg", "mjölk"],
            },
        }
        result = feasibility.feasibility_check(
            bad, domain="food", profile=profile, context=ctx
        )
        self.assertFalse(result.ok)

    def test_title_cheese_rejected_when_meta_hides_it(self) -> None:
        """LLM naming cheese in the title must fail even if meta omits ost."""
        import feasibility

        profile = feasibility.parse_profile(self.user, {"source": fr.SOURCE})
        avail = ["yoghurt", "ägg", "sylt", "smör", "saft"]
        ctx = {
            "source": fr.SOURCE,
            "available_ingredients": avail,
            "meal_type": "frukost",
            "language": "sv",
        }
        sneaky = {
            "suggestion": "Macka med ost",
            "justification": "Du har ägg och smör",
            "meta": {
                "ingredients": ["ägg", "smör"],
                "source": fr.SOURCE,
                "available_ingredients": avail,
            },
        }
        result = feasibility.feasibility_check(
            sneaky, domain="food", profile=profile, context=ctx
        )
        self.assertFalse(result.ok)
        self.assertIn("fridge_missing_ingredient", result.reasons)

        r = pipeline.decide(
            self.user["id"],
            "Vad laga från kylen?",
            domain_hint="food",
            language="sv",
            db_path=self.db_path,
            context_extra={
                "source": fr.SOURCE,
                "available_ingredients": avail,
                "meal_type": "frukost",
            },
        )
        self.assertTrue(r.ok)
        title = (r.suggestion or "").lower()
        self.assertNotIn("ost", title)
        self.assertFalse("macka" in title and "ost" in title)
        # Honest dish from what was seen
        self.assertTrue(
            "yoghurt" in title or "äggröra" in title or "ägg" in title,
            r.suggestion,
        )


class FridgeUiTests(unittest.TestCase):
    def test_home_exposes_fridge_entry(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=45)
        at.run()
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any("kylen" in lab.lower() for lab in labels), labels)

    def test_confirm_inventory_then_decide(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=60)
        at.run()
        for b in at.button:
            if b.label and "kylen" in b.label.lower():
                b.click().run()
                break
        self.assertEqual(at.session_state["page"], "fridge")
        # Jump to confirm with known inventory (skip vision)
        at.session_state["fridge_step"] = "confirm"
        at.session_state["fridge_inventory"] = [
            {"name": "ägg", "confidence": 1.0},
            {"name": "paprika", "confidence": 1.0},
            {"name": "ost", "confidence": 1.0},
        ]
        at.run()
        body = " ".join(str(m.value or "") for m in at.markdown)
        self.assertIn("ägg", body.lower())
        hit = False
        for b in at.button:
            if b.label and ("bestäm" in b.label.lower() or "pick a dish" in b.label.lower()):
                b.click().run()
                hit = True
                break
        self.assertTrue(hit)
        self.assertFalse(bool(at.session_state["ui_error"]))
        self.assertEqual(at.session_state["page"], "result")
        cur = at.session_state["current"] or {}
        ctx = cur.get("context") or {}
        if isinstance(ctx, str):
            import json

            ctx = json.loads(ctx)
        self.assertEqual(ctx.get("source"), fr.SOURCE)
        self.assertIsNone(ctx.get("shopping"))
        self.assertTrue(bool(at.session_state["fridge_mode"]))


if __name__ == "__main__":
    unittest.main()
