# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import api.secrets as secrets


class ApiSecretsTests(unittest.TestCase):
    def test_normalize_strips_quotes_and_bearer(self) -> None:
        self.assertEqual(secrets._normalize_secret_value('  "xai-abc"  '), "xai-abc")
        self.assertEqual(secrets._normalize_secret_value("Bearer xai-abc"), "xai-abc")

    def test_toml_wins_over_env(self) -> None:
        td = Path(tempfile.mkdtemp())
        (td / ".streamlit").mkdir()
        (td / ".streamlit" / "secrets.toml").write_text(
            'GROK_API_KEY = "xai-from-toml-123456"\n',
            encoding="utf-8",
        )
        prev = os.environ.get("GROK_API_KEY")
        os.environ["GROK_API_KEY"] = "xai-from-env-XXXXXX"
        orig_paths = secrets.secrets_paths
        try:
            secrets.secrets_paths = lambda: [td / ".streamlit" / "secrets.toml"]  # type: ignore[assignment]
            secrets.reload_secrets()
            self.assertEqual(secrets.grok_api_key(), "xai-from-toml-123456")
            diag = secrets.grok_key_diagnostics()
            self.assertEqual(diag["source"], "secrets.toml")
            self.assertTrue(diag["env_differs_from_toml"])
        finally:
            secrets.secrets_paths = orig_paths  # type: ignore[assignment]
            if prev is None:
                os.environ.pop("GROK_API_KEY", None)
            else:
                os.environ["GROK_API_KEY"] = prev
            secrets.reload_secrets()


if __name__ == "__main__":
    unittest.main()
