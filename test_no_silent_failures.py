# -*- coding: utf-8 -*-
"""Lint: no bare `except Exception: pass` swallow-and-continue in app.py."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


_BARE_SWALLOW = re.compile(
    r"(?m)^(?P<indent>[ \t]*)except Exception(?: as \w+)?:\n(?P=indent)[ \t]+pass\b"
)


class NoSilentFailuresLint(unittest.TestCase):
    def test_app_py_has_zero_bare_exception_pass(self) -> None:
        src = (Path(__file__).resolve().parent / "app.py").read_text(encoding="utf-8")
        hits = []
        for m in _BARE_SWALLOW.finditer(src):
            line = src[: m.start()].count("\n") + 1
            snippet = m.group(0).splitlines()[0]
            hits.append(f"L{line}: {snippet}")
        self.assertEqual(
            hits,
            [],
            "Bare except Exception: pass is forbidden — log or remove the try/except:\n"
            + "\n".join(hits),
        )


if __name__ == "__main__":
    unittest.main()
