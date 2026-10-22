from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from .core import (
    MoltError,
    execute_recipe,
    execute_recipe_resumable,
    fingerprint_file,
    load_json,
    profile_csv,
    read_csv,
    safe_name,
    save_json,
    schema_fingerprint,
    operation_diff,
    verify_recipe,
    write_csv_atomic,
)
from .ollama import generate_recipe, load_fixture_recipe
from .application import MoltService
from .config import config_from_workspace
from .http_api import serve
from .watcher import FolderWatcher
from .ollama import readiness
from .temporal import run_worker, start_cli_run


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RECIPE = ROOT / "examples" / "recipes" / "expense-v1.json"
DEFAULT_INPUT = ROOT / "examples" / "input"
DEFAULT_EXPECTED = ROOT / "examples" / "expected"


def _json_print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def _state_path(state_dir: Path, name: str) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / name


def _workspace_arg(value: str | None) -> Path:
    return config_from_workspace(value).workspace


def run_once(recipe: dict[str, Any], input_path: Path, output_path: Path, state_dir: Path, *, run_name: str, crash_after: int | None = None, resume: bool = False, llm_calls: int = 0) -> dict[str, Any]:
    started = time.perf_counter()
    run_dir = state_dir / "runs" / safe_name(run_name)
    try:
        headers, rows = read_csv(input_path)
        result_headers, result_rows, resumed_from = execute_recipe_resumable(recipe, headers, rows, run_dir / "checkpoints", resume=resume, crash_after=crash_after)
        write_csv_atomic(output_path, result_headers, result_rows)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record = {
            "run_id": safe_name(run_name), "status": "SUCCEEDED", "input": str(input_path), "output": str(output_path),
            "file_fingerprint": fingerprint_file(input_path), "schema_fingerprint": schema_fingerprint(headers),
            "rows_read": len(rows), "rows_written": len(result_rows), "llm_calls": llm_calls,
            "duration_ms": duration_ms, "resumed_from_step": resumed_from,
        }
    except MoltError as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record = {"run_id": safe_name(run_name), "status": "BLOCKED_DRIFT" if exc.code in {"REQUIRED_COLUMN_MISSING", "UNMAPPED_VALUE"} else "FAILED", "input": str(input_path), "output": None, "error_code": exc.code, "message": exc.message, "details": exc.details, "llm_calls": llm_calls, "duration_ms": duration_ms}
    save_json(run_dir / "report.json", record)
    with _state_path(state_dir, "runs.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(record, sort_keys=True) + "\n")
    return record


def demo(args: argparse.Namespace) -> int:
    state_dir = _workspace_arg(args.state_dir)
    candidate_path = _state_path(state_dir, "candidate.json")
    active_path = _state_path(state_dir, "active.json")
    print("MOLT - Slow and Steady demo")
    print("1. COMPILE: profile the example and prepare a constrained recipe")
    profile = profile_csv(DEFAULT_INPUT / "golden.csv")
    print(f"   Profiled {profile['row_count']} rows and {len(profile['columns'])} columns")
    metadata = {"source": "offline_fixture", "llm_calls": 0, "model": None}
    if args.model:
        try:
            recipe, metadata = generate_recipe(args.model, "Normalize this synthetic expense export", profile)
        except MoltError as exc:
            print(f"   FAIL {exc.code}: {exc.message}")
            return 1
    else:
        recipe = load_fixture_recipe(DEFAULT_RECIPE)
    save_json(candidate_path, {"recipe": recipe, "metadata": metadata, "status": "CANDIDATE"})
    print(f"   Candidate saved: {candidate_path} ({metadata['source'] if 'source' in metadata else 'ollama'})")

    print("2. VERIFY: replay golden and held-out fixtures")
    verification = verify_recipe(recipe, [(DEFAULT_INPUT / "golden.csv", DEFAULT_EXPECTED / "golden.csv"), (DEFAULT_INPUT / "heldout.csv", DEFAULT_EXPECTED / "heldout.csv")])
    for result in verification["results"]:
        print(f"   {result['status']:4} {result['fixture']}: {result['check']}")
    if verification["status"] != "PASS":
        print("   Candidate is not eligible for approval.")
        return 1
    print(f"   PASS {verification['checks_passed']}/{verification['checks_total']} mandatory checks")
    if not args.approve:
        print("   A human approval is required. Re-run with --approve after reviewing the candidate.")
        return 2

    print("3. APPROVE: activate verified recipe")
    active = {"version": 1, "status": "ACTIVE", "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "recipe": recipe, "verification": verification, "metadata": metadata}
    save_json(active_path, active)
    print(f"   Active recipe v1: {active_path}")

    print("4. REUSE: deterministic runs (no additional model calls)")
    for name in ("golden-reuse", "heldout-reuse"):
        source = DEFAULT_INPUT / ("golden.csv" if name.startswith("golden") else "heldout.csv")
        record = run_once(recipe, source, state_dir / "done" / f"{name}.csv", state_dir, run_name=name, llm_calls=0)
        print(f"   {record['status']:10} {name}: llm_calls={record['llm_calls']}, rows={record.get('rows_written', 0)}")

    print("5. DRIFT: fail closed and quarantine invalid inputs")
    for name in ("missing-column", "unmapped-category"):
        source = DEFAULT_INPUT / ("drift-missing-column.csv" if name.startswith("missing") else "drift-unmapped-category.csv")
        record = run_once(recipe, source, state_dir / "done" / f"{name}.csv", state_dir, run_name=name)
        quarantine = state_dir / "quarantine" / source.name
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, quarantine)
        print(f"   {record['status']:13} {name}: {record.get('error_code')} -> {quarantine}")

    calls_avoided = 2
    ledger = {"baseline": "one model call per comparable file", "comparable_runs": 2, "actual_execution_calls": 0, "calls_avoided": calls_avoided, "generation_calls": metadata.get("llm_calls", 0), "note": "Calls avoided excludes one-time generation/verification overhead."}
    save_json(_state_path(state_dir, "ledger.json"), ledger)
    print(f"6. LEDGER: {calls_avoided} steady-state model calls avoided; generation overhead recorded separately")
    print(f"Reports: {state_dir.resolve()}")
    return 0


def command_run(args: argparse.Namespace) -> int:
    state_dir = _workspace_arg(args.state_dir)
    if not (state_dir / "active.json").exists():
        service = MoltService(config_from_workspace(state_dir))
        automation = service.list_automations()
        if not automation:
            print("No automation exists in the workspace. Use the dashboard/API to create one.")
            return 1
        active = next((item for item in automation if item.get("active_version")), None)
        if not active:
            print("No active recipe exists in the workspace.")
            return 1
        record = service.run(active["id"], args.input, output_path=args.output)
        _json_print(record)
        return 0 if record["status"] == "SUCCEEDED" else 1
    active = load_json(state_dir / "active.json")
    record = run_once(active["recipe"], Path(args.input), Path(args.output), state_dir, run_name=args.run_name, resume=args.resume, crash_after=args.crash_after)
    _json_print(record)
    return 0 if record["status"] == "SUCCEEDED" else 1


def command_serve(args: argparse.Namespace) -> int:
    config = config_from_workspace(args.state_dir)
    serve(config, host=args.host or config.host, port=args.port or config.port)
    return 0


def command_init(args: argparse.Namespace) -> int:
    config = config_from_workspace(args.state_dir)
    config.prepare()
    MoltService(config)
    print(f"Initialized Molt workspace: {config.workspace}")
    for directory in (config.input_dir, config.done_dir, config.quarantine_dir, config.reports_dir, config.archive_dir, config.checkpoints_dir, config.uploads_dir):
        print(f"  {directory.name}/")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    config = config_from_workspace(args.state_dir)
    checks: list[tuple[str, str, str]] = []
    service: MoltService | None = None
    checks.append(("python", "PASS" if sys.version_info >= (3, 11) else "WARN", sys.version.split()[0]))
    try:
        config.prepare()
        probe = config.workspace / ".molt-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        service = MoltService(config)
        checks.append(("workspace_and_sqlite", "PASS", str(config.workspace)))
    except Exception as exc:
        checks.append(("workspace_and_sqlite", "FAIL", str(exc)))
    model_status = readiness(config.ollama_base_url, config.ollama_model, timeout=min(config.ollama_timeout_seconds, 5.0))
    model_state = model_status.get("status")
    checks.append(("ollama_server", "PASS" if model_state in {"ready", "model_missing"} else "WARN", f"{config.ollama_base_url} ({model_state})"))
    checks.append(("ollama_model", "PASS" if model_state == "ready" else "WARN", config.ollama_model if model_state != "unreachable" else "Start Ollama first"))
    checks.append(("telemetry", "PASS" if config.sentry_dsn else "INFO", "configured" if config.sentry_dsn else "disabled/local-only"))
    if service is not None:
        tabpfn = service.anomaly.readiness()
        tabpfn_state = tabpfn["readiness"]
        checks.append(("tabpfn", "PASS" if tabpfn_state == "ready_for_supervised_triage" else "INFO", f"{tabpfn_state}: {tabpfn['reason']}"))
    else:
        checks.append(("tabpfn", "INFO", "not checked because workspace initialization failed"))
    print("Molt doctor")
    print(f"Effective configuration: {json.dumps(config.as_public_dict(), sort_keys=True)}")
    for name, status, detail in checks:
        print(f"[{status}] {name}: {detail}")
    if model_state == "unreachable":
        print("  Ollama remediation: install/start Ollama, then pull the configured model with `ollama pull <model>`.")
    elif model_state == "model_missing":
        print(f"  Ollama remediation: run `ollama pull {config.ollama_model}`.")
    required_failed = any(status == "FAIL" for _, status, _ in checks)
    ollama_required = args.require_ollama and model_state != "ready"
    return 1 if required_failed or ollama_required else 0


def command_watch(args: argparse.Namespace) -> int:
    config = config_from_workspace(args.state_dir)
    service = MoltService(config)
    automation_id = args.automation_id
    if not automation_id:
        automation = next((item for item in service.list_automations() if item.get("active_version")), None)
        if not automation:
            print("No active automation found. Pass --automation-id or approve a recipe first.")
            return 1
        automation_id = automation["id"]
    FolderWatcher(service, automation_id, config).run_forever()
    return 0


def _temporal_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--address", default=None, help="Temporal server address (default: MOLT_TEMPORAL_ADDRESS or 127.0.0.1:7233)")
    parser.add_argument("--namespace", default=None, help="Temporal namespace (default: MOLT_TEMPORAL_NAMESPACE or default)")
    parser.add_argument("--task-queue", default=None, help="Temporal task queue (default: MOLT_TEMPORAL_TASK_QUEUE or molt)")


def command_temporal_worker(args: argparse.Namespace) -> int:
    run_worker(
        address=args.address or os.environ.get("MOLT_TEMPORAL_ADDRESS", "127.0.0.1:7233"),
        namespace=args.namespace or os.environ.get("MOLT_TEMPORAL_NAMESPACE", "default"),
        task_queue=args.task_queue or os.environ.get("MOLT_TEMPORAL_TASK_QUEUE", "molt"),
        max_concurrent_activities=args.max_concurrent_activities,
    )
    return 0


def command_temporal_start(args: argparse.Namespace) -> int:
    workspace = _workspace_arg(args.state_dir)
    result = start_cli_run(
        workspace=workspace,
        automation_id=args.automation_id,
        input_path=args.input,
        output_path=args.output,
        workflow_id=args.workflow_id,
        address=args.address or os.environ.get("MOLT_TEMPORAL_ADDRESS", "127.0.0.1:7233"),
        namespace=args.namespace or os.environ.get("MOLT_TEMPORAL_NAMESPACE", "default"),
        task_queue=args.task_queue or os.environ.get("MOLT_TEMPORAL_TASK_QUEUE", "molt"),
        wait=not args.no_wait,
        activity_timeout_seconds=args.activity_timeout_seconds,
    )
    _json_print(result)
    result_status = result.get("result", {}).get("status")
    return 1 if result_status == "FAILED" else 0


def command_temporal_demo(args: argparse.Namespace) -> int:
    print("Temporal demo: starting one approved Molt execution through a Temporal workflow.")
    print("A Temporal server and a worker must already be running; this command does not start either one.")
    return command_temporal_start(args)


def command_init_demo(args: argparse.Namespace) -> int:
    config = config_from_workspace(args.state_dir)
    service = MoltService(config)
    input_path = config.input_dir / "expense-demo.csv"
    shutil.copy2(DEFAULT_INPUT / "golden.csv", input_path)
    automation = service.create_automation("Expense export normalizer", "Normalize synthetic expense CSV exports locally.", str(input_path))
    profile = service.profile(input_path)
    version = service.generate_candidate(automation["id"], "Normalize the expense export", profile, recipe_file=str(DEFAULT_RECIPE))
    verification = service.verify_version(version["id"])
    if verification["status"] != "PASS":
        print(json.dumps(verification, indent=2))
        return 1
    if args.approve:
        active = service.approve_version(version["id"])
        print(f"Demo automation ready: {automation['id']} active recipe v{active['version_number']}")
    else:
        print(f"Candidate ready for review: automation={automation['id']} version={version['id']}")
        print("Re-run with --approve to activate it.")
    return 0


def command_compile(args: argparse.Namespace) -> int:
    config = config_from_workspace(args.state_dir)
    service = MoltService(config)
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        print(f"Input file does not exist: {input_path}", file=sys.stderr)
        return 1
    automation = service.create_automation(args.name, args.task, str(input_path))
    profile = service.profile(input_path)
    version = service.generate_candidate(automation["id"], args.task, profile, recipe_file=args.recipe_file, model=args.model)
    verification = service.verify_version(version["id"])
    _json_print({"automation": automation["id"], "version": version["id"], "verification": verification, "model": args.model or config.ollama_model if not args.recipe_file else None})
    if verification["status"] != "PASS":
        return 1
    if args.approve:
        active = service.approve_version(version["id"])
        print(f"Approved automation {automation['id']} version {active['version_number']}.")
    else:
        print(f"Candidate created. Review it, then approve version {version['id']} through the dashboard or API.")
    return 0


def propose_repair(args: argparse.Namespace) -> int:
    state_dir = _workspace_arg(args.state_dir)
    active = load_json(state_dir / "active.json")
    base_recipe = active["recipe"]
    if args.recipe_file:
        candidate = load_fixture_recipe(Path(args.recipe_file))
        metadata = {"source": "manual_candidate", "llm_calls": 0}
    else:
        if not args.model:
            print("Provide --recipe-file for a local candidate or --model for an Ollama proposal.")
            return 2
        drift_profile = profile_csv(Path(args.input))
        try:
            candidate, metadata = generate_recipe(args.model, "Repair the active expense recipe for this drifted input", drift_profile)
        except MoltError as exc:
            print(f"FAIL {exc.code}: {exc.message}")
            return 1
    proposal = {"status": "PROPOSED", "base_version": active["version"], "recipe": candidate, "metadata": metadata, "operation_diff": operation_diff(base_recipe, candidate), "drift_input": args.input}
    save_json(state_dir / "repair-candidate.json", proposal)
    print(f"Repair candidate saved separately from active v{active['version']}: {state_dir / 'repair-candidate.json'}")
    for change in proposal["operation_diff"]:
        print(f"  {change}")
    return 0


def verify_repair(args: argparse.Namespace) -> int:
    state_dir = _workspace_arg(args.state_dir)
    proposal = load_json(state_dir / "repair-candidate.json")
    verification = verify_recipe(proposal["recipe"], [(DEFAULT_INPUT / "golden.csv", DEFAULT_EXPECTED / "golden.csv"), (DEFAULT_INPUT / "heldout.csv", DEFAULT_EXPECTED / "heldout.csv")])
    proposal["verification"] = verification
    proposal["status"] = "VERIFIED" if verification["status"] == "PASS" else "REJECTED"
    save_json(state_dir / "repair-candidate.json", proposal)
    _json_print(verification)
    return 0 if verification["status"] == "PASS" else 1


def approve_repair(args: argparse.Namespace) -> int:
    state_dir = _workspace_arg(args.state_dir)
    active = load_json(state_dir / "active.json")
    proposal = load_json(state_dir / "repair-candidate.json")
    if proposal.get("status") != "VERIFIED" or proposal.get("verification", {}).get("status") != "PASS":
        print("Repair cannot be activated without a passing full verification result.")
        return 1
    active = {"version": active["version"] + 1, "status": "ACTIVE", "approved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "recipe": proposal["recipe"], "verification": proposal["verification"], "metadata": proposal.get("metadata", {}), "previous_version": proposal["base_version"]}
    save_json(state_dir / "active.json", active)
    proposal["status"] = "APPROVED"
    proposal["approved_version"] = active["version"]
    save_json(state_dir / "repair-candidate.json", proposal)
    print(f"Approved repair as active v{active['version']}; previous version remains recorded as v{proposal['base_version']}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="molt", description="Compile once, verify against truth, reuse without repeated inference.")
    parser.add_argument("--state-dir", help="Single Molt workspace directory (default: MOLT_DATA_DIR or workspace)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo_parser = subparsers.add_parser("demo", help="Run the complete offline challenge demonstration")
    demo_parser.add_argument("--offline", action="store_true", help="Use the checked-in candidate recipe")
    demo_parser.add_argument("--model", help="Use this local Ollama model for compile instead of the fixture")
    demo_parser.add_argument("--approve", action="store_true", help="Explicitly approve the verified candidate")
    demo_parser.set_defaults(func=demo)
    run_parser = subparsers.add_parser("run", help="Run the active recipe on a CSV")
    run_parser.add_argument("input")
    run_parser.add_argument("output")
    run_parser.add_argument("--run-name", default="manual-run")
    run_parser.add_argument("--resume", action="store_true")
    run_parser.add_argument("--crash-after", type=int)
    run_parser.set_defaults(func=command_run)
    serve_parser = subparsers.add_parser("serve", help="Start the local API and browser dashboard")
    serve_parser.add_argument("--host")
    serve_parser.add_argument("--port", type=int)
    serve_parser.set_defaults(func=command_serve)
    watch_parser = subparsers.add_parser("watch", help="Poll the workspace/in folder and process stable CSV files")
    watch_parser.add_argument("--automation-id")
    watch_parser.set_defaults(func=command_watch)

    temporal_parser = subparsers.add_parser("temporal", help="Use the optional Temporal durable execution boundary")
    temporal_subparsers = temporal_parser.add_subparsers(dest="temporal_command", required=True)
    temporal_worker_parser = temporal_subparsers.add_parser("worker", help="Run a Temporal worker for approved Molt runs")
    _temporal_connection_args(temporal_worker_parser)
    temporal_worker_parser.add_argument("--max-concurrent-activities", type=int, default=10)
    temporal_worker_parser.set_defaults(func=command_temporal_worker)
    for command_name, command_func, help_text in (("start", command_temporal_start, "Start a durable approved-recipe workflow"), ("demo", command_temporal_demo, "Start a durable workflow for a prepared demo automation")):
        temporal_run_parser = temporal_subparsers.add_parser(command_name, help=help_text)
        temporal_run_parser.add_argument("--automation-id", required=True)
        temporal_run_parser.add_argument("--input", required=True, help="CSV inside the Molt workspace")
        temporal_run_parser.add_argument("--output")
        temporal_run_parser.add_argument("--workflow-id", help="Stable ID used for client-side start idempotency")
        temporal_run_parser.add_argument("--no-wait", action="store_true", help="Return after starting instead of waiting for the result")
        temporal_run_parser.add_argument("--activity-timeout-seconds", type=int, default=300)
        _temporal_connection_args(temporal_run_parser)
        temporal_run_parser.set_defaults(func=command_func)

    # Flat aliases are convenient for installations that prefer one executable action.
    temporal_worker_alias = subparsers.add_parser("temporal-worker", help="Alias for `temporal worker`")
    _temporal_connection_args(temporal_worker_alias)
    temporal_worker_alias.add_argument("--max-concurrent-activities", type=int, default=10)
    temporal_worker_alias.set_defaults(func=command_temporal_worker)
    for command_name, command_func in (("temporal-start", command_temporal_start), ("temporal-demo", command_temporal_demo)):
        temporal_alias = subparsers.add_parser(command_name, help=f"Alias for `temporal {command_name.removeprefix('temporal-')}`")
        temporal_alias.add_argument("--automation-id", required=True)
        temporal_alias.add_argument("--input", required=True)
        temporal_alias.add_argument("--output")
        temporal_alias.add_argument("--workflow-id")
        temporal_alias.add_argument("--no-wait", action="store_true")
        temporal_alias.add_argument("--activity-timeout-seconds", type=int, default=300)
        _temporal_connection_args(temporal_alias)
        temporal_alias.set_defaults(func=command_func)
    init_parser = subparsers.add_parser("init-demo", help="Create one SQLite-backed demo automation in the workspace")
    init_parser.add_argument("--approve", action="store_true")
    init_parser.set_defaults(func=command_init_demo)
    compile_parser = subparsers.add_parser("compile", help="Profile a CSV, compile a candidate, verify it, and optionally approve it")
    compile_parser.add_argument("--input", required=True, help="CSV inside the configured workspace")
    compile_parser.add_argument("--name", required=True)
    compile_parser.add_argument("--task", required=True)
    compile_parser.add_argument("--model")
    compile_parser.add_argument("--recipe-file", help="Use a checked-in fixture recipe instead of Ollama")
    compile_parser.add_argument("--approve", action="store_true")
    compile_parser.set_defaults(func=command_compile)
    clean_init_parser = subparsers.add_parser("init", help="Create an empty SQLite-backed Molt workspace")
    clean_init_parser.set_defaults(func=command_init)
    doctor_parser = subparsers.add_parser("doctor", help="Check runtime, workspace, server, and Ollama readiness")
    doctor_parser.add_argument("--require-ollama", action="store_true", help="Return failure unless the configured model is ready")
    doctor_parser.set_defaults(func=command_doctor)
    repair_parser = subparsers.add_parser("repair-propose", help="Save a repair candidate without changing the active recipe")
    repair_parser.add_argument("--recipe-file")
    repair_parser.add_argument("--model")
    repair_parser.add_argument("--input", default=str(DEFAULT_INPUT / "drift-missing-column.csv"))
    repair_parser.set_defaults(func=propose_repair)
    repair_verify_parser = subparsers.add_parser("repair-verify", help="Run the complete fixture suite against a repair candidate")
    repair_verify_parser.set_defaults(func=verify_repair)
    repair_approve_parser = subparsers.add_parser("repair-approve", help="Activate only a passing, explicitly approved repair")
    repair_approve_parser.set_defaults(func=approve_repair)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MoltError as exc:
        print(f"Molt error [{exc.code}]: {exc.message}", file=sys.stderr)
        if exc.details:
            print(json.dumps(exc.details, sort_keys=True), file=sys.stderr)
        return 1
