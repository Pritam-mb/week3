from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import MoltError, load_json


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


class VerifierRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.service = MoltService(MoltConfig(self.workspace))
        self.recipe = load_json(EXAMPLES / "recipes/expense-v1.json")

    def verify(self, recipe, fixtures=None):
        automation = self.service.create_automation("Verifier regression")
        version = self.service.create_version(automation["id"], recipe)
        report = self.service.verify_version(version["id"], fixtures=fixtures)
        saved = self.service.get_version(version["id"])
        self.assertEqual(saved["verification"]["status"], report["status"])
        self.assertEqual(saved["status"], "AWAITING_APPROVAL" if report["status"] == "PASS" else "REJECTED")
        if report["status"] == "FAIL":
            with self.assertRaises(MoltError) as error:
                self.service.approve_version(version["id"])
            self.assertEqual(error.exception.code, "APPROVAL_REQUIRED")
        return report

    def test_default_production_fixtures_pass_correct_recipe(self) -> None:
        report = self.verify(self.recipe)
        self.assertEqual(report["status"], "PASS", report)
        checks = {(item["fixture"], item["check"]) for item in report["results"]}
        self.assertIn(("dedupe-key.csv", "golden_output"), checks)
        self.assertIn(("drift-unmapped-category.csv", "expected_error"), checks)

    def test_dedupe_key_mutant_passes_old_fixtures_but_fails_production(self) -> None:
        self.recipe["operations"][4]["key_columns"] = ["merchant"]
        old = [(EXAMPLES / f"input/{name}.csv", EXAMPLES / f"expected/{name}.csv") for name in ("golden", "heldout")]
        self.assertEqual(self.verify(self.recipe, old)["status"], "PASS")
        report = self.verify(self.recipe)
        failures = [item for item in report["results"] if item["status"] == "FAIL"]
        self.assertEqual([(item["fixture"], item["check"]) for item in failures], [("dedupe-key.csv", "golden_output")])
        self.assertEqual(failures[0]["structure"]["actual_rows"], 1)
        self.assertEqual(failures[0]["structure"]["expected_rows"], 2)

    def test_preserve_unknown_mutant_fails_negative_fixture_only(self) -> None:
        self.recipe["operations"][3]["on_unmapped"] = "preserve"
        old = [(EXAMPLES / f"input/{name}.csv", EXAMPLES / f"expected/{name}.csv") for name in ("golden", "heldout")]
        self.assertEqual(self.verify(self.recipe, old)["status"], "PASS")
        report = self.verify(self.recipe)
        failures = [item for item in report["results"] if item["status"] == "FAIL"]
        self.assertEqual([(item["fixture"], item["check"]) for item in failures], [("drift-unmapped-category.csv", "expected_error")])
        self.assertEqual(failures[0]["expected_error"], "UNMAPPED_VALUE")
        self.assertIsNone(failures[0]["actual_error"])

    def test_preserve_remains_valid_with_task_specific_stored_oracle(self) -> None:
        self.recipe["operations"][3]["on_unmapped"] = "preserve"
        source = self.workspace / "unknown.csv"
        expected = self.workspace / "expected.csv"
        shutil.copy2(EXAMPLES / "input/drift-unmapped-category.csv", source)
        expected.write_text(
            "transaction_id,date,merchant,amount,category,notes\n"
            "t-902,2026-10-21,Store,10.00,pet supplies,unknown category\n",
            encoding="utf-8",
        )
        automation = self.service.create_automation("Preserve unknown categories")
        self.service.add_fixture(automation["id"], source, expected, name="preserve oracle")
        version = self.service.create_version(automation["id"], self.recipe)
        self.assertEqual(self.service.verify_version(version["id"])["status"], "PASS")
        self.assertEqual(self.service.approve_version(version["id"])["status"], "ACTIVE")

    def test_expected_error_requires_exact_code(self) -> None:
        self.recipe["operations"][1]["input_formats"] = ["%Y-%m-%d"]
        report = self.verify(self.recipe, [(
            EXAMPLES / "input/drift-unmapped-category.csv",
            EXAMPLES / "expected/drift-unmapped-category.error.json",
        )])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["results"][0]["check"], "expected_error")
        self.assertEqual(report["results"][0]["actual_error"], "INPUT_TYPE_MISMATCH")

    def test_negative_first_does_not_supply_positive_invariant_input(self) -> None:
        automation = self.service.create_automation("Negative first")
        fixtures = self.service._fixture_pairs(automation["id"], recipe=self.recipe)
        report = self.verify(self.recipe, fixtures[-1:] + fixtures[:-1])
        self.assertEqual(report["status"], "PASS", report)
        self.assertTrue(all(item["check"] == "expected_error" for item in report["results"] if item["fixture"] == "drift-unmapped-category.csv"))

    def test_negative_only_stored_fixture_uses_production_path(self) -> None:
        automation = self.service.create_automation("Expected error")
        source = self.workspace / "unknown.csv"
        oracle = self.workspace / "unknown.error.json"
        shutil.copy2(EXAMPLES / "input/drift-unmapped-category.csv", source)
        shutil.copy2(EXAMPLES / "expected/drift-unmapped-category.error.json", oracle)
        self.service.add_fixture(automation["id"], source, oracle, name="unknown is rejected")
        version = self.service.create_version(automation["id"], self.recipe)
        report = self.service.verify_version(version["id"])
        self.assertEqual(report["status"], "PASS", report)
        self.assertEqual(report["checks_total"], 1)

    def test_fixture_loading_error_is_not_expected_execution_error(self) -> None:
        oracle = self.workspace / "missing.error.json"
        oracle.write_text(json.dumps({"error_code": "INPUT_TYPE_MISMATCH"}), encoding="utf-8")
        report = self.verify(self.recipe, [(self.workspace / "missing.csv", oracle)])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["results"][0]["check"], "INPUT_TYPE_MISMATCH")

    def test_invalid_expected_error_oracle_fails(self) -> None:
        oracle = self.workspace / "invalid.error.json"
        oracle.write_text('{"error_code": ""}', encoding="utf-8")
        report = self.verify(self.recipe, [(EXAMPLES / "input/drift-unmapped-category.csv", oracle)])
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["results"][0]["check"], "INVALID_FIXTURE")


if __name__ == "__main__":
    unittest.main()
