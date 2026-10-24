from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import shutil
import os

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import MoltError
from molt.temporal import (
    build_run_request,
    default_workflow_id,
    execute_run_activity,
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
