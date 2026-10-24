"""Local process-kill evidence, not a model benchmark or production load test.

Uses the real HTTP start/status routes and production Temporal worker. A test-only
barrier pauses immediately after checkpoint publication, so kills are repeatable
rather than random. Only processes created by this script are stopped.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from molt.application import MoltService
from molt.config import MoltConfig
from molt.core import read_csv, save_json
from molt.http_api import MoltHandler
from molt.temporal import run_worker


ROOT = Path(__file__).resolve().parent
QUEUE = "molt-chaos-evidence"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def worker_main(address: str, marker: Path, pause_step: int) -> None:
    def save_and_pause(path, value):
        save_json(path, value)
        if path.name == "state.json" and value.get("status") == "running" and value.get("completed_steps") == pause_step:
            marker.write_text(str(pause_step), encoding="utf-8")
            # Only the evidence worker pauses; production workers never do.
            time.sleep(120)

    with patch("molt.core.save_json", side_effect=save_and_pause), patch(
        "molt.application.generate_recipe", side_effect=AssertionError("Reuse must not call a model")
    ):
        run_worker(address=address, namespace="default", task_queue=QUEUE, max_concurrent_activities=1)


def api(base: str, path: str, body: dict | None = None) -> dict:
    request = Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=15) as response:
        return json.load(response)


def wait_marker(marker: Path, worker: subprocess.Popen, timeout: int = 75) -> None:
    deadline = time.monotonic() + timeout
    while not marker.exists():
        require(worker.poll() is None, "Evidence worker exited before checkpoint barrier")
        require(time.monotonic() < deadline, "Timed out waiting for checkpoint barrier")
        time.sleep(0.1)


def wait_workflow(base: str, workflow_id: str) -> dict:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        response = api(base, f"/api/temporal-runs/{workflow_id}")
        if response["status"] != "RUNNING":
            require(response["status"] == "COMPLETED", "Temporal workflow did not complete")
            return response
        time.sleep(0.5)
    raise RuntimeError("Timed out waiting for workflow completion")


def signature(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


async def history_attempts(address: str, workflow_ids: list[str]) -> dict[str, int]:
    from temporalio.client import Client
    from temporal_crash_recovery import activity_attempts

    client = await Client.connect(address)
    return {workflow_id: activity_attempts([event async for event in client.get_workflow_handle(workflow_id).fetch_history_events()])
            for workflow_id in workflow_ids}


def run(temporal_cli: str) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="molt-chaos-") as directory:
        root = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        address = f"127.0.0.1:{port}"
        config = MoltConfig(root / "workspace", sentry_dsn="", temporal_address=address, temporal_task_queue=QUEUE)
        service = MoltService(config)
        sources = {}
        for name, fixture in (("golden", "golden"), ("heldout", "heldout"), ("drift", "drift-unmapped-category")):
            sources[name] = config.input_dir / f"{name}.csv"
            shutil.copyfile(ROOT / f"examples/input/{fixture}.csv", sources[name])
        source_hashes = {name: signature(path)[0] for name, path in sources.items()}
        automation = service.create_automation("Slow and steady recovery", "Synthetic fixture demonstration")
        version = service.generate_candidate(automation["id"], "Normalize", service.profile(sources["golden"]),
                                             recipe_file=str(ROOT / "examples/recipes/expense-v1.json"))
        require(service.verify_version(version["id"])["status"] == "PASS", "Fixture verification failed")
        service.approve_version(version["id"])
        handler = type("EvidenceHandler", (MoltHandler,), {"service": service, "log_message": lambda *args: None})
        http = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=http.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{http.server_port}"
        # Do not inherit repository .env or credentials into child processes.
        env = {key: os.environ[key] for key in ("PATH", "HOME", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG") if key in os.environ}
        env["MOLT_ENV_FILE"] = str(root / "absent.env")
        processes: list[subprocess.Popen] = []
        logs = []

        def launch(command: list[str], name: str) -> subprocess.Popen:
            log = (root / f"{name}.log").open("wb")
            logs.append(log)
            process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            processes.append(process)
            return process

        def start_server(name: str) -> subprocess.Popen:
            process = launch([temporal_cli, "server", "start-dev", "--ip", "127.0.0.1", "--port", str(port),
                              "--headless", "--db-filename", str(root / "temporal.sqlite")], name)
            deadline = time.monotonic() + 40
            while time.monotonic() < deadline:
                require(process.poll() is None, "Evidence Temporal server exited during startup")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                        return process
                except OSError:
                    time.sleep(0.2)
            raise RuntimeError("Evidence Temporal server did not start")

        def start_worker(step: int) -> tuple[subprocess.Popen, Path]:
            marker = root / f"pause-{step}"
            process = launch([sys.executable, str(Path(__file__).resolve()), "--worker", "--address", address,
                              "--marker", str(marker), "--pause-step", str(step)], f"worker-{step}")
            return process, marker

        def start(name: str, suffix: str = "") -> str:
            response = api(base, f"/api/automations/{automation['id']}/temporal-runs", {
                "input_reference": f"in/{name}.csv", "output_reference": f"done/{name}.csv",
                "workflow_id": f"molt-chaos-{name}{suffix}", "wait": False, "activity_timeout_seconds": 20,
            })
            require(response["status"] == "STARTED", "HTTP route did not start workflow")
            return response["workflow_id"]

        try:
            server = start_server("server-first")
            worker, marker = start_worker(1)
            first_id = start("golden")
            wait_marker(marker, worker)
            first_step = next(config.checkpoints_dir.glob("*/step_1.csv"))
            first_signature = signature(first_step)
            worker.kill()
            worker.wait(timeout=10)
            server.kill()
            server.wait(timeout=10)
            require((root / "temporal.sqlite").is_file(), "Server persistence file missing")
            server = start_server("server-restarted")
            worker, marker = start_worker(2)
            wait_marker(marker, worker)
            require(signature(first_step) == first_signature, "Completed step 1 was redone")
            second_step = first_step.parent / "step_2.csv"
            second_signature = signature(second_step)
            worker.kill()
            worker.wait(timeout=10)
            worker, _ = start_worker(0)
            first = wait_workflow(base, first_id)
            require(signature(first_step) == first_signature and signature(second_step) == second_signature,
                    "Completed checkpoints were rewritten")
            # The remaining files are ordinary work, not special chaos activities.
            second_id, drift_id = start("heldout"), start("drift")
            second, drift = wait_workflow(base, second_id), wait_workflow(base, drift_id)
            output = config.done_dir / "golden.csv"
            output_before = signature(output)
            replay_id = start("golden", "-replay")
            replay = wait_workflow(base, replay_id)
            attempts = asyncio.run(history_attempts(address, [first_id, second_id, drift_id, replay_id]))
            return build_report(service, sources, source_hashes, first, second, drift, replay,
                                attempts, output_before, started)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
            http.shutdown()
            http.server_close()
            thread.join(timeout=5)
            for log in logs:
                log.close()


def build_report(service, sources, source_hashes, first, second, drift, replay, attempts, output_before, started) -> dict:
    config = service.config
    oracle_matches = sum(read_csv(config.done_dir / f"{name}.csv") == read_csv(ROOT / f"examples/expected/{name}.csv")
                         for name in ("golden", "heldout"))
    checks = {
        "successful_files": first["result"]["status"] == second["result"]["status"] == "SUCCEEDED",
        "independent_oracles_match": oracle_matches == 2,
        "retry_attempts_observed": attempts[first["workflow_id"]] == 3,
        "drift_not_retried": drift["result"]["status"] == "BLOCKED_DRIFT" and attempts[drift["workflow_id"]] == 1,
        "drift_quarantined_without_output": len(list(config.quarantine_dir.glob("*.csv"))) == 1 and not (config.done_dir / "drift.csv").exists(),
        "replay_idempotent": replay["result"]["temporal_outcome"] == "idempotent_replay" and service.metrics()["total_runs"] == 3,
        "output_not_rewritten": signature(config.done_dir / "golden.csv") == output_before,
        "source_bytes_preserved": all(signature(path)[0] == source_hashes[name] for name, path in sources.items()),
        "zero_run_model_calls": all(item["result"]["llm_calls"] == 0 for item in (first, second, drift, replay)),
    }
    return {
        "status": "COMPLETE" if all(checks.values()) else "FAILED",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.monotonic() - started, 2),
        "checks": checks,
        "failure_injection": {
            "worker_process_kills": 2, "server_process_kills": 1,
            "method": "SIGKILL" if os.name == "posix" else "TerminateProcess",
            "timing": "Deterministic test-only barriers after checkpoints 1 and 2; not random kills",
            "server_persistence": "Same local SQLite file and port after restart",
            "completed_checkpoints_not_rewritten": 2,
        },
        "batch": {"input_files": 3, "successful_outputs": oracle_matches, "blocked_drift": 1,
                  "replay_workflows": 1, "execution_records": service.metrics()["total_runs"], "model_calls": 0},
        "workflows": [{"case": label, "temporal_status": item["status"], "molt_status": item["result"]["status"],
                       "outcome": item["result"]["temporal_outcome"], "activity_attempts": attempts[item["workflow_id"]]}
                      for label, item in (("checkpoint_recovery", first), ("compatible_reuse", second), ("drift", drift), ("replay", replay))],
        "claim_boundary": "Real local HTTP API, Temporal dev server and production worker; synthetic CSVs, fixture recipe, scripted approval. Two worker process kills and one persistent-server process kill. No live Gemma compilation, model API retry/cache, power-loss, multi-host, or production durability claim. Shared workspace retained; approval/input unchanged during recovery.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temporal-cli", default=shutil.which("temporal"), help="Path to installed Temporal CLI")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--address", default="127.0.0.1:7233", help=argparse.SUPPRESS)
    parser.add_argument("--marker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--pause-step", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        worker_main(args.address, args.marker, args.pause_step)
        return 0
    if not args.temporal_cli:
        parser.error("Install the Temporal CLI or pass --temporal-cli; no Cloud account is needed")
    try:
        result = run(str(Path(args.temporal_cli).resolve()))
    except Exception as exc:
        result = {"status": "FAILED", "error_type": type(exc).__name__, "recorded_at": datetime.now(timezone.utc).isoformat()}
        print(f"Chaos check failed: {exc}", file=sys.stderr)
    save_json(ROOT / "evidence/temporal-chaos.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
