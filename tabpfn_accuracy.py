"""Re-run the existing synthetic supervised fixture; export aggregates only.

Run with the existing TABPFN_TOKEN environment variable from a directory without
a .env file (TabPFN itself auto-loads .env). No credentials are read by this script.
Example: python D:\\week3\\tabpfn_accuracy.py
The package/model/device match evidence/tabpfn-live.json; no model override.
"""
from __future__ import annotations

import contextlib
import csv
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from molt.anomaly import AnomalyAnalyzer
from molt.config import MoltConfig


ROOT = Path(__file__).resolve().parent
FEATURES = [
    "row_count", "null_fraction", "unseen_category_fraction",
    "date_parse_fail_fraction", "decimal_parse_fail_fraction", "column_count_delta",
    "duplicate_fraction", "header_similarity",
]


def fingerprint(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def aggregate_result(result: dict[str, Any]) -> dict[str, Any]:
    # An allowlist keeps row payloads, scores, and arbitrary failure text out.
    keys = (
        "status", "code", "eligible", "error_type", "advisory_only", "rows_changed",
        "split", "threshold", "rows_scored", "rows_flagged", "holdout_metrics",
    )
    return {key: result[key] for key in keys if key in result}


def main() -> int:
    source = ROOT / "molt_drift_features.csv"
    output = ROOT / "evidence" / "tabpfn-accuracy.json"
    started = time.perf_counter()
    config = MoltConfig(
        workspace=ROOT,
        sentry_dsn="",
        local_only=True,
        tabpfn_enabled=True,
        tabpfn_license_accepted=True,  # Already acknowledged for this same model.
        tabpfn_model="default",
        tabpfn_device="cpu",
        tabpfn_max_rows=5_000,
    )
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["TABPFN_ALLOW_CPU_LARGE_DATASET"] = "1"
    evidence: dict[str, Any] = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "FAILED",
        "dataset": {
            "file": source.name,
            "synthetic": True,
            "description": "Existing rule-generated fixture with overlapping distributions and noisy labels; not regenerated.",
        },
        "advisory_only": True,
        "task": "supervised_binary_classification",
        "target": {"column": "is_drift", "anomaly_label": "1"},
        "features": FEATURES,
        "requested_test_fraction": 0.2,
        "threshold": 0.5,
        "config": {
            "model": config.tabpfn_model, "device": config.tabpfn_device,
            "license": "previously acknowledged for the same model",
            "telemetry_enabled": False, "local_only": config.local_only,
        },
        "runtime": {"python": platform.python_version()},
        "privacy": "Aggregate-only export: no CSV row values, row numbers, per-row labels/probabilities, credentials, or exception messages.",
        "limitation": "Synthetic supervised holdout evaluation against supplied labels; advisory only, not unlabeled anomaly detection or real-world drift validation.",
    }
    before: str | None = None
    try:
        before = fingerprint(source)
        evidence["dataset"]["sha256_before"] = before
        with source.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FEATURES + ["is_drift"]:
                raise ValueError("Unexpected fixture schema")
            labels = [row["is_drift"] for row in reader]
        evidence["dataset"].update({
            "rows": len(labels),
            "positive_labels": labels.count("1"),
            "negative_labels": labels.count("0"),
        })
        if len(labels) != 1500 or set(labels) != {"0", "1"}:
            raise ValueError("Unexpected fixture size or labels")
        prior = json.loads((ROOT / "evidence" / "tabpfn-live.json").read_text(encoding="utf-8"))
        version = importlib.metadata.version("tabpfn")
        evidence["runtime"]["tabpfn"] = version
        if (version != prior["readiness"]["package"]["version"]
                or config.tabpfn_model != prior["readiness"]["config"]["model"]
                or config.tabpfn_device != prior["readiness"]["config"]["device"]
                or FEATURES != prior["features"]):
            raise ValueError("Prior package/model/device/features do not match")
        # Optional-package diagnostics can contain raw data or credential-bearing
        # URLs. Keep them out of both console output and saved evidence.
        with open(os.devnull, "w", encoding="utf-8") as sink:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                analyzer = AnomalyAnalyzer(
                    enabled=config.tabpfn_enabled,
                    license_accepted=config.tabpfn_license_accepted,
                    model=config.tabpfn_model, device=config.tabpfn_device,
                    max_rows=config.tabpfn_max_rows,
                )
                result = analyzer.analyze(
                    source, label_column="is_drift", anomaly_label="1",
                    feature_columns=FEATURES, test_fraction=0.2,
                )
        evidence.update(aggregate_result(result))
    except (Exception, KeyboardInterrupt) as exc:
        evidence.update({"status": "FAILED", "error_type": type(exc).__name__})
    finally:
        try:
            after = fingerprint(source)
            evidence["dataset"]["sha256_after"] = after
            evidence["source_preserved"] = before is not None and before == after
        except OSError as exc:
            evidence["source_preserved"] = False
            evidence["fingerprint_error_type"] = type(exc).__name__
        if not evidence["source_preserved"]:
            evidence["status"] = "FAILED"
        evidence["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        output.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, allow_nan=False))
    return 0 if evidence["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
