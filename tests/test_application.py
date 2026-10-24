from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import load_json, MoltError


ROOT = Path(__file__).resolve().parents[1]


class ApplicationFlowTests(unittest.TestCase):
    def test_orders_workflow_recipe_supports_rename_and_ordered_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            source = Path(directory) / "orders.csv"
            shutil.copy2(ROOT / "examples/orders_input.csv", source)
            automation = service.create_automation("Orders", "Normalize order exports")
            version = service.generate_candidate(automation["id"], "Normalize orders", service.profile(source), recipe_file=str(ROOT / "examples/recipes/orders-v1.json"))
            result = service.verify_version(version["id"])
            self.assertEqual(result["status"], "PASS", result)
            service.approve_version(version["id"])
            run = service.run(automation["id"], source)
            self.assertEqual(run["status"], "SUCCEEDED")

    def test_repair_regression_and_approval_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            source = Path(directory) / "orders.csv"
            drift = Path(directory) / "orders-drift.csv"
            shutil.copy2(ROOT / "examples/orders_input.csv", source)
            shutil.copy2(ROOT / "examples/orders_drift_unknown_status.csv", drift)
            automation = service.create_automation("Orders repair", "Repair order statuses")
            version = service.generate_candidate(automation["id"], "Normalize orders", service.profile(source), recipe_file=str(ROOT / "examples/recipes/orders-v1.json"))
            self.assertEqual(service.verify_version(version["id"])["status"], "PASS")
            service.approve_version(version["id"])
            blocked = service.run(automation["id"], drift)
            self.assertEqual(blocked["status"], "BLOCKED_DRIFT")
            bad = service.propose_repair(automation["id"], blocked["id"], recipe_file=str(ROOT / "examples/recipes/orders-bad-repair.json"))
            bad_result = service.verify_repair(bad["id"])
            self.assertEqual(bad_result["status"], "REJECTED")
            with self.assertRaises(MoltError):
                service.approve_repair(bad["id"])
            good = service.propose_repair(automation["id"], blocked["id"], recipe_file=str(ROOT / "examples/recipes/orders-good-repair.json"))
            good_result = service.verify_repair(good["id"])
            self.assertEqual(good_result["status"], "VERIFIED")
            active = service.approve_repair(good["id"])
            self.assertEqual(active["status"], "APPROVED")

    def test_mastra_repair_sidecar_returns_candidate_without_bypassing_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory), mastra_repair_url="http://mastra.test"))
            source = Path(directory) / "orders.csv"
            drift = Path(directory) / "orders-drift.csv"
            shutil.copy2(ROOT / "examples/orders_input.csv", source)
            shutil.copy2(ROOT / "examples/orders_drift_unknown_status.csv", drift)
            automation = service.create_automation("Orders Mastra", "Repair order statuses")
            version = service.generate_candidate(automation["id"], "Normalize orders", service.profile(source), recipe_file=str(ROOT / "examples/recipes/orders-v1.json"))
            self.assertEqual(service.verify_version(version["id"])["status"], "PASS")
            service.approve_version(version["id"])
            blocked = service.run(automation["id"], drift)
            good_recipe = load_json(ROOT / "examples/recipes/orders-good-repair.json")

            class FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    return False

                def read(self, _limit):
                    return json.dumps({"status": "PROPOSED", "recipe": good_recipe, "reason": "Add the observed status mapping", "model": "mastra/test", "trace_id": "trace-test"}).encode()

            with patch("molt.application.urlopen", return_value=FakeResponse()):
                proposal = service.propose_repair(automation["id"], blocked["id"], model="mastra/test")

            self.assertEqual(proposal["status"], "PROPOSED")
            self.assertEqual(proposal["candidate"]["provider_metadata"]["provider"], "mastra")
            self.assertEqual(service.verify_repair(proposal["id"])["status"], "VERIFIED")

    def test_sqlite_lifecycle_run_drift_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = MoltConfig(Path(directory))
            service = MoltService(config)
            input_path = config.input_dir / "expense.csv"
            shutil.copy2(ROOT / "examples/input/golden.csv", input_path)
            automation = service.create_automation("Expenses", "Normalize exports")
            recipe = load_json(ROOT / "examples/recipes/expense-v1.json")
            profile = service.profile(input_path)
            version = service.generate_candidate(automation["id"], "Normalize", profile, recipe_file=str(ROOT / "examples/recipes/expense-v1.json"))
            verification = service.verify_version(version["id"])
            self.assertEqual(verification["status"], "PASS")
            active = service.approve_version(version["id"])
            self.assertEqual(active["status"], "ACTIVE")
            result = service.run(automation["id"], input_path)
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertEqual(result["llm_calls"], 0)
            self.assertEqual(service.metrics()["successful_runs"], 1)

            drift = config.input_dir / "drift.csv"
            shutil.copy2(ROOT / "examples/input/drift-missing-column.csv", drift)
            blocked = service.run(automation["id"], drift)
            self.assertEqual(blocked["status"], "BLOCKED_DRIFT")
            self.assertTrue(list(config.quarantine_dir.glob("drift-*")))

    def test_stale_or_missing_approval_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            automation = service.create_automation("Unapproved", "")
            recipe = load_json(ROOT / "examples/recipes/expense-v1.json")
            version = service.create_version(automation["id"], recipe)
            with self.assertRaises(MoltError) as context:
                service.approve_version(version["id"])
            self.assertEqual(context.exception.code, "APPROVAL_REQUIRED")


if __name__ == "__main__":
    unittest.main()
