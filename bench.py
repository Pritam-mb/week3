from __future__ import annotations

import argparse
import csv
import json
import random
import statistics
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import execute_recipe, load_json, read_csv
from molt.ollama import generate_recipe


ROOT = Path(__file__).resolve().parent
DRIFT_SEED = 41


@dataclass(frozen=True)
class DriftCase:
    name: str
    description: str
    headers: tuple[str, ...]
    rows: tuple[dict[str, str], ...]
    expected_headers: tuple[str, ...] | None
    expected_rows: tuple[dict[str, str], ...] | None
    molt_expected_status: str


def _independent_order_oracle(headers: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]] | None:
    """Independently authored ground truth for the benchmark drift fixtures.

    This is intentionally a small reference transformation rather than a call to
    Molt's recipe interpreter.  It describes the intended order export semantics
    by column name so that the positional baseline can be evaluated against an
    oracle that is not derived from the implementation under test.
    """
    customer_column = next((column for column in (" Customer Name ", "Customer Name", "customer_name") if column in headers), None)
    required = {"order_id", "status", "order_date"}
    if customer_column is None or not required <= set(headers):
        return None

    output_headers = ["order_id", "customer_name", "status", "order_date"]
    excluded = {"order_id", customer_column, "status", "order_date"}
    output_headers.extend(column for column in headers if column not in excluded)
    output_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    status_aliases = {"complete": "completed", "completed": "completed", "done": "completed"}
    for source in rows:
        order_id = source.get("order_id", "")
        if order_id in seen:
            continue
        seen.add(order_id)
        raw_date = source.get("order_date", "").strip()
        if "/" in raw_date:
            month, day, year = raw_date.split("/")
            raw_date = f"{year}-{int(month):02d}-{int(day):02d}"
        normalized = {
            "order_id": order_id,
            "customer_name": source.get(customer_column, "").strip(),
            "status": status_aliases.get(source.get("status", "").strip().lower(), source.get("status", "").strip().lower()),
            "order_date": raw_date,
        }
        for column in output_headers[4:]:
            normalized[column] = source.get(column, "")
        output_rows.append(normalized)
    return output_headers, output_rows


def build_drift_cases(seed: int = DRIFT_SEED) -> list[DriftCase]:
    """Build repeatable, named schema-drift cases from the checked-in orders fixture."""
    source_headers, source_rows = read_csv(ROOT / "examples" / "orders_input.csv")
    rng = random.Random(seed)
    seeded_rows = [dict(row) for row in source_rows]
    rng.shuffle(seeded_rows)
    region_values = [f"region-{rng.randrange(100, 1000)}" for _ in seeded_rows]

    renamed_headers = ["order_id", "Customer Name", "status", "order_date", "notes"]
    renamed_rows = [
        {("Customer Name" if column == " Customer Name " else column): value for column, value in row.items()}
        for row in seeded_rows
    ]

    dropped_headers = [column for column in source_headers if column != "status"]
    dropped_rows = [{column: value for column, value in row.items() if column != "status"} for row in seeded_rows]

    reordered_headers = ["status", "order_id", " Customer Name ", "order_date", "notes"]
    reordered_rows = [{column: row[column] for column in reordered_headers} for row in seeded_rows]

    extra_headers = source_headers + ["region"]
    extra_rows = [row | {"region": region} for row, region in zip(seeded_rows, region_values)]

    cases = [
        ("renamed_customer_column", "Customer Name was renamed without an approved recipe change.", renamed_headers, renamed_rows, "BLOCKED_DRIFT"),
        ("dropped_status_column", "The required status column was removed.", dropped_headers, dropped_rows, "BLOCKED_DRIFT"),
        ("reordered_columns", "Required columns were reordered; names still identify them.", reordered_headers, reordered_rows, "SUCCEEDED"),
        ("extra_column", "An unrelated region column was added.", extra_headers, extra_rows, "SUCCEEDED"),
    ]
    drift_cases: list[DriftCase] = []
    for name, description, headers, rows, molt_status in cases:
        oracle = _independent_order_oracle(headers, rows)
        expected_headers, expected_rows = oracle if oracle is not None else (None, None)
        drift_cases.append(
            DriftCase(
                name=name,
                description=description,
                headers=tuple(headers),
                rows=tuple(dict(row) for row in rows),
                expected_headers=tuple(expected_headers) if expected_headers is not None else None,
                expected_rows=tuple(dict(row) for row in expected_rows) if expected_rows is not None else None,
                molt_expected_status=molt_status,
            )
        )
    return drift_cases


