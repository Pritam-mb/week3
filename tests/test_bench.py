from __future__ import annotations

import unittest
from pathlib import Path

from bench import build_drift_cases, measure_molt_drift_cases, run_naive_positional_baseline
from molt.core import load_json


class TierA4BenchmarkTests(unittest.TestCase):
    def test_fixed_seed_builds_repeatable_drift_cases(self) -> None:
        first = build_drift_cases(41)
        second = build_drift_cases(41)

        self.assertEqual(first, second)
        self.assertEqual([case.name for case in first], [
            "renamed_customer_column",
            "dropped_status_column",
            "reordered_columns",
            "extra_column",
        ])
        self.assertNotEqual(first, build_drift_cases(42))

    def test_naive_positional_baseline_records_silent_wrong_outputs(self) -> None:
        report = run_naive_positional_baseline(41)
        by_name = {case["name"]: case for case in report["cases"]}

        self.assertEqual(report["seed"], 41)
        self.assertEqual(report["case_count"], 4)
        self.assertEqual(report["silent_wrong_outputs"], 3)
        self.assertEqual(report["drift_cases_accepted_without_validation"], 2)
        self.assertTrue(by_name["renamed_customer_column"]["accepted_drift"])
        self.assertTrue(by_name["dropped_status_column"]["silent_wrong_output"])
        self.assertTrue(by_name["reordered_columns"]["silent_wrong_output"])
        self.assertTrue(by_name["extra_column"]["silent_wrong_output"])
        self.assertIsNone(report["cost"]["amount_usd"])

    def test_molt_measurement_counts_actual_blocks_and_quarantines(self) -> None:
        recipe = load_json(Path("examples/recipes/orders-v1.json"))
        report = measure_molt_drift_cases(recipe, 41)

        self.assertEqual(report["status"], "MEASURED")
        self.assertEqual(report["blocked_count"], 2)
        self.assertEqual(report["quarantined_count"], 2)
        self.assertEqual(report["succeeded_count"], 2)
        self.assertEqual(
            [case["status"] for case in report["cases"]],
            ["BLOCKED_DRIFT", "BLOCKED_DRIFT", "SUCCEEDED", "SUCCEEDED"],
        )


if __name__ == "__main__":
    unittest.main()
