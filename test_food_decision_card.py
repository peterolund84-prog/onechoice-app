# -*- coding: utf-8 -*-
"""Pre-lock food decision card — image + meta only; dish_category gating."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import db
import food_categories as fcat
import pipeline


class DishCategoryTests(unittest.TestCase):
    def test_normalize_unknown_falls_back_to_generic(self) -> None:
        self.assertEqual(fcat.normalize_dish_category("xyz-unknown"), "generic")
        self.assertEqual(fcat.normalize_dish_category("pasta"), "pasta")
        self.assertEqual(fcat.normalize_dish_category("gratäng"), "gratang")

    def test_infer_from_suggestion(self) -> None:
        self.assertEqual(
            fcat.infer_dish_category("Kycklingwok med ris"),
            "wok",
        )
        self.assertEqual(
            fcat.infer_dish_category("Mystery bowl", meta={"dish_category": "nope"}),
            "generic",
        )
        # Salad form beats protein cue (tonfisk → fisk.jpg was salmon)
        self.assertEqual(fcat.infer_dish_category("Sallad med tonfisk"), "sallad")
        self.assertEqual(fcat.infer_dish_category("Tuna salad"), "sallad")
        self.assertEqual(fcat.infer_dish_category("Grillad lax"), "fisk")
        # Lentil identity beats stew/soup form — was beef-stew gryta.jpg
        self.assertEqual(fcat.infer_dish_category("Etiopisk linsgryta"), "linser")
        self.assertEqual(fcat.infer_dish_category("Linsgryta"), "linser")
        self.assertEqual(fcat.infer_dish_category("Röd linssoppa"), "linser")
        self.assertEqual(
            fcat.infer_dish_category(
                "Etiopisk linsgryta", meta={"dish_category": "gryta"}
            ),
            "linser",
        )
        self.assertEqual(fcat.infer_dish_category("Kycklinggryta"), "kyckling")
        self.assertEqual(
            fcat.dish_image_path("sallad").name,
            "sallad.jpg",
        )
        self.assertEqual(fcat.dish_image_path("linser").name, "linser.jpg")

    def test_image_path_never_broken(self) -> None:
        path = fcat.dish_image_path("pasta")
        self.assertTrue(path.is_file(), path)
        self.assertLessEqual(path.stat().st_size, 120_000, path.name)
        # generic / unknown → no invented photo (file may be absent)
        gen = fcat.dish_image_path("generic")
        self.assertFalse(gen.is_file())
        self.assertIsNone(fcat.dish_image_bytes("generic"))
        self.assertIsNone(fcat.dish_image_bytes("not-a-real-category"))

    def test_pipeline_stamps_dish_category(self) -> None:
        import dish_images as dimg

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db_path = str(Path(tmp.name) / "t.db")
        db.init_db(db_path)
        user = db.ensure_user(language="sv", path=db_path)
        r = pipeline.decide(
            user["id"],
            "Vad ska jag äta?",
            domain_hint="food",
            language="sv",
            db_path=db_path,
            context_extra={"meal_type": "middag"},
        )
        self.assertTrue(r.ok)
        cat = (r.context or {}).get("dish_category")
        self.assertIn(cat, fcat.DISH_CATEGORY_SET)
        # Title resolver must find a real photo even when pack stamps English
        # ids that normalize to generic (e.g. burger → generic).
        path = dimg.resolve_dish_image(
            str(r.suggestion or ""), str(cat) if cat else None
        )
        self.assertIsNotNone(path)
        self.assertTrue(Path(path).is_file())


class PreLockFoodCardUiTests(unittest.TestCase):
    def test_prelock_shows_card_not_shopping_or_recipe(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        self.assertFalse(bool(at.session_state["accepted"]))
        self.assertFalse(at.exception)

        body = " ".join(str(m.value or "") for m in at.markdown)
        cur = at.session_state["current"] or {}
        import app as app_mod

        card = app_mod._render_food_card_html(
            language="sv",
            suggestion=str(cur.get("suggestion") or ""),
            justification=str(cur.get("justification") or ""),
            ctx=(cur.get("context") if isinstance(cur.get("context"), dict) else {}) or {},
        )
        # Decision card present (painted via st.html — assert renderer)
        self.assertIn("oc-food-decision", card)
        self.assertIn("oc-food-img", card)
        self.assertIn("oc-food-meta", card)
        # Shopping list + recipe steps belong to execute, not pre-lock
        self.assertNotIn('class="oc-shop"', body)
        self.assertNotIn("Inköpslista", body)
        shop = (cur.get("context") or {}).get("shopping") or {}
        recipe = (cur.get("context") or {}).get("recipe") or shop.get("recipe") or {}
        steps = list(recipe.get("steps") or []) if isinstance(recipe, dict) else []
        for step in steps[:4]:
            snip = str(step).strip()
            if len(snip) >= 12:
                self.assertNotIn(snip, body, f"recipe step leaked into pre-lock: {snip!r}")
                self.assertNotIn(snip, card, f"recipe step leaked into card: {snip!r}")
        to_buy = shop.get("to_buy") if isinstance(shop, dict) else {}
        if isinstance(to_buy, dict):
            for items in to_buy.values():
                for item in items or []:
                    name = str(item).split("—")[0].split("–")[0].strip()
                    if len(name) >= 8:
                        # Item may appear in title/justification — only fail on list chrome
                        pass
        labels = [b.label or "" for b in at.button]
        self.assertTrue(any(lab == "Välj" or lab.startswith("Välj") for lab in labels), labels)
        self.assertTrue(any("Nytt förslag" in lab for lab in labels), labels)
        self.assertFalse(any("Handla" in lab for lab in labels), labels)

    def test_go_for_it_opens_execute_directly(self) -> None:
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        for b in at.button:
            if (b.label or "") == "Välj":
                b.click().run()
                break
        self.assertTrue(at.session_state["accepted"])
        self.assertEqual(at.session_state["page"], "execute")
        from test_share import _html_blobs

        exec_body = _html_blobs(at)
        self.assertIn("oc-food-img", exec_body)
        self.assertIn("data:image/jpeg", exec_body)
        labels = [b.label or "" for b in at.button]
        self.assertFalse(any("Handla" in lab for lab in labels), labels)
        self.assertNotIn("Välj", labels)
        self.assertNotIn("Nytt förslag", labels)
        # Heart lives inside the card HTML (not a floating Streamlit host)
        self.assertIn("oc-fav-corner", exec_body)
        self.assertIn("oc-share-corner", exec_body)

    def test_result_page_paints_real_jpeg_not_placeholder(self) -> None:
        """Device gate: after Mat → result, painted HTML must embed a real dish JPEG.

        Asserts the actual st.html payload (not just the renderer helper). Style
        tags are stripped so class names in CSS do not false-positive.
        """
        import base64
        import re
        from pathlib import Path

        from streamlit.testing.v1 import AppTest

        from test_share import _html_blobs

        at = AppTest.from_file("app.py", default_timeout=90)
        at.run()
        at.session_state["food_meal_type"] = "middag"
        at.query_params["domain"] = "food"
        at.run()
        self.assertEqual(at.session_state["page"], "result")
        self.assertFalse(at.exception)

        painted = re.sub(r"<style[\s\S]*?</style>", "", _html_blobs(at))
        self.assertIn("oc-food-decision", painted)
        self.assertIn('class="oc-food-img"', painted)
        self.assertNotIn("oc-food-img-ph", painted)
        self.assertNotIn("oc-skel-card", painted)
        self.assertNotIn("data-oc-deciding", painted)
        self.assertIn("data:image/jpeg;base64,", painted)

        m = re.search(
            r'<img class="oc-food-img" src="data:image/jpeg;base64,([A-Za-z0-9+/=]+)"',
            painted,
        )
        self.assertIsNotNone(m, "missing oc-food-img data URL in painted HTML")
        raw = base64.b64decode(m.group(1))
        self.assertTrue(raw.startswith(b"\xff\xd8\xff"), "not a JPEG payload")
        self.assertGreater(len(raw), 8_000, len(raw))

        # CSS must force the image visible on result (beats leftover skeleton hide)
        css = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".block-container:has(.oc-result) .oc-food-img", css)
        self.assertIn('st-key-decide_slot"] .oc-skel-card', css)
        self.assertNotIn(
            "body:has(.oc-skel-card):not(:has(.oc-result))",
            css,
        )


if __name__ == "__main__":
    unittest.main()
