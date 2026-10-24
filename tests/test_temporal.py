from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import shutil
import os
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import MoltError, save_json, write_csv_atomic
from molt.temporal import (
    build_run_request,
    default_workflow_id,
    execute_run_activity,
    describe_workflow,
    require_temporal,
    temporalio_available,
)


class _FakeService:
    def __init__(self, config: object):
        self.config = config
        self.called_with: dict[str, object] = {}

    def run(self, automation_id: str, input_path: str, *, output_path: str | None, use_checkpoints: bool) -> dict[str, object]:
        self.called_with = {
            "automation_id": automation_id,
            "input_path": input_path,
            "output_path": output_path,
            "use_checkpoints": use_checkpoints,
        }
        return {
            "status": "BLOCKED_DRIFT",
            "error_code": "UNMAPPED_VALUE",
            "error_message": "Unknown status",
            "error_details": {"column": "status", "value": "in progress"},
        }


class _ReplayService:
    def __init__(self, config: object):
        self.config = config

    def run(self, *args: object, **kwargs: object) -> dict[str, object]:
        raise MoltError("DUPLICATE_FILE_EVENT", "Already recorded", details={"run_id": "run_existing"})

    def get_run(self, run_id: str) -> dict[str, object]:
        return {"run_id": run_id, "status": "SUCCEEDED", "llm_calls": 0}


