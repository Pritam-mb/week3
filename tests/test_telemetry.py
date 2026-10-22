from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from molt.application import MoltService
from molt.config import MoltConfig
from molt.telemetry import Telemetry


ROOT = Path(__file__).resolve().parents[1]


class FakeSpan:
    def __init__(self, name: str) -> None:
        self.name = name
        self.data: dict[str, Any] = {}
        self.closed = False

    def __enter__(self) -> "FakeSpan":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.closed = True

    def set_data(self, key: str, value: Any) -> None:
        self.data[key] = value


class FakeSentry:
    def __init__(self) -> None:
        self.init_args: tuple[Any, ...] | None = None
        self.init_kwargs: dict[str, Any] = {}
        self.spans: list[FakeSpan] = []

    def init(self, *args: Any, **kwargs: Any) -> None:
        self.init_args = args
        self.init_kwargs = kwargs

    def start_span(self, *, name: str, **_kwargs: Any) -> FakeSpan:
        span = FakeSpan(name)
        self.spans.append(span)
        return span


class TelemetryTests(unittest.TestCase):
    def test_disabled_telemetry_records_only_redacted_local_events(self) -> None:
        telemetry = Telemetry("")

        with telemetry.span(
            "automation.profile_csv",
            input_bytes=123,
            row_count=2,
            prompt="raw prompt",
            response="raw response",
            path="C:\\private\\input.csv",
            raw_value="secret-value",
        ):
            pass

        self.assertFalse(telemetry.enabled)
        self.assertEqual(telemetry.status()["mode"], "local-only")
        event = telemetry.events[0]
        self.assertEqual(event["name"], "automation.profile_csv")
        self.assertEqual(event["attributes"], {"input_bytes": 123, "row_count": 2})
        self.assertNotIn("raw prompt", str(event))
        self.assertNotIn("private", str(event))

    def test_mock_sdk_receives_named_redacted_spans_and_scrub_callbacks(self) -> None:
        sdk = FakeSentry()
        telemetry = Telemetry("https://public@example.invalid/1", sdk=sdk)

        with telemetry.span("recipe.compile_gemma", provider="ollama", attempt=1, prompt="do not send", input_rows=4):
            pass

        self.assertTrue(telemetry.enabled)
        self.assertEqual(sdk.init_kwargs["send_default_pii"], False)
        self.assertIn("before_send", sdk.init_kwargs)
        self.assertIn("before_send_transaction", sdk.init_kwargs)
        self.assertEqual(sdk.spans[0].name, "recipe.compile_gemma")
        self.assertEqual(
            sdk.spans[0].data,
            {"provider": "ollama", "attempt": 1, "input_rows": 4, "duration_ms": sdk.spans[0].data["duration_ms"]},
        )
        scrubbed = sdk.init_kwargs["before_send"]({"message": "raw", "request": {"url": "https://private/path"}, "status": "ok", "count": 3, "data": {"prompt": "raw prompt", "input_rows": 4, "free_text": "raw csv value"}})
        self.assertEqual(scrubbed, {"status": "ok", "count": 3, "data": {"input_rows": 4}})

    def test_sdk_failures_do_not_break_application_flow(self) -> None:
        class BrokenSpan(FakeSpan):
            def set_data(self, _key: str, _value: Any) -> None:
                raise RuntimeError("telemetry failed")

            def __exit__(self, *_args: Any) -> None:
                raise RuntimeError("telemetry failed")

        sdk = SimpleNamespace(
            init=lambda *_args, **_kwargs: None,
            start_span=lambda **kwargs: BrokenSpan(kwargs["name"]),
        )
        telemetry = Telemetry("https://public@example.invalid/1", sdk=sdk)
        with telemetry.span("automation.execute_approved_recipe", output_rows=1):
            result = "core-result"
        self.assertEqual(result, "core-result")
        self.assertEqual(telemetry.events[0]["attributes"], {"output_rows": 1})

    def test_disabled_service_workflow_emits_required_local_stage_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory), sentry_dsn=""))
            source = Path(directory) / "orders.csv"
            drift = Path(directory) / "orders-drift.csv"
            shutil.copy2(ROOT / "examples/orders_input.csv", source)
            shutil.copy2(ROOT / "examples/orders_drift_unknown_status.csv", drift)
            automation = service.create_automation("Telemetry workflow")
            version = service.generate_candidate(
                automation["id"],
                "Normalize orders",
                service.profile(source),
                recipe_file=str(ROOT / "examples/recipes/orders-v1.json"),
            )
            self.assertEqual(service.verify_version(version["id"])["status"], "PASS")
            service.approve_version(version["id"])
            blocked = service.run(automation["id"], drift)
            service.propose_repair(
                automation["id"],
                blocked["id"],
                recipe_file=str(ROOT / "examples/recipes/orders-bad-repair.json"),
            )
            service.anomaly_analysis(source)

            names = {event["name"] for event in service.telemetry.events}
            self.assertTrue(
                {
                    "automation.profile_csv",
                    "recipe.compile",
                    "recipe.validate_schema",
                    "recipe.validate_operations",
                    "recipe.verify_examples",
                    "recipe.verify_invariants",
                    "recipe.approve_version",
                    "automation.check_drift",
                    "automation.execute_approved_recipe",
                    "repair.propose",
                    "tabpfn.score_rows",
                } <= names
            )
            self.assertFalse(service.telemetry.enabled)


if __name__ == "__main__":
    unittest.main()
