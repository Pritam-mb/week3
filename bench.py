from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

from molt.core import execute_recipe, load_json, read_csv
from molt.ollama import generate_recipe


ROOT = Path(__file__).resolve().parent


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
    report = {
        "baseline": "one model call per comparable file",
        "comparable_files": len(durations),
        "repeated_llm_baseline": {
            "calls_assumed": len(durations),
            "status": "declared comparison; live model calls require --model",
            "model_calls_made": metadata["generation_calls"] if args.model else 0,
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
        "claim_boundary": "Call avoidance is an inference proxy, not measured electricity savings.",
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
