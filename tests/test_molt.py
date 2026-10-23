from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from molt.core import MoltError, execute_recipe, execute_recipe_resumable, load_json, read_csv, validate_recipe, verify_recipe
from molt.privacy import safe_verification_feedback


ROOT = Path(__file__).resolve().parents[1]
RECIPE = load_json(ROOT / "examples" / "recipes" / "expense-v1.json")


class MoltCoreTests(unittest.TestCase):
    def test_independent_fixtures_and_idempotence_pass(self) -> None:
        result = verify_recipe(RECIPE, [
            (ROOT / "examples/input/golden.csv", ROOT / "examples/expected/golden.csv"),
            (ROOT / "examples/input/heldout.csv", ROOT / "examples/expected/heldout.csv"),
        ])
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["checks_failed"], 0)

    def test_missing_required_column_fails_closed(self) -> None:
        headers, rows = read_csv(ROOT / "examples/input/drift-missing-column.csv")
        with self.assertRaises(MoltError) as context:
            execute_recipe(RECIPE, headers, rows)
        self.assertEqual(context.exception.code, "REQUIRED_COLUMN_MISSING")

    def test_unknown_category_is_not_silently_preserved(self) -> None:
        headers, rows = read_csv(ROOT / "examples/input/drift-unmapped-category.csv")
        with self.assertRaises(MoltError) as context:
            execute_recipe(RECIPE, headers, rows)
        self.assertEqual(context.exception.code, "UNMAPPED_VALUE")
        self.assertEqual(context.exception.details["column"], "category")
        self.assertEqual(context.exception.details["unmapped_count"], 1)

    def test_map_values_keeps_canonical_values_without_identity_entries(self) -> None:
        recipe = json.loads(json.dumps(RECIPE))
        mapping = recipe["operations"][3]["mapping"]
        for canonical in ("Food", "Transport", "Books"):
            mapping.pop(canonical)
        normalized = validate_recipe(recipe)
        self.assertTrue(normalized["operations"][3]["keep_known"])
        headers, rows = read_csv(ROOT / "examples/input/golden.csv")
        actual_headers, actual_rows = execute_recipe(recipe, headers, rows)
        expected_headers, expected_rows = read_csv(ROOT / "examples/expected/golden.csv")
        self.assertEqual(actual_headers, expected_headers)
        self.assertEqual(actual_rows, expected_rows)

    def test_map_values_can_reject_canonical_values_when_requested(self) -> None:
        recipe = json.loads(json.dumps(RECIPE))
        recipe["operations"][3]["keep_known"] = False
        recipe["operations"][3]["mapping"] = {"food & drink": "Food"}
        headers, rows = read_csv(ROOT / "examples/input/golden.csv")
        with self.assertRaises(MoltError) as context:
            execute_recipe(recipe, headers, rows)
        self.assertEqual(context.exception.code, "UNMAPPED_VALUE")

    def test_safe_unmapped_feedback_contains_structure_not_values(self) -> None:
        feedback = safe_verification_feedback({
            "status": "FAIL",
            "checks_failed": 1,
            "results": [{
                "status": "FAIL",
                "check": "UNMAPPED_VALUE",
                "context": {"column": "category", "unmapped_count": 3, "value": "private merchant"},
            }],
        })
        encoded = json.dumps(feedback)
        self.assertIn("3 row(s)", feedback["failures"][0]["message"])
        self.assertNotIn("private merchant", encoded)
        self.assertNotIn("value", feedback["failures"][0]["context"])

    def test_unknown_operation_is_rejected(self) -> None:
        invalid = json.loads(json.dumps(RECIPE))
        invalid["operations"][0] = {"type": "run_python", "code": "print('unsafe')"}
        with self.assertRaises(MoltError) as context:
            validate_recipe(invalid)
        self.assertEqual(context.exception.code, "UNSUPPORTED_OPERATION")

    def test_unrelated_column_is_preserved_and_column_order_does_not_matter(self) -> None:
        headers, rows = read_csv(ROOT / "examples/input/golden.csv")
        reordered = ["notes", "category", "amount", "merchant", "date", "transaction_id"]
        reordered_rows = [{column: row[column] for column in reordered} for row in rows]
        actual_headers, actual_rows = execute_recipe(RECIPE, reordered, reordered_rows)
        self.assertEqual(actual_headers, reordered)
        self.assertEqual(actual_rows[0]["notes"], "team breakfast")

    def test_checkpoint_resume_starts_after_completed_step(self) -> None:
        headers, rows = read_csv(ROOT / "examples/input/golden.csv")
        with tempfile.TemporaryDirectory() as directory:
            checkpoint_dir = Path(directory)
            with self.assertRaises(RuntimeError):
                execute_recipe_resumable(RECIPE, headers, rows, checkpoint_dir, crash_after=2)
            state = load_json(checkpoint_dir / "state.json")
            self.assertEqual(state["completed_steps"], 2)
            _, resumed_rows, resumed_from = execute_recipe_resumable(RECIPE, headers, rows, checkpoint_dir, resume=True)
            self.assertEqual(resumed_from, 2)
            self.assertEqual(len(resumed_rows), 3)


if __name__ == "__main__":
    unittest.main()
