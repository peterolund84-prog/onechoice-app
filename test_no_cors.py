# -*- coding: utf-8 -*-
"""Same-origin HTML+API — no permissive CORS middleware in production."""

from __future__ import annotations

import unittest
from pathlib import Path

from api.main import app


class NoCorsMiddlewareTests(unittest.TestCase):
    def test_no_cors_middleware_registered(self) -> None:
        names = []
        for middleware in app.user_middleware:
            cls = getattr(middleware, "cls", None) or getattr(
                middleware, "__class__", None
            )
            names.append(getattr(cls, "__name__", str(cls)))
        joined = " ".join(names).lower()
        self.assertNotIn("cors", joined)

        main_src = Path(__file__).resolve().parent / "api" / "main.py"
        text = main_src.read_text(encoding="utf-8")
        self.assertNotIn("CORSMiddleware", text)
        self.assertNotIn("allow_origins", text)


if __name__ == "__main__":
    unittest.main()
