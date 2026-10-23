"""Read-only reachable-history audit; prints counts, never matched secrets."""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def main():
    # Authorized credential audit: compare local values in memory only. Never
    # persist values, hashes of values, matched lines, or arbitrary log payloads.
    names = ("TABPFN_TOKEN", "SENTRY_DSN")
    local = {}
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                if key.strip() in names:
                    local[key.strip()] = value.strip().strip('"').strip("'")
    values = {name: {v.encode() for v in (os.environ.get(name, ""), local.get(name, "")) if len(v) > 12} for name in names}
    objects = git("rev-list", "--objects", "--all").splitlines()
    hits = {name: 0 for name in names}
    env_paths = set()
    blobs = 0
    signature_blobs = 0
    signature_paths = set()
    signature_review = []
    signatures = re.compile(rb"https://[a-fA-F0-9]{32}@[^\s\"']*sentry[^\s\"']*|hf_[A-Za-z0-9]{30,}|eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}")
    batch = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for item in objects:
        oid, _, raw_path = item.partition(b" ")
        path = raw_path.decode("utf-8", "replace")
        base = path.rsplit("/", 1)[-1]
        if base == ".env" or (base.startswith(".env.") and base not in {".env.example", ".env.sample", ".env.template"}):
            env_paths.add(path)
        batch.stdin.write(oid + b"\n")
        batch.stdin.flush()
        header = batch.stdout.readline().split()
        content = batch.stdout.read(int(header[2]))
        batch.stdout.read(1)
        if header[1] != b"blob":
            continue
        blobs += 1
        for name in names:
            hits[name] += int(any(value in content for value in values[name]))
        matches = list(signatures.finditer(content))
        if matches:
            signature_blobs += 1
            signature_paths.add(path)
            for match in matches:
                value = match.group()
                is_dsn = value.startswith(b"https://")
                public_key = value.split(b"@")[0].removeprefix(b"https://") if is_dsn else b""
                signature_review.append({
                    "path": path,
                    "kind": "sentry_dsn" if is_dsn else "token_pattern",
                    "repeated_character_example_key": is_dsn and len(set(public_key)) == 1,
                    "matches_current_known_value": any(value == secret for secrets in values.values() for secret in secrets),
                })
    batch.stdin.close()
    batch.wait()
    tracked = git("ls-files", "--", ".env").decode().splitlines()
    current_signature_paths = []
    for path in sorted(signature_paths):
        current = ROOT / path
        if current.is_file() and signatures.search(current.read_bytes()):
            current_signature_paths.append(path)
    report = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "revision": git("rev-parse", "HEAD").decode().strip(),
        "scope": "All blobs reachable from local Git refs (--all); no remote fetch or history rewrite.",
        "reachable_blobs_scanned": blobs,
        "private_env_paths_in_history": sorted(env_paths),
        "env_tracked_now": bool(tracked),
        "env_ignored_now": subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT).returncode == 0,
        "known_credential_values_available_for_scan": {name: bool(values[name]) for name in names},
        "known_credential_matching_blob_counts": hits,
        "credential_signature_matching_blob_count": signature_blobs,
        "credential_signature_paths_for_private_review": sorted(signature_paths),
        "signature_review_without_values": signature_review,
        "signature_paths_still_in_working_tree": current_signature_paths,
        "limitations": "No proof that arbitrary old/rotated or unrecognized secrets never existed. Reflog-only, unreachable, remote-only objects and chat/screenshots are outside scope. Pattern matches need private review.",
        "sentry_rotation": "NOT_DONE; dashboard account access required; historical chat exposure still requires rotation.",
    }
    (ROOT / "evidence/repo-hygiene.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
