from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from molt.config import config_from_workspace
from molt.ollama import generate_recipe, readiness
from molt.core import MoltError, load_json


ROOT = Path(__file__).resolve().parents[1]


class FakeResponse:
    def __init__(self, payload: dict, headers: dict | None = None):
        self.payload = json.dumps(payload).encode("utf-8")
        self.headers = headers or {"Content-Length": str(len(self.payload))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount: int = -1):
        return self.payload if amount < 0 else self.payload[:amount]


class OllamaTests(unittest.TestCase):
    def test_request_uses_schema_and_masks_profile_values(self) -> None:
        recipe = load_json(ROOT / "examples/recipes/expense-v1.json")
        captured: dict = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse({"model": "gemma3:4b", "response": json.dumps(recipe), "prompt_eval_count": 12, "eval_count": 20})

        with patch("molt.ollama.urlopen", fake_urlopen):
            candidate, metadata = generate_recipe("gemma3:4b", "Normalize expenses", {"columns": ["merchant"], "sample": [{"merchant": "PRIVATE_VALUE"}]}, endpoint="http://ollama.test", timeout=3)
        payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(candidate["name"], recipe["name"])
        self.assertEqual(metadata["llm_calls"], 1)
        self.assertIsInstance(payload["format"], dict)
        self.assertIn("schema_version", payload["format"]["properties"])
        self.assertIn("system", payload)
        self.assertNotIn("PRIVATE_VALUE", payload["prompt"])
        self.assertEqual(captured["timeout"], 3)

    def test_invalid_model_recipe_is_rejected(self) -> None:
        invalid_recipe = {"schema_version": 1, "name": "bad", "description": "bad", "input_contract": {}, "operations": [{"type": "run_shell"}], "output_contract": {}}
        def fake_urlopen(request, timeout):
            return FakeResponse({"response": json.dumps(invalid_recipe)})
        with patch("molt.ollama.urlopen", fake_urlopen):
            with self.assertRaises(MoltError) as context:
                generate_recipe("gemma3:4b", "bad", {"columns": []})
        self.assertIn(context.exception.code, {"UNSUPPORTED_OPERATION", "RECIPE_SCHEMA_INVALID"})

    def test_readiness_distinguishes_missing_model(self) -> None:
        with patch("molt.ollama.urlopen", lambda request, timeout: FakeResponse({"models": [{"name": "other:latest"}]})):
            result = readiness("http://ollama.test", "gemma3:4b")
        self.assertEqual(result["status"], "model_missing")

    def test_repair_context_contains_active_recipe_and_drift(self) -> None:
        recipe = load_json(ROOT / "examples/recipes/expense-v1.json")
        captured: dict = {}
        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({"response": json.dumps(recipe)})
        with patch("molt.ollama.urlopen", fake_urlopen):
            generate_recipe("gemma3:4b", "Repair it", {"columns": ["category"]}, active_recipe=recipe, drift_report={"code": "UNMAPPED_VALUE", "column": "category"})
        prompt = captured["payload"]["prompt"]
        self.assertIn("UNMAPPED_VALUE", prompt)
        self.assertIn("normalize_expense_export", prompt)

    def test_environment_configuration_is_used(self) -> None:
        original = {key: os.environ.get(key) for key in ("MOLT_DATA_DIR", "MOLT_HOST", "MOLT_PORT", "OLLAMA_BASE_URL", "MOLT_GEMMA_MODEL", "MOLT_MODEL_TIMEOUT_SECONDS", "MOLT_MODEL_MAX_RETRIES")}
        try:
            os.environ.update({"MOLT_DATA_DIR": "custom-workspace", "MOLT_HOST": "0.0.0.0", "MOLT_PORT": "9001", "OLLAMA_BASE_URL": "http://example.test", "MOLT_GEMMA_MODEL": "gemma-test", "MOLT_MODEL_TIMEOUT_SECONDS": "7", "MOLT_MODEL_MAX_RETRIES": "4"})
            config = config_from_workspace()
            self.assertEqual(config.host, "0.0.0.0")
            self.assertEqual(config.port, 9001)
            self.assertEqual(config.ollama_base_url, "http://example.test")
            self.assertEqual(config.ollama_model, "gemma-test")
            self.assertEqual(config.ollama_timeout_seconds, 7)
            self.assertEqual(config.ollama_max_retries, 4)
        finally:
            for key, value in original.items():
                if value is None: os.environ.pop(key, None)
                else: os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
