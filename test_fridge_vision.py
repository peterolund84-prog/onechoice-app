# -*- coding: utf-8 -*-
"""Vision invent: no silent empty, sample image live/dev proof."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from unittest import mock

import fridge_domain as fr

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample_fridge.jpg"
REPORT = Path(__file__).resolve().parent / "artifacts" / "fridge_vision_report.txt"


class FridgeVisionStrictTests(unittest.TestCase):
    def test_placeholder_key_raises_not_empty(self) -> None:
        blob = b"\xff\xd8\xff" + b"x" * 100
        with self.assertRaises(fr.FridgeVisionError) as ctx:
            fr.invent_from_images([blob], api_key="din_grok_api_nyckel_här")
        self.assertEqual(ctx.exception.code, "missing_api_key")

    def test_empty_key_raises(self) -> None:
        blob = b"\xff\xd8\xff" + b"x" * 100
        with self.assertRaises(fr.FridgeVisionError) as ctx:
            fr.invent_from_images([blob], api_key="")
        self.assertEqual(ctx.exception.code, "missing_api_key")

    def test_no_image_raises(self) -> None:
        with self.assertRaises(fr.FridgeVisionError) as ctx:
            fr.invent_from_images([], api_key="xai-real-looking-key-123456")
        self.assertEqual(ctx.exception.code, "no_image")

    def test_parse_prose_raises(self) -> None:
        with self.assertRaises(fr.FridgeVisionError) as ctx:
            fr.parse_inventory_json("Jag ser ägg och mjölk i kylen.")
        self.assertEqual(ctx.exception.code, "parse_json")

    def test_parse_json_ok(self) -> None:
        raw = '{"ingredients":[{"name":"Ägg","confidence":0.9},{"name":"mjölk","confidence":0.8}]}'
        items = fr.parse_inventory_json(raw)
        self.assertEqual([i["name"] for i in items], ["ägg", "mjölk"])

    def test_text_only_model_not_in_list(self) -> None:
        self.assertNotIn("grok-2-latest", fr.VISION_MODELS)

    def test_downscale_caps_long_edge(self) -> None:
        from io import BytesIO

        from PIL import Image

        im = Image.new("RGB", (4000, 2000), (10, 20, 30))
        buf = BytesIO()
        im.save(buf, format="JPEG")
        out, mime = fr.downscale_image(buf.getvalue(), "image/jpeg")
        self.assertEqual(mime, "image/jpeg")
        im2 = Image.open(BytesIO(out))
        self.assertLessEqual(max(im2.size), fr.MAX_IMAGE_EDGE)

    def test_http_failure_raises_not_empty(self) -> None:
        blob = SAMPLE.read_bytes() if SAMPLE.exists() else (b"\xff\xd8\xff" + b"y" * 200)

        class FakeResp:
            status_code = 401
            text = '{"error":"Invalid API key"}'

            def json(self):
                return {"error": "Invalid API key"}

        with mock.patch("fridge_domain.requests.post", return_value=FakeResp()):
            with self.assertRaises(fr.FridgeVisionError) as ctx:
                fr.invent_from_images(
                    [blob],
                    api_key="xai-looks-real-enough-abcdefgh",
                    language="sv",
                )
        self.assertIn(ctx.exception.code, ("all_models_failed", "http_error"))

    def test_successful_mock_returns_ingredients_and_logs_raw(self) -> None:
        blob = SAMPLE.read_bytes() if SAMPLE.exists() else (b"\xff\xd8\xff" + b"z" * 200)
        model_raw = json.dumps(
            {
                "ingredients": [
                    {"name": "mjölk", "confidence": 0.95},
                    {"name": "ägg", "confidence": 0.9},
                    {"name": "ost", "confidence": 0.85},
                ]
            },
            ensure_ascii=False,
        )

        class FakeResp:
            status_code = 200
            text = json.dumps(
                {"choices": [{"message": {"content": model_raw}}]},
                ensure_ascii=False,
            )

            def json(self):
                return json.loads(self.text)

        with mock.patch("fridge_domain.requests.post", return_value=FakeResp()):
            items = fr.invent_from_images(
                [blob],
                api_key="xai-looks-real-enough-abcdefgh",
                language="sv",
            )
        self.assertGreaterEqual(len(items), 1)
        self.assertEqual(fr.LAST_VISION_DEBUG.get("raw_response"), model_raw)
        self.assertEqual(fr.LAST_VISION_DEBUG.get("http_status"), 200)
        self.assertTrue(fr.LAST_VISION_DEBUG.get("image_bytes"))


@unittest.skipUnless(
    bool(os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY")),
    "Set GROK_API_KEY or XAI_API_KEY to run live vision proof",
)
class FridgeVisionLiveSampleTests(unittest.TestCase):
    def test_sample_fridge_returns_ingredients(self) -> None:
        self.assertTrue(SAMPLE.exists(), f"missing {SAMPLE}")
        key = (os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY") or "").strip()
        blob = SAMPLE.read_bytes()
        items = fr.invent_from_images([blob], api_key=key, language="sv", mime_types=["image/jpeg"])
        raw = fr.LAST_VISION_DEBUG.get("raw_response")
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(
            "LIVE FRIDGE VISION REPORT\n"
            f"model={fr.LAST_VISION_DEBUG.get('model')}\n"
            f"endpoint={fr.LAST_VISION_DEBUG.get('endpoint')}\n"
            f"status={fr.LAST_VISION_DEBUG.get('http_status')}\n"
            f"images={fr.LAST_VISION_DEBUG.get('image_bytes')}\n"
            f"parsed_n={fr.LAST_VISION_DEBUG.get('parsed_n')}\n"
            f"names={[i['name'] for i in items]}\n"
            "---- RAW MODEL RESPONSE ----\n"
            f"{raw}\n",
            encoding="utf-8",
        )
        print("\n==== RAW MODEL RESPONSE ====\n", raw, "\n==== END ====\n")
        self.assertIsInstance(raw, str)
        self.assertTrue(raw.strip())
        self.assertGreaterEqual(len(items), 1, f"expected ingredients, got {items}; raw={raw!r}")


if __name__ == "__main__":
    unittest.main()
