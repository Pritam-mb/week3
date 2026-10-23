"""Recovered 20-mutation experiment; run: python verifier_measurement.py.

The historical inline runner was not checked in. Its exact mutations were
recovered from the session command transcript and expressed as JSON patches.
Both fixture sets run on today's production service/verifier. No historical
outcome, desired catch rate, or candidate-generated output is used as an oracle.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from collections import Counter
from pathlib import Path

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import MoltError, canonical_csv, execute_recipe, load_json, read_csv


ROOT = Path(__file__).resolve().parent
ORIGINAL = ROOT / "evidence/verifier-catch-rate.json"
RECIPE = ROOT / "examples/recipes/expense-v1.json"
DEFAULT_OUTPUT = ROOT / "evidence/verifier-catch-rate-after.json"


def mutations(recipe):
    """Return exact, independently applied JSON patches in historical order."""
    columns = recipe["input_contract"]["required_columns"]
    mapping = recipe["operations"][3]["mapping"]
    assert [op["type"] for op in recipe["operations"]] == [
        "trim", "coerce_date", "parse_decimal", "map_values", "dedupe",
    ], "Revisit reconstruction if the base recipe changes."

    def replace(path, value):
        return {"op": "replace", "path": path, "value": value}

    def append(operation):
        return {"op": "add", "path": "/operations/-", "value": operation}

    return [
        ("extra_category_casing", [{"op": "add", "path": "/operations/1", "value": {"type": "normalize_case", "columns": ["category"], "mode": "upper"}}]),
        ("wrong_date_output_format", [replace("/operations/1/output_format", "%d-%m-%Y")]),
        ("missing_map_identity_with_keep_known_disabled", [
            {"op": "remove", "path": "/operations/3/mapping/Food"},
            {"op": "add", "path": "/operations/3/keep_known", "value": False},
        ]),
        ("dedupe_wrong_column", [replace("/operations/4/key_columns", ["merchant"])]),
        ("drop_required_output", [
            {"op": "add", "path": "/operations/0", "value": {"type": "select_columns", "columns": list(columns)}},
        ]),
        ("wrong_output_column_order", [append({"type": "reorder_columns", "columns": ["category", "transaction_id", "date", "merchant", "amount"], "preserve_extra_columns": True})]),
        ("wrong_decimal_places", [replace("/operations/2/decimal_places", 0)]),
        ("remove_trim", [replace("/operations/0", {"type": "trim", "columns": ["category"]})]),
        ("wrong_category_mapping", [replace("/operations/3/mapping/books", "Food")]),
        ("merchant_uppercase", [{"op": "add", "path": "/operations/1", "value": {"type": "normalize_case", "columns": ["merchant"], "mode": "upper"}}]),
        ("filter_rows", [{"op": "add", "path": "/operations/0", "value": {"type": "filter_rows", "condition": {"column": "category", "operator": "neq", "value": "books"}, "on_no_match": "keep_empty"}}]),
        ("wrong_date_input_formats", [replace("/operations/1/input_formats", ["%d/%m/%Y"])]),
        ("wrong_decimal_separator", [replace("/operations/2/decimal_separator", ",")]),
        ("rename_column", [{"op": "add", "path": "/operations/0", "value": {"type": "rename_column", "source": "merchant", "destination": "vendor"}}]),
        ("dedupe_keep_last", [replace("/operations/4/keep", "last")]),
        ("preserve_unknown_policy", [replace("/operations/3/on_unmapped", "preserve")]),
        ("extra_fill_null", [append({"type": "fill_null", "columns": ["notes"], "value": "unknown"})]),
        ("drop_dedupe", [replace("/operations/4", {"type": "trim", "columns": ["notes"]})]),
        ("date_as_decimal", [replace("/operations/2/column", "date")]),
        ("category_to_upper", [
            {"op": "add", "path": "/operations/1", "value": {"type": "normalize_case", "columns": ["category"], "mode": "upper"}},
            {"op": "add", "path": "/operations/3/mapping", "value": {"FOOD & DRINK": "Food", "TRANSIT": "Transport", "BOOKS": "Books"}},
            {"op": "add", "path": "/operations/3/keep_known", "value": True},
        ]),
    ]


def apply_mutation(recipe, edits):
    candidate = copy.deepcopy(recipe)
    for edit in edits:
        parts = [part.replace("~1", "/").replace("~0", "~") for part in edit["path"].split("/")[1:]]
        parent = candidate
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        key = parts[-1]
        if isinstance(parent, list):
            index = len(parent) if key == "-" else int(key)
            if edit["op"] == "add":
                parent.insert(index, copy.deepcopy(edit["value"]))
            elif edit["op"] == "remove":
                del parent[index]
            else:
                parent[index] = copy.deepcopy(edit["value"])
        elif edit["op"] == "remove":
            del parent[key]
        else:
            if edit["op"] == "replace":
                assert key in parent, edit
            parent[key] = copy.deepcopy(edit["value"])
    return candidate


def summarize_verification(report):
    failures = [{key: value for key, value in item.items() if key in {
        "fixture", "check", "structure", "expected_error", "actual_error",
    }} for item in report["results"] if item["status"] == "FAIL"]
    checks = sorted({item["check"] for item in failures})
    return {
        "verification_status": report["status"],
        "caught": report["status"] == "FAIL",
        "rejection_stage": "runtime_recipe_schema" if "RECIPE_SCHEMA_INVALID" in checks else "fixture_verification" if failures else "none",
        "checks_total": report["checks_total"],
        "checks_failed": report["checks_failed"],
        "failure_checks": checks,
        "failures": failures,
    }


def observe(recipe, fixtures):
    """Finite-workload comparison only; never used to author expected outputs."""
    observations = []
    for source, _ in fixtures:
        headers, rows = read_csv(source)
        try:
            actual_headers, actual_rows = execute_recipe(recipe, headers, rows)
            observations.append(("output", canonical_csv(actual_headers, actual_rows)))
            # Include the verifier's second application in the observed workload.
            second_headers, second_rows = execute_recipe(recipe, actual_headers, actual_rows)
            observations.append(("second_output", canonical_csv(second_headers, second_rows)))
        except MoltError as error:
            observations.append(("error", error.code, error.details))
    return observations


def summary(results, field):
    outcomes = [item[field] for item in results]
    caught = sum(item["caught"] for item in outcomes)
    stages = Counter(item["rejection_stage"] for item in outcomes)
    return {
        "total": len(results), "caught": caught, "missed": len(results) - caught,
        "catch_rate": caught / len(results),
        "fixture_verification_failures": stages["fixture_verification"],
        "schema_rejections_before_fixtures": stages["schema_before_fixtures"],
        "runtime_recipe_schema_rejections": stages["runtime_recipe_schema"],
        "misses": [item["name"] for item in results if not item[field]["caught"]],
        "no_observed_effect": [item["name"] for item in results if item["no_observed_effect"][field]],
    }


def measure():
    original = load_json(ORIGINAL)
    recipe = load_json(RECIPE)
    manifest = mutations(recipe)
    assert [name for name, _ in manifest] == [item["name"] for item in original["results"]]
    old_fixtures = [(ROOT / f"examples/input/{name}.csv", ROOT / f"examples/expected/{name}.csv") for name in ("golden", "heldout")]
    with tempfile.TemporaryDirectory(prefix="molt-verifier-") as directory:
        service = MoltService(MoltConfig(Path(directory)))
        automation = service.create_automation("Verifier measurement")
        fixtures = service._fixture_pairs(automation["id"], recipe=recipe)
        control = service.create_version(automation["id"], recipe)
        before_control = summarize_verification(service.verify_version(control["id"], fixtures=old_fixtures))
        after_control = summarize_verification(service.verify_version(control["id"]))
        if before_control["caught"] or after_control["caught"]:
            raise RuntimeError("Correct recipe must pass both fixture sets before measuring mutants.")
        old_observations, observations = observe(recipe, old_fixtures), observe(recipe, fixtures)
        results = []
        for (name, edits), historical in zip(manifest, original["results"]):
            candidate = apply_mutation(recipe, edits)
            entry = {"name": name, "category": historical["category"], "edits": edits, "historical_result": historical}
            try:
                version = service.create_version(automation["id"], candidate)
            except MoltError as error:
                if error.code not in {"RECIPE_SCHEMA_INVALID", "UNSUPPORTED_OPERATION"}:
                    raise
                rejected = {
                    "verification_status": "REJECTED_BEFORE_FIXTURES", "caught": True,
                    "rejection_stage": "schema_before_fixtures", "failure_checks": [error.code],
                    "checks_total": 0, "checks_failed": 0, "failures": [],
                }
                entry.update(before=copy.deepcopy(rejected), after=copy.deepcopy(rejected))
                entry["no_observed_effect"] = {"before": None, "after": None}
            else:
                entry["before"] = summarize_verification(service.verify_version(version["id"], fixtures=old_fixtures))
                entry["after"] = summarize_verification(service.verify_version(version["id"]))
                entry["no_observed_effect"] = {
                    "before": observe(candidate, old_fixtures) == old_observations,
                    "after": observe(candidate, fixtures) == observations,
                }
            entry["historical_outcome_reproduced"] = all(
                entry["before"][key] == historical[key]
                for key in ("verification_status", "failure_checks", "caught")
            )
            results.append(entry)

    paths = [ORIGINAL, RECIPE, Path(__file__).resolve(), ROOT / "molt/core.py", ROOT / "molt/application.py"]
    paths.extend(path for pair in fixtures for path in pair)
    return {
        "schema_version": 1,
        "reproduction_command": "python verifier_measurement.py",
        "provenance": {
            "reconstructed": False,
            "original_runner_found": False,
            "source": "Historical inline command in the session transcript, evidence/verifier-catch-rate.json and examples/recipes/expense-v1.json",
            "disclosure": "The original runner was inline, not a repository file. Exact edits recovered from the session transcript are listed below. Before outcomes are checked against the saved historical report.",
            "choices": [
                "drop_required_output actually selects all five declared columns and drops extra notes; its historical name is imprecise.",
                "rename_column inserts before trim and leaves later references unchanged; schema validation rejects it.",
                "extra_fill_null and drop_dedupe refer to undeclared notes and are schema-rejected, not semantic fixture catches.",
                "category_to_upper retains the historical index bug: after insertion, mapping/keep_known attach to parse_decimal and are schema-rejected.",
                "wrong_decimal_separator changes only decimal_separator to comma, colliding with thousands_separator; this is a runtime recipe-schema rejection, not a semantic fixture catch.",
            ],
            "historical_outcome_mismatches": [item["name"] for item in results if not item["historical_outcome_reproduced"]],
        },
        "method": "Each patch starts from a deep copy of the base recipe. MoltService.create_version and verify_version run both sets. After uses production default fixture discovery. Expected CSVs/error codes are independently authored and never generated from a candidate. No model calls.",
        "comparison_scope": "Before reruns the transcript-recovered mutations on golden + heldout with current code; the historical 18/20 file is preserved. After adds dedupe-key and unknown-category expected-error fixtures.",
        "no_op_scope": "no_observed_effect compares first/second execution outputs and error codes/context on the finite fixture workload. It is not proof of global equivalence and is not counted as a caught mutation. Null means schema prevented execution.",
        "counting": "caught includes fixture-verification failures and separately enumerated schema rejections. All 20 remain in the denominator, including workload no-ops; fixture failures are not presented as 20 semantic defect catches.",
        "source_sha256": {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in dict.fromkeys(paths)},
        "fixtures": [{"input": source.relative_to(ROOT).as_posix(), "expected": expected.relative_to(ROOT).as_posix(), "oracle": "expected_error" if expected.name.endswith(".error.json") else "golden_csv"} for source, expected in fixtures],
        "correct_recipe": {"before": before_control, "after": after_control},
        "historical_summary": original["summary"],
        "before_summary": summary(results, "before"),
        "after_summary": summary(results, "after"),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Compare with the saved report without writing it.")
    args = parser.parse_args()
    if args.output.resolve() == ORIGINAL.resolve():
        parser.error("The historical evidence must not be overwritten.")
    report = measure()
    if args.check:
        if load_json(args.output) != report:
            parser.exit(1, "Saved evidence differs from this rerun.\n")
    else:
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"before": report["before_summary"], "after": report["after_summary"]}, indent=2))


if __name__ == "__main__":
    main()