class TemporalOptionalTests(unittest.TestCase):
    def test_completed_status_exposes_only_aggregate_result(self) -> None:
        handle = SimpleNamespace(
            describe=AsyncMock(return_value=SimpleNamespace(status=SimpleNamespace(name="COMPLETED"))),
            result=AsyncMock(return_value={"status": "BLOCKED_DRIFT", "llm_calls": 0,
                                          "input": "/private/path.csv", "error_message": "PRIVATE_VALUE"}),
        )
        client = SimpleNamespace(get_workflow_handle=lambda workflow_id: handle)
        with patch("molt.temporal.require_temporal"), patch("molt.temporal._TemporalClient", SimpleNamespace(connect=AsyncMock(return_value=client))):
            result = describe_workflow(workflow_id="test-workflow")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["result"]["status"], "BLOCKED_DRIFT")
        self.assertNotIn("PRIVATE_VALUE", json.dumps(result))
        self.assertNotIn("/private", json.dumps(result))

    @unittest.skipUnless(temporalio_available(), "Optional Temporal SDK not installed")
    def test_evidence_uses_real_event_enum_and_attempt_number(self) -> None:
        from temporalio.api.enums.v1 import EventType
        from temporalio.api.history.v1 import HistoryEvent, ActivityTaskStartedEventAttributes
        from temporal_crash_recovery import _event_type, activity_attempts

        scheduled = HistoryEvent(event_type=EventType.EVENT_TYPE_WORKFLOW_TASK_SCHEDULED)
        started = HistoryEvent(event_type=EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED,
                               activity_task_started_event_attributes=ActivityTaskStartedEventAttributes(attempt=3))
        self.assertEqual(_event_type(scheduled), "WORKFLOW_TASK_SCHEDULED")
        self.assertEqual(activity_attempts([scheduled, started]), 3)

    def test_checkpoint_metadata_replacement_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            save_json(state, {"completed_steps": 1})
            with patch("molt.core.os.replace", side_effect=OSError("interrupted publish")):
                with self.assertRaises(OSError):
                    save_json(state, {"completed_steps": 2})
            self.assertEqual(json.loads(state.read_text()), {"completed_steps": 1})
            self.assertEqual(list(Path(directory).iterdir()), [state])

    def test_atomic_output_never_replaces_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.csv"
            output.write_bytes(b"existing output")
            with self.assertRaises(FileExistsError):
                write_csv_atomic(output, ["a"], [{"a": "new"}], overwrite=False)
            self.assertEqual(output.read_bytes(), b"existing output")
            self.assertEqual(list(Path(directory).iterdir()), [output])

    def test_retry_after_output_publish_reconciles_without_overwriting(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            source = service.config.input_dir / "golden.csv"
            shutil.copy2(root / "examples/input/golden.csv", source)
            output = service.config.done_dir / "output.csv"
            automation = service.create_automation("Publish recovery")
            version = service.generate_candidate(automation["id"], "Normalize", service.profile(source), recipe_file=str(root / "examples/recipes/expense-v1.json"))
            service.verify_version(version["id"])
            service.approve_version(version["id"])
            artifact = service._artifact

            def crash_after_publish(path, kind):
                if kind == "output":
                    raise RuntimeError("worker died before recording output")
                return artifact(path, kind)

            with patch.object(service, "_artifact", side_effect=crash_after_publish):
                with self.assertRaises(RuntimeError):
                    service.run(automation["id"], source, output_path=output, use_checkpoints=True)
            before = (output.read_bytes(), output.stat().st_mtime_ns)
            result = service.run(automation["id"], source, output_path=output, use_checkpoints=True)
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), before)
            self.assertEqual(service.metrics()["total_runs"], 1)

    def test_module_imports_without_temporal_sdk(self) -> None:
        # The test environment intentionally has no temporalio package. If an
        # opt-in environment installs it, the import is still the behavior we
        # need to preserve.
        self.assertIn(temporalio_available(), {True, False})
        if not temporalio_available():
            with self.assertRaises(MoltError) as context:
                require_temporal()
            self.assertEqual(context.exception.code, "TEMPORAL_UNAVAILABLE")

    def test_drift_is_returned_as_data_and_checkpoint_mode_is_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = build_run_request(directory, "auto_123", Path(directory) / "in.csv")
            service = _FakeService(None)
            result = execute_run_activity(request, service_factory=lambda config: service)
        self.assertEqual(result["status"], "BLOCKED_DRIFT")
        self.assertEqual(result["temporal_outcome"], "drift")
        self.assertFalse(result["retryable"])
        self.assertEqual(result["drift"]["details"]["column"], "status")
        self.assertTrue(service.called_with["use_checkpoints"])

    def test_duplicate_activity_is_replayed_from_existing_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request = build_run_request(directory, "auto_123", Path(directory) / "in.csv")
            result = execute_run_activity(request, service_factory=_ReplayService)
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["temporal_outcome"], "idempotent_replay")
        self.assertFalse(result["retryable"])

    def test_activity_uses_real_service_checkpoints_and_idempotency(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            config = MoltConfig(Path(directory))
            service = MoltService(config)
            source = config.input_dir / "golden.csv"
            shutil.copy2(root / "examples/input/golden.csv", source)
            automation = service.create_automation("Temporal execution", "Use the approved fixture")
            version = service.generate_candidate(
                automation["id"],
                "Normalize the fixture",
                service.profile(source),
                recipe_file=str(root / "examples/recipes/expense-v1.json"),
            )
            self.assertEqual(service.verify_version(version["id"])["status"], "PASS")
            service.approve_version(version["id"])
            request = build_run_request(directory, automation["id"], source)

            first = execute_run_activity(request)
            self.assertEqual(first["status"], "SUCCEEDED")
            self.assertTrue(list(config.checkpoints_dir.glob("*/state.json")))
            replay = execute_run_activity(request)
            self.assertEqual(replay["temporal_outcome"], "idempotent_replay")

    def test_activity_retry_resumes_after_one_shot_simulated_crash(self) -> None:
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            config = MoltConfig(Path(directory))
            service = MoltService(config)
            source = config.input_dir / "golden.csv"
            shutil.copy2(root / "examples/input/golden.csv", source)
            automation = service.create_automation("Temporal crash recovery", "Resume a checked recipe after a worker interruption.")
            version = service.generate_candidate(
                automation["id"],
                "Normalize the fixture",
                service.profile(source),
                recipe_file=str(root / "examples/recipes/expense-v1.json"),
            )
            self.assertEqual(service.verify_version(version["id"])["status"], "PASS")
            service.approve_version(version["id"])
            request = build_run_request(directory, automation["id"], source)
            previous = os.environ.get("MOLT_CRASH_AT")
            os.environ["MOLT_CRASH_AT"] = "1"
            try:
                with self.assertRaises(RuntimeError):
                    execute_run_activity(request)
                checkpoint_states = list(config.checkpoints_dir.glob("*/state.json"))
                self.assertTrue(checkpoint_states)
                self.assertEqual(checkpoint_states[0].read_text(encoding="utf-8").count('"status": "running"'), 1)
                resumed = execute_run_activity(request)
            finally:
                if previous is None:
                    os.environ.pop("MOLT_CRASH_AT", None)
                else:
                    os.environ["MOLT_CRASH_AT"] = previous
            self.assertEqual(resumed["status"], "SUCCEEDED")
            self.assertEqual(resumed["temporal_outcome"], "completed")
            self.assertTrue(resumed["rows_written"] > 0)

    def test_default_workflow_id_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "in.csv"
            self.assertEqual(
                default_workflow_id(directory, "auto_123", input_path),
                default_workflow_id(directory, "auto_123", input_path),
            )


if __name__ == "__main__":
    unittest.main()