def naive_positional_script(headers: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    """A deliberately naive, independently authored positional baseline.

    It assumes the original five-column order, ignores header names, does not
    validate the contract, and pads missing positions.  Those choices model the
    maintenance/safety trade-off of a hand-written script; they are not used by
    Molt's runtime.
    """
    output_headers = ["order_id", "customer_name", "status", "order_date", "notes"]
    output_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in rows:
        values = [source.get(column, "") for column in headers]
        values.extend([""] * (5 - len(values)))
        order_id, customer, status, order_date, notes = values[:5]
        if order_id in seen:
            continue
        seen.add(order_id)
        status_value = status.strip().lower()
        status_value = {"complete": "completed", "completed": "completed", "done": "completed"}.get(status_value, status_value)
        date_value = order_date.strip()
        if "/" in date_value:
            parts = date_value.split("/")
            if len(parts) == 3:
                month, day, year = parts
                date_value = f"{year}-{int(month):02d}-{int(day):02d}"
        output_rows.append({
            "order_id": order_id.strip(),
            "customer_name": customer.strip(),
            "status": status_value,
            "order_date": date_value,
            "notes": notes,
        })
    return output_headers, output_rows


def run_naive_positional_baseline(seed: int = DRIFT_SEED) -> dict[str, Any]:
    cases = build_drift_cases(seed)
    case_reports: list[dict[str, Any]] = []
    silent_wrong_outputs = 0
    accepted_drift = 0
    durations: list[float] = []
    for case in cases:
        started = time.perf_counter()
        try:
            actual_headers, actual_rows = naive_positional_script(list(case.headers), [dict(row) for row in case.rows])
            error = None
        except (IndexError, TypeError, ValueError) as exc:
            actual_headers, actual_rows = [], []
            error = type(exc).__name__
        durations.append((time.perf_counter() - started) * 1000)
        matches_oracle = (
            error is None
            and case.expected_headers is not None
            and tuple(actual_headers) == case.expected_headers
            and tuple(actual_rows) == case.expected_rows
        )
        should_block = case.molt_expected_status == "BLOCKED_DRIFT"
        missed_drift = error is None and should_block
        silent_wrong = error is None and (not matches_oracle if case.expected_rows is not None else should_block)
        silent_wrong_outputs += int(silent_wrong)
        accepted_drift += int(missed_drift)
        case_reports.append({
            "name": case.name,
            "description": case.description,
            "status": "PRODUCED" if error is None else "ERROR",
            "error": error,
            "matches_independent_oracle": matches_oracle,
            "silent_wrong_output": silent_wrong,
            "accepted_drift": missed_drift,
            "expected_molt_status": case.molt_expected_status,
        })
    return {
        "implementation": "independently_authored_naive_positional_script",
        "seed": seed,
        "cases": case_reports,
        "case_count": len(case_reports),
        "silent_wrong_outputs": silent_wrong_outputs,
        "drift_cases_accepted_without_validation": accepted_drift,
        "latency_ms": {"samples": len(durations), "mean": round(statistics.mean(durations), 3)},
        "cost": {
            "status": "not_estimated",
            "amount_usd": None,
            "reason": "The benchmark has no defensible script-maintenance or provider price estimate; it reports behavior and measured latency only.",
        },
    }


def _write_case(path: Path, headers: tuple[str, ...], rows: tuple[dict[str, str], ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def measure_molt_drift_cases(recipe: dict[str, Any], seed: int = DRIFT_SEED) -> dict[str, Any]:
    """Run the same fixed cases through Molt to count actual blocks/quarantines."""
    cases = build_drift_cases(seed)
    with tempfile.TemporaryDirectory(prefix="molt-a4-") as directory:
        config = MoltConfig(Path(directory))
        service = MoltService(config)
        automation = service.create_automation("Tier A4 orders", "Fixed-seed positional baseline comparison")
        version = service.create_version(automation["id"], recipe, metadata={"provider": "fixture", "llm_calls": 0})
        verification = service.verify_version(version["id"], fixtures=[(ROOT / "examples" / "orders_input.csv", ROOT / "examples" / "orders_expected.csv")])
        if verification["status"] != "PASS":
            return {"status": "UNAVAILABLE", "reason": "The selected recipe did not pass the benchmark fixture.", "verification": verification}
        service.approve_version(version["id"])
        results: list[dict[str, Any]] = []
        for case in cases:
            input_path = config.input_dir / f"{case.name}.csv"
            _write_case(input_path, case.headers, case.rows)
            result = service.run(automation["id"], input_path, baseline_calls=1)
            matches_oracle = False
            if result["status"] == "SUCCEEDED" and result.get("output"):
                actual_headers, actual_rows = read_csv(Path(result["output"]))
                matches_oracle = (
                    case.expected_headers is not None
                    and tuple(actual_headers) == case.expected_headers
                    and tuple(actual_rows) == case.expected_rows
                )
            results.append({"name": case.name, "status": result["status"], "error_code": result.get("error_code"), "matches_independent_oracle": matches_oracle if result["status"] == "SUCCEEDED" else None})
        quarantine_count = len(list(config.quarantine_dir.glob("*.csv")))
    blocked_count = sum(result["status"] == "BLOCKED_DRIFT" for result in results)
    return {
        "status": "MEASURED",
        "seed": seed,
        "cases": results,
        "blocked_count": blocked_count,
        "quarantined_count": quarantine_count,
        "succeeded_count": sum(result["status"] == "SUCCEEDED" for result in results),
        "successful_output_oracle_matches": sum(result.get("matches_independent_oracle") is True for result in results),
        "successful_output_oracle_mismatches": sum(result.get("matches_independent_oracle") is False for result in results),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure Molt deterministic reuse against a declared repeated-call baseline.")
    parser.add_argument("--model", help="Optional Ollama model to compile the recipe live")
    args = parser.parse_args()
    recipe = load_json(ROOT / "examples/recipes/orders-v1.json")
    metadata = {"mode": "offline_fixture", "generation_calls": 0, "model": None}
    if args.model:
        profile = {"columns": read_csv(ROOT / "examples/orders_input.csv")[0]}
        recipe, live_metadata = generate_recipe(args.model, "Normalize the synthetic expense export", profile)
        metadata = {"mode": "ollama", "generation_calls": live_metadata["llm_calls"], "model": args.model}

    durations = []
    for name in ("orders_input", "orders_compatible_2"):
        headers, rows = read_csv(ROOT / "examples" / f"{name}.csv")
        started = time.perf_counter()
        execute_recipe(recipe, headers, rows)
        durations.append((time.perf_counter() - started) * 1000)
    naive_baseline = run_naive_positional_baseline()
    molt_drift = measure_molt_drift_cases(recipe)
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "baseline": "one model call per comparable file",
        "comparable_files": len(durations),
        "repeated_llm_baseline": {
            "calls_assumed": len(durations),
            "status": "declared comparison; live model calls require --model",
            "model_calls_made": metadata["generation_calls"] if args.model else 0,
            "cost": {
                "status": "not_estimated",
                "amount_usd": None,
                "reason": "No provider price was supplied; offline fixture mode makes no live model call and live token pricing is not inferred.",
            },
        },
        "fixed_script_baseline": {
            "status": "not used as the primary claim",
            "note": "A manually maintained script is a deterministic engineering comparison, not the repeated-inference comparison.",
        },
        "baseline_calls": len(durations),
        "deterministic_execution_calls": 0,
        "steady_state_calls_avoided": len(durations),
        "generation": metadata,
        "deterministic_latency_ms": {"samples": len(durations), "mean": round(statistics.mean(durations), 3)},
        "naive_positional_script_baseline": naive_baseline,
        "molt_drift_measurement": molt_drift,
        "cost_reporting": {
            "status": "not_estimated",
            "currency": "USD",
            "estimated_total_usd": None,
            "reason": "No defensible provider or script-maintenance price was configured. Call counts and measured latency are reported without converting them to money or energy savings.",
        },
        "claim_boundary": "Call avoidance is an inference proxy, not measured electricity savings.",
    }
    (ROOT / "evidence" / "benchmark.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
