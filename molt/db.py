from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS automations (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL, active_version_id TEXT, input_reference TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recipe_versions (
  id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id), version_number INTEGER NOT NULL,
  recipe_json TEXT NOT NULL, schema_fingerprint TEXT NOT NULL, created_from TEXT NOT NULL, status TEXT NOT NULL,
  base_version_id TEXT, model_name TEXT, provider_metadata_json TEXT NOT NULL DEFAULT '{}',
  approved_at TEXT, created_at TEXT NOT NULL, UNIQUE(automation_id, version_number)
);
CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, path TEXT NOT NULL, root_name TEXT NOT NULL,
  file_fingerprint TEXT, size_bytes INTEGER, created_at TEXT NOT NULL, UNIQUE(root_name, path)
);
CREATE TABLE IF NOT EXISTS test_fixtures (
  id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id), name TEXT NOT NULL,
  input_artifact_id TEXT NOT NULL REFERENCES artifacts(id), expected_artifact_id TEXT REFERENCES artifacts(id),
  oracle_source TEXT NOT NULL, is_regression INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS verification_runs (
  id TEXT PRIMARY KEY, recipe_version_id TEXT NOT NULL REFERENCES recipe_versions(id), status TEXT NOT NULL,
  checks_total INTEGER NOT NULL DEFAULT 0, checks_passed INTEGER NOT NULL DEFAULT 0,
  checks_failed INTEGER NOT NULL DEFAULT 0, results_json TEXT NOT NULL DEFAULT '{}',
  started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS execution_runs (
  id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id), recipe_version_id TEXT NOT NULL REFERENCES recipe_versions(id),
  input_artifact_id TEXT NOT NULL REFERENCES artifacts(id), output_artifact_id TEXT, quarantine_artifact_id TEXT,
  file_fingerprint TEXT NOT NULL, schema_fingerprint TEXT, idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL, rows_read INTEGER, rows_written INTEGER, llm_calls INTEGER NOT NULL DEFAULT 0,
  baseline_llm_calls INTEGER NOT NULL DEFAULT 0, duration_ms REAL, checkpoint_step INTEGER NOT NULL DEFAULT 0,
  validation_results_json TEXT NOT NULL DEFAULT '{}', error_code TEXT, error_message TEXT,
  started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS run_checkpoints (
  id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES execution_runs(id), step_number INTEGER NOT NULL,
  artifact_id TEXT, state_json TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(run_id, step_number)
);
CREATE TABLE IF NOT EXISTS repair_proposals (
  id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id), base_version_id TEXT NOT NULL,
  candidate_version_id TEXT NOT NULL, source_run_id TEXT, drift_report_json TEXT NOT NULL,
  operation_diff_json TEXT NOT NULL DEFAULT '[]', verification_run_id TEXT, status TEXT NOT NULL,
  user_decision TEXT, decision_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watched_folders (
  id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id), root_path TEXT NOT NULL,
  input_path TEXT NOT NULL, done_path TEXT NOT NULL, quarantine_path TEXT NOT NULL, reports_path TEXT NOT NULL,
  archive_path TEXT, poll_interval_ms INTEGER NOT NULL DEFAULT 1500, max_file_bytes INTEGER NOT NULL,
  enabled INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger_events (
  id TEXT PRIMARY KEY, automation_id TEXT NOT NULL REFERENCES automations(id), run_id TEXT,
  event_type TEXT NOT NULL, baseline_id TEXT NOT NULL, actual_llm_calls INTEGER NOT NULL DEFAULT 0,
  baseline_llm_calls INTEGER NOT NULL DEFAULT 0, tokens_actual INTEGER, tokens_are_estimated INTEGER NOT NULL DEFAULT 0,
  latency_ms REAL, details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, event_type TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_automation ON execution_runs(automation_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_versions_automation ON recipe_versions(automation_id, version_number);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            connection.executescript(SCHEMA)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(automations)").fetchall()}
            if "input_reference" not in columns:
                connection.execute("ALTER TABLE automations ADD COLUMN input_reference TEXT")
            connection.execute("INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', '1')")
            connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


def json_text(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None
