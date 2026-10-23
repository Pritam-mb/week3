"""Bounded follow-up, not a replacement for the historical ladder.

Run sequentially: python gemma_full_task_rerun.py --trial 1 (through 5).
Each trial has three <=120s generation requests and a 390s process deadline.
No candidate is approved by this measurement. No secrets/.env are loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import MoltError, profile_csv
from molt.ollama import COMPILER_INSTRUCTION, generate_recipe

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "evidence/gemma-full-task-followup.json"
TASK = (
    "Normalize the expense export: trim merchant and category whitespace, normalize dates "
    "to YYYY-MM-DD, parse amounts to two decimal places, map food & drink and meals to Food, "
    "transit to Transport, and books to Books, remove duplicate transaction_id rows, "
    "and preserve unrelated columns."
)


def save(report):
    temporary = REPORT.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    # Windows indexers/viewers can briefly hold the destination open.
    for attempt in range(10):
        try:
            temporary.replace(REPORT)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.2)


def recover():
    """Read already-persisted candidate outcomes; never rerun a model request."""
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    service = MoltService(MoltConfig(workspace=(ROOT / "workspace/submission-rung4").resolve(), sentry_dsn=""))
    for entry in report["trials"]:
        if entry["status"] != "PROCESS_INTERRUPTED" or "automation_id" not in entry:
            continue
        automation = service.get_automation(entry["automation_id"])
        versions = automation["versions"]
        passed = [v for v in versions if v.get("verification", {}).get("status") == "PASS"]
        entry.update(
            status="RECOVERED_PASS" if passed else "RECOVERED_NO_PASS",
            verification="PASS" if passed else "FAIL" if versions else "NO_CANDIDATE",
            pass_at_1=any(v["provider_metadata"].get("verification_attempt") == 1 for v in passed),
            pass_within_3=bool(passed),
            generation_requests_attempted=len(entry["requests"]), verified_candidates=len(versions),
            active_version_present=automation["active_version"] is not None,
            latency_seconds=None,
            recovery_note="Final JSON replace failed on Windows. Outcomes recovered from existing SQLite verification records; no model calls repeated. Total latency unavailable.",
        )
        entry["candidates"] = [{"status": v["status"], "checks_failed": v.get("verification", {}).get("checks_failed"),
                                "failed_check_codes": sorted({c["check"] for c in v.get("verification", {}).get("results", []) if c["status"] == "FAIL"})} for v in versions]
    save(report)
    print(json.dumps({"recovered_trials": [{"trial": e["trial"], "status": e["status"], "verified_candidates": e.get("verified_candidates")} for e in report["trials"]]}, indent=2))


def trial(number):
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    entry = report["trials"][-1]
    started = time.perf_counter()
    calls = []
    service = MoltService(MoltConfig(
        workspace=(ROOT / "workspace/submission-rung4").resolve(),
        sentry_dsn="", ollama_model="gemma3:4b",
        ollama_max_retries=2, ollama_timeout_seconds=120.0,
    ))
    auto = service.create_automation(f"Full task follow-up {number}")
    entry["automation_id"] = auto["id"]
    save(report)

    def measured(*args, **kwargs):
        call = {"number": len(calls) + 1, "status": "REQUEST_STARTED"}
        calls.append(call)
        entry["requests"] = calls
        save(report)  # Write before I/O so timeouts never look like zero calls.
        begin = time.perf_counter()
        try:
            recipe, metadata = generate_recipe(*args, **kwargs)
            call.update(status="SCHEMA_VALID", prompt_tokens=metadata.get("prompt_tokens"), response_tokens=metadata.get("response_tokens"))
            return recipe, metadata
        except MoltError as error:
            call.update(status="ERROR", error_code=error.code)
            raise
        finally:
            call["latency_seconds"] = round(time.perf_counter() - begin, 3)
            save(report)

    try:
        source_profile = profile_csv(ROOT / "examples/input/golden.csv")
        # Golden structural context only. No raw samples, file paths or held-out data.
        profile = {key: source_profile[key] for key in ("columns", "row_count", "inferred_types")}
        with patch("molt.application.generate_recipe", side_effect=measured):
            result = service.generate_candidate(auto["id"], TASK, profile, model="gemma3:4b")
        entry["status"] = result["status"]
        entry["verification"] = result["verification"]["status"]
        entry["pass_at_1"] = result["verification"]["status"] == "PASS" and len(calls) == 1
        entry["pass_within_3"] = result["verification"]["status"] == "PASS"
    except MoltError as error:
        entry.update(status="EXHAUSTED", error_code=error.code, verification="NO_PASS", pass_at_1=False, pass_within_3=False)
    finally:
        automation = service.get_automation(auto["id"])
        entry["candidates"] = [{
            "status": version["status"],
            "checks_total": version.get("verification", {}).get("checks_total"),
            "checks_failed": version.get("verification", {}).get("checks_failed"),
            "failed_checks": [{"check": check["check"], "structure": check.get("structure", {})}
                              for check in version.get("verification", {}).get("results", []) if check["status"] == "FAIL"],
        } for version in automation["versions"]]
        entry["active_version_present"] = automation["active_version"] is not None
        entry["latency_seconds"] = round(time.perf_counter() - started, 3)
        entry["generation_requests_attempted"] = len(calls)
        entry["verified_candidates"] = len(automation["versions"])
        save(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--trial", type=int, choices=range(1, 6))
    group.add_argument("--recover", action="store_true")
    args = parser.parse_args()
    if args.recover:
        recover()
        return
    if REPORT.exists():
        report = json.loads(REPORT.read_text(encoding="utf-8"))
    else:
        report = {
            "recorded_at": datetime.now(timezone.utc).isoformat(), "model": "gemma3:4b",
            "temperature": 0, "keep_alive": "15m", "request_timeout_seconds": 120,
            "max_requests_per_trial": 3, "trial_deadline_seconds": 390,
            "system_prompt_sha256": hashlib.sha256(COMPILER_INSTRUCTION.encode()).hexdigest(),
            "task_sha256": hashlib.sha256(TASK.encode()).hexdigest(),
            "original_evidence": "evidence/gemma-ladder-rung4.json",
            "changes": "Shorter system prompt and structural golden context; 120s timeout; warm model; expanded verifier fixtures. Not directly comparable to original 30s/3-request rung4.",
            "fixture_independence": "Expected outputs and held-out rows never sent. Structured verification feedback can include held-out failures, so these fixtures are regression/development tests, not an untouched final evaluation set.",
            "activation": "Measurement never approves or executes candidates.",
            "trials": [],
        }
        save(report)
        start = time.perf_counter()
        try:
            request = Request("http://127.0.0.1:11434/api/generate", data=json.dumps({"model": "gemma3:4b", "keep_alive": "15m", "stream": False}).encode(), headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=120) as response:
                payload = json.loads(response.read(65536))
            report["warmup"] = {"status": "COMPLETE", "done": payload.get("done"), "model": payload.get("model")}
        except Exception as error:
            report["warmup"] = {"status": "FAILED", "error_type": type(error).__name__}
        report["warmup"]["seconds"] = round(time.perf_counter() - start, 3)
        save(report)
    if args.trial in {entry["trial"] for entry in report["trials"]}:
        parser.error("Trial already recorded; preserve existing evidence.")
    report["trials"].append({"trial": args.trial, "status": "STARTED", "requests": []})
    save(report)
    process = multiprocessing.Process(target=trial, args=(args.trial,))
    process.start()
    process.join(390)
    if process.is_alive():
        process.terminate()
        process.join()
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    if report["trials"][-1]["status"] == "STARTED":
        report["trials"][-1]["status"] = "PROCESS_INTERRUPTED"
    report["summary"] = {
        "trials": len(report["trials"]),
        "pass_at_1": sum(entry.get("pass_at_1", False) for entry in report["trials"]),
        "pass_within_3": sum(entry.get("pass_within_3", False) for entry in report["trials"]),
        "generation_requests_attempted": sum(len(entry["requests"]) for entry in report["trials"]),
    }
    save(report)
    print(json.dumps({"latest": report["trials"][-1], "summary": report["summary"]}, indent=2))


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
