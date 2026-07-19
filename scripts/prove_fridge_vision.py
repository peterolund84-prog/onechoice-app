#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dev proof: send fixtures/sample_fridge.jpg to xAI vision and print RAW response.

Usage:
  GROK_API_KEY=xai-... python3 scripts/prove_fridge_vision.py

Exit 0 only if ≥1 ingredient is parsed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import fridge_domain as fr  # noqa: E402

SAMPLE = ROOT / "fixtures" / "sample_fridge.jpg"
OUT = ROOT / "artifacts" / "fridge_vision_report.txt"


def main() -> int:
    key = (os.environ.get("GROK_API_KEY") or os.environ.get("XAI_API_KEY") or "").strip()
    # Also try Streamlit secrets placeholder path for honesty report
    if not key:
        secrets = ROOT / ".streamlit" / "secrets.toml"
        if secrets.exists():
            for line in secrets.read_text().splitlines():
                if line.strip().startswith("GROK_API_KEY"):
                    raw = line.split("=", 1)[-1].strip().strip('"').strip("'")
                    key = raw
                    break

    print("usable_key?", fr.usable_vision_key(key), "len", len(key))
    print("sample exists?", SAMPLE.exists(), SAMPLE)
    if not SAMPLE.exists():
        print("FAIL: missing sample image")
        return 2

    blob = SAMPLE.read_bytes()
    print("sample bytes", len(blob))

    try:
        items = fr.invent_from_images(
            [blob], api_key=key, language="sv", mime_types=["image/jpeg"]
        )
    except fr.FridgeVisionError as exc:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(
            "FRIDGE VISION PROOF — FAILED\n"
            f"code={exc.code}\n"
            f"message={exc}\n"
            f"status={exc.status}\n"
            f"model={exc.model}\n"
            f"debug={fr.LAST_VISION_DEBUG}\n"
            f"raw={exc.raw}\n",
            encoding="utf-8",
        )
        print("FAIL FridgeVisionError:", exc.code, exc)
        print("LAST_VISION_DEBUG:", fr.LAST_VISION_DEBUG)
        return 1

    raw = fr.LAST_VISION_DEBUG.get("raw_response")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    report = (
        "FRIDGE VISION PROOF — OK\n"
        f"model={fr.LAST_VISION_DEBUG.get('model')}\n"
        f"endpoint={fr.LAST_VISION_DEBUG.get('endpoint')}\n"
        f"status={fr.LAST_VISION_DEBUG.get('http_status')}\n"
        f"images={fr.LAST_VISION_DEBUG.get('image_bytes')}\n"
        f"payload_chars={fr.LAST_VISION_DEBUG.get('payload_chars')}\n"
        f"parsed={[i['name'] for i in items]}\n"
        "---- RAW MODEL RESPONSE ----\n"
        f"{raw}\n"
    )
    OUT.write_text(report, encoding="utf-8")
    print(report)
    return 0 if items else 1


if __name__ == "__main__":
    raise SystemExit(main())
