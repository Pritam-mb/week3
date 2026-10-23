"""Local artifact and offline-demo checks; no publishing or external accounts."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    draft = (ROOT / "POST_DRAFT.md").read_text(encoding="utf-8")
    local_links = [link for link in re.findall(r"\]\(([^)]+)\)", draft) if not link.startswith(("https://", "http://"))]
    missing = [link for link in local_links if not (ROOT / link).is_file()]
    ET.parse(ROOT / "evidence/pipeline.svg")
    parsed = sum(1 for path in (ROOT / "evidence").glob("*.json") if isinstance(json.loads(path.read_text(encoding="utf-8")), (list, dict)))
    with tempfile.TemporaryDirectory(prefix="molt-offline-submission-") as directory:
        env = {key: value for key, value in os.environ.items() if not re.search(r"TOKEN|SECRET|PASSWORD|DSN|API_KEY|^MOLT_|^OLLAMA_", key, re.I)}
        env["MOLT_ENV_FILE"] = str(Path(directory) / "absent.env")
        env["PYTHONPATH"] = str(ROOT)
        # Real CLI entry point with all socket connect attempts made fatal.
        command = (
            "import socket; "
            "def_no_network = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('NETWORK_FORBIDDEN')); "
            "socket.create_connection = def_no_network; socket.socket.connect = def_no_network; "
            "from molt.cli import main; "
            "raise SystemExit(main(['--state-dir', 'runtime', 'demo', '--offline', '--approve']))"
        )
        completed = subprocess.run([sys.executable, "-c", command], cwd=directory, env=env, capture_output=True, timeout=120)
        runs = Path(directory) / "runtime/runs.jsonl"
        records = [json.loads(line) for line in runs.read_text(encoding="utf-8").splitlines()] if runs.exists() else []
        statuses = {item["run_id"]: item["status"] for item in records}
        offline_pass = completed.returncode == 0 and len(records) == 4 and all(item["llm_calls"] == 0 for item in records)
        offline_pass &= sum(item["status"] == "SUCCEEDED" for item in records) == 2
        offline_pass &= sum(item["status"] == "BLOCKED_DRIFT" for item in records) == 2
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "offline_demo": {"status": "PASS" if offline_pass else "FAIL", "env_file": "absent", "credentials_removed_from_child_environment": True,
                         "network_connects": "forbidden", "exit_code": completed.returncode, "runs": statuses,
                         "scope": "Fresh temporary workspace, existing local Python installation; not a fresh OS installation."},
        "local_markdown_links": {"checked": len(local_links), "missing": missing},
        "pipeline_svg": "XML parsed", "evidence_json_files_parsed": parsed,
        "tags_present": all(tag in draft for tag in ("#devchallenge", "#hf26challenge")),
        "not_checked": ["external links on publication site", "image upload/render in publishing preview", "human read-aloud/external review"],
    }
    (ROOT / "evidence/submission-checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if offline_pass and not missing and report["tags_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
