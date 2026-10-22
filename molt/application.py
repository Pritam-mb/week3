from __future__ import annotations

import hashlib
import json
import shutil
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from .config import MoltConfig
from .core import (
    MoltError,
    check_contract,
    execute_recipe,
    execute_recipe_resumable,
    formula_injection_warnings,
    fingerprint_file,
    load_json,
    operation_diff,
    profile_csv,
    read_csv,
    schema_fingerprint,
    validate_recipe,
    verify_recipe,
    write_csv_atomic,
)
from .db import Database, json_text, new_id, now, row_dict
from .ollama import generate_recipe, load_fixture_recipe
from .ollama import readiness as ollama_readiness
from .anomaly import AnomalyAnalyzer
from .telemetry import Telemetry
from .privacy import safe_profile_context


class MoltService:
    """Application services shared by the CLI, HTTP API, and folder watcher."""

    def __init__(self, config: MoltConfig):
        self.config = config
        self.config.prepare()
        self.db = Database(config.database)
        self.telemetry = Telemetry(config.sentry_dsn)
        self.anomaly = AnomalyAnalyzer(
            config.tabpfn_enabled,
            license_accepted=config.tabpfn_license_accepted,
            model=config.tabpfn_model,
            device=config.tabpfn_device,
            max_rows=config.tabpfn_max_rows,
        )

    def _safe_path(self, path: str | Path, *, must_exist: bool = True) -> Path:
        candidate = Path(path).expanduser().resolve()
        try:
            candidate.relative_to(self.config.workspace)
        except ValueError as exc:
            raise MoltError("FILE_ACCESS_DENIED", "Path is outside the configured Molt workspace.") from exc
        if candidate.is_symlink():
            raise MoltError("FILE_ACCESS_DENIED", "Symlink paths are not allowed.")
        if must_exist and not candidate.is_file():
            raise MoltError("FILE_ACCESS_DENIED", f"File does not exist: {candidate.name}.")
        if candidate.exists() and candidate.stat().st_size > self.config.max_file_bytes:
            raise MoltError("INPUT_LIMIT_EXCEEDED", "File exceeds the configured size limit.")
        return candidate

    def _artifact(self, path: Path, kind: str) -> str:
        relative = path.relative_to(self.config.workspace).as_posix()
        artifact_id = new_id("art")
        fingerprint = fingerprint_file(path) if path.is_file() else None
        size = path.stat().st_size if path.exists() else None
        with self.db.transaction() as connection:
            existing = connection.execute("SELECT id FROM artifacts WHERE root_name = ? AND path = ?", ("workspace", relative)).fetchone()
            if existing:
                return existing["id"]
            connection.execute("INSERT INTO artifacts(id, kind, path, root_name, file_fingerprint, size_bytes, created_at) VALUES(?,?,?,?,?,?,?)", (artifact_id, kind, relative, "workspace", fingerprint, size, now()))
        return artifact_id

    def health(self) -> dict[str, Any]:
        try:
            with closing(self.db.connect()) as connection:
                connection.execute("SELECT 1").fetchone()
            ollama = ollama_readiness(self.config.ollama_base_url, self.config.ollama_model, timeout=min(self.config.ollama_timeout_seconds, 5.0))
            return {"status": "ok", "database": "ok", "workspace": {"path": str(self.config.workspace), "writable": self.config.workspace.is_dir()}, "ollama": ollama | {"configured": bool(self.config.ollama_model)}, "telemetry": self.telemetry.status(), "tabpfn": self.anomaly.readiness(), "config": self.config.as_public_dict(), "version": "0.4.0"}
        except Exception as exc:
            return {"status": "degraded", "database": str(exc), "ollama": {"configured": bool(self.config.ollama_model), "status": "not_checked"}, "telemetry": self.telemetry.status(), "tabpfn": self.anomaly.readiness(), "config": self.config.as_public_dict(), "version": "0.4.0"}

    def public_config(self) -> dict[str, Any]:
        return self.config.as_public_dict() | {"telemetry": self.telemetry.status(), "tabpfn": self.anomaly.readiness()}

    def create_automation(self, name: str, description: str = "", input_reference: str | None = None) -> dict[str, Any]:
        automation_id = new_id("auto")
        timestamp = now()
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO automations(id,name,description,status,input_reference,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (automation_id, name.strip(), description, "DRAFT", input_reference, timestamp, timestamp))
            self._audit(connection, "automation", automation_id, "created", {"name": name})
        return self.get_automation(automation_id)

    def list_automations(self) -> list[dict[str, Any]]:
        with closing(self.db.connect()) as connection:
            rows = connection.execute("SELECT * FROM automations ORDER BY updated_at DESC").fetchall()
        return [self.get_automation(row["id"]) for row in rows]

    def get_automation(self, automation_id: str) -> dict[str, Any]:
        with closing(self.db.connect()) as connection:
            automation = row_dict(connection.execute("SELECT * FROM automations WHERE id = ?", (automation_id,)).fetchone())
            if not automation:
                raise MoltError("NOT_FOUND", "Automation was not found.")
            versions = [dict(row) for row in connection.execute("SELECT * FROM recipe_versions WHERE automation_id = ? ORDER BY version_number DESC", (automation_id,)).fetchall()]
            runs = [dict(row) for row in connection.execute("SELECT * FROM execution_runs WHERE automation_id = ? ORDER BY started_at DESC LIMIT 20", (automation_id,)).fetchall()]
            repairs = [dict(row) for row in connection.execute("SELECT * FROM repair_proposals WHERE automation_id = ? ORDER BY created_at DESC", (automation_id,)).fetchall()]
            for version in versions:
                version["recipe"] = json.loads(version.pop("recipe_json"))
                version["provider_metadata"] = json.loads(version.pop("provider_metadata_json"))
            automation["versions"] = versions
            automation["runs"] = runs
            automation["repair_proposals"] = repairs
            automation["active_version"] = next((version for version in versions if version["id"] == automation.get("active_version_id")), None)
            automation["candidate"] = next((version for version in versions if version["status"] in {"AWAITING_APPROVAL", "VERIFYING", "DRAFT"}), None)
            return automation

    def profile(self, path: str | Path) -> dict[str, Any]:
        safe = self._safe_path(path)
        with self.telemetry.span("automation.profile_csv", input_bytes=safe.stat().st_size):
            profile = profile_csv(safe)
        profile["file_fingerprint"] = fingerprint_file(safe)
        profile["schema_fingerprint"] = schema_fingerprint(profile["columns"])
        profile["size_bytes"] = safe.stat().st_size
        return profile

    def anomaly_analysis(
        self,
        path: str | Path,
        *,
        label_column: str | None = None,
        anomaly_label: str | None = None,
        feature_columns: list[str] | None = None,
        test_fraction: float = 0.25,
    ) -> dict[str, Any]:
        safe = self._safe_path(path)
        with self.telemetry.span("tabpfn.score_rows", input_bytes=safe.stat().st_size, available=self.anomaly.available):
            return self.anomaly.analyze(
                safe,
                label_column=label_column,
                anomaly_label=anomaly_label,
                feature_columns=feature_columns,
                test_fraction=test_fraction,
            )

    def create_version(self, automation_id: str, recipe: dict[str, Any], *, created_from: str = "initial", model_name: str | None = None, metadata: dict[str, Any] | None = None, base_version_id: str | None = None) -> dict[str, Any]:
        operation_count = len(recipe.get("operations", [])) if isinstance(recipe, dict) and isinstance(recipe.get("operations"), list) else 0
        with self.telemetry.span("recipe.validate_operations", operation_count=operation_count):
            with self.telemetry.span("recipe.validate_schema", operation_count=operation_count):
                validate_recipe(recipe)
        automation = self.get_automation(automation_id)
        version_id = new_id("ver")
        version_number = max((version["version_number"] for version in automation["versions"]), default=0) + 1
        contract_fp = schema_fingerprint(recipe["input_contract"]["required_columns"])
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO recipe_versions(id,automation_id,version_number,recipe_json,schema_fingerprint,created_from,status,base_version_id,model_name,provider_metadata_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (version_id, automation_id, version_number, json_text(recipe), contract_fp, created_from, "DRAFT", base_version_id, model_name, json_text(metadata or {}), now()))
            self._audit(connection, "recipe_version", version_id, "created", {"created_from": created_from, "automation_id": automation_id})
        return self.get_version(version_id)

    def get_version(self, version_id: str) -> dict[str, Any]:
        with closing(self.db.connect()) as connection:
            row = row_dict(connection.execute("SELECT * FROM recipe_versions WHERE id = ?", (version_id,)).fetchone())
        if not row:
            raise MoltError("NOT_FOUND", "Recipe version was not found.")
        row["recipe"] = json.loads(row.pop("recipe_json"))
        row["provider_metadata"] = json.loads(row.pop("provider_metadata_json"))
        return row

    def get_run(self, run_id: str) -> dict[str, Any]:
        with closing(self.db.connect()) as connection:
            run = row_dict(connection.execute("SELECT * FROM execution_runs WHERE id = ?", (run_id,)).fetchone())
            if not run:
                raise MoltError("NOT_FOUND", "Run was not found.")
            run["validation_results"] = json.loads(run.pop("validation_results_json"))
            run["checkpoints"] = [dict(row) for row in connection.execute("SELECT * FROM run_checkpoints WHERE run_id = ? ORDER BY step_number", (run_id,)).fetchall()]
            return run

    def generate_candidate(self, automation_id: str, task: str, profile: dict[str, Any], *, recipe_file: str | None = None, model: str | None = None) -> dict[str, Any]:
        provider = "fixture" if recipe_file else "ollama" if (model or self.config.ollama_model) else "unconfigured"
        with self.telemetry.span("recipe.compile", provider=provider):
            return self._generate_candidate(automation_id, task, profile, recipe_file=recipe_file, model=model)

    def _generate_candidate(self, automation_id: str, task: str, profile: dict[str, Any], *, recipe_file: str | None = None, model: str | None = None) -> dict[str, Any]:
        if recipe_file:
            recipe = load_fixture_recipe(Path(recipe_file))
            metadata = {"provider": "fixture", "llm_calls": 0, "attempts": 1}
        elif model or self.config.ollama_model:
            model = model or self.config.ollama_model
            recipe = None
            metadata = {"provider": "ollama", "llm_calls": 0, "attempts": 0}
            last_error: MoltError | None = None
            for attempt in range(1, self.config.ollama_max_retries + 2):
                try:
                    with self.telemetry.span("recipe.compile_gemma", attempt=attempt):
                        recipe, call_metadata = generate_recipe(model, task, safe_profile_context(profile), endpoint=self.config.ollama_base_url, feedback=str(last_error) if last_error else None, timeout=self.config.ollama_timeout_seconds, max_response_bytes=self.config.ollama_max_response_bytes)
                    metadata.update(call_metadata)
                    metadata["attempts"] = attempt
                    break
                except MoltError as exc:
                    last_error = exc
                    metadata["attempts"] = attempt
            if recipe is None:
                raise last_error or MoltError("MODEL_RESPONSE_INVALID", "Recipe compilation failed after the configured attempts.")
        else:
            raise MoltError("MODEL_REQUIRED", "Choose a fixture recipe or a local Ollama model.")
        version = self.create_version(automation_id, recipe, model_name=model, metadata=metadata)
        with self.db.transaction() as connection:
            connection.execute("UPDATE recipe_versions SET status = 'VERIFYING' WHERE id = ?", (version["id"],))
        return self.get_version(version["id"])

    def _fixture_pairs(self, automation_id: str) -> list[tuple[Path, Path]]:
        root = Path(__file__).resolve().parent.parent / "examples"
        automation = self.get_automation(automation_id)
        recipe = (automation.get("candidate") or automation.get("active_version") or {}).get("recipe", {})
        defaults = [(root / "orders_input.csv", root / "orders_expected.csv")] if str(recipe.get("name", "")).startswith("normalize_weekly_orders") else [(root / "input" / "golden.csv", root / "expected" / "golden.csv"), (root / "input" / "heldout.csv", root / "expected" / "heldout.csv")]
        with closing(self.db.connect()) as connection:
            stored = connection.execute("SELECT input_artifact_id, expected_artifact_id FROM test_fixtures WHERE automation_id = ? AND expected_artifact_id IS NOT NULL ORDER BY created_at", (automation_id,)).fetchall()
            paths = []
            for row in stored:
                input_row = connection.execute("SELECT path FROM artifacts WHERE id = ?", (row["input_artifact_id"],)).fetchone()
                expected_row = connection.execute("SELECT path FROM artifacts WHERE id = ?", (row["expected_artifact_id"],)).fetchone()
                if input_row and expected_row:
                    paths.append((self.config.workspace / input_row["path"], self.config.workspace / expected_row["path"]))
        return paths or defaults

    def add_fixture(self, automation_id: str, input_path: str | Path, expected_path: str | Path, *, name: str, oracle_source: str = "human_authored") -> dict[str, Any]:
        if oracle_source not in {"human_authored", "human_reviewed", "documented_source"}:
            raise MoltError("INVALID_FIXTURE", "Fixture oracle_source is not allowed.")
        input_file = self._safe_path(input_path)
        expected_file = self._safe_path(expected_path)
        input_artifact = self._artifact(input_file, "fixture_input")
        expected_artifact = self._artifact(expected_file, "fixture_expected")
        fixture_id = new_id("fixture")
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO test_fixtures(id,automation_id,name,input_artifact_id,expected_artifact_id,oracle_source,is_regression,created_at) VALUES(?,?,?,?,?,?,?,?)", (fixture_id, automation_id, name, input_artifact, expected_artifact, oracle_source, 1, now()))
        return {"id": fixture_id, "name": name, "oracle_source": oracle_source, "input": str(input_file), "expected": str(expected_file)}

    def verify_version(self, version_id: str, fixtures: list[tuple[Path, Path]] | None = None) -> dict[str, Any]:
        version = self.get_version(version_id)
        with self.telemetry.span("recipe.verify_examples", checks="regression") as verification_event:
            result = verify_recipe(version["recipe"], fixtures or self._fixture_pairs(version["automation_id"]))
            self.telemetry.annotate(verification_event, checks_total=result["checks_total"], checks_passed=result["checks_passed"], checks_failed=result["checks_failed"], status=result["status"])
        with self.telemetry.span("recipe.verify_invariants", checks_total=result["checks_total"], checks_passed=result["checks_passed"], checks_failed=result["checks_failed"], status=result["status"]):
            pass
        verification_id = new_id("verify")
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO verification_runs(id,recipe_version_id,status,checks_total,checks_passed,checks_failed,results_json,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?)", (verification_id, version_id, result["status"], result["checks_total"], result["checks_passed"], result["checks_failed"], json_text(result), now(), now()))
            new_status = "AWAITING_APPROVAL" if result["status"] == "PASS" else "REJECTED"
            connection.execute("UPDATE recipe_versions SET status = ? WHERE id = ?", (new_status, version_id))
            self._audit(connection, "recipe_version", version_id, "verified", {"verification_id": verification_id, "status": result["status"]})
        result["verification_id"] = verification_id
        return result

    def approve_version(self, version_id: str) -> dict[str, Any]:
        with self.telemetry.span("recipe.approve_version", recipe_version=version_id):
            return self._approve_version(version_id)

    def _approve_version(self, version_id: str) -> dict[str, Any]:
        version = self.get_version(version_id)
        with self.db.transaction() as connection:
            latest = connection.execute("SELECT * FROM verification_runs WHERE recipe_version_id = ? ORDER BY started_at DESC LIMIT 1", (version_id,)).fetchone()
            if not latest or latest["status"] != "PASS":
                raise MoltError("APPROVAL_REQUIRED", "Recipe cannot be approved without passing verification.")
            connection.execute("UPDATE recipe_versions SET status = 'ARCHIVED' WHERE automation_id = ? AND status = 'ACTIVE'", (version["automation_id"],))
            connection.execute("UPDATE recipe_versions SET status = 'ACTIVE', approved_at = ? WHERE id = ?", (now(), version_id))
            connection.execute("UPDATE automations SET active_version_id = ?, status = 'ACTIVE', updated_at = ? WHERE id = ?", (version_id, now(), version["automation_id"]))
            self._audit(connection, "recipe_version", version_id, "approved", {"automation_id": version["automation_id"]})
        return self.get_version(version_id)

    def reject_version(self, version_id: str) -> dict[str, Any]:
        version = self.get_version(version_id)
        with self.db.transaction() as connection:
            connection.execute("UPDATE recipe_versions SET status = 'REJECTED' WHERE id = ? AND status != 'ACTIVE'", (version_id,))
            self._audit(connection, "recipe_version", version_id, "rejected", {"automation_id": version["automation_id"]})
        return self.get_version(version_id)

    def rollback(self, automation_id: str, version_id: str) -> dict[str, Any]:
        target = self.get_version(version_id)
        if target["automation_id"] != automation_id or target["status"] == "REJECTED":
            raise MoltError("INVALID_ROLLBACK", "Version is not available for this automation.")
        with self.db.transaction() as connection:
            connection.execute("UPDATE recipe_versions SET status = 'ARCHIVED' WHERE automation_id = ? AND status = 'ACTIVE'", (automation_id,))
            connection.execute("UPDATE recipe_versions SET status = 'ACTIVE', approved_at = COALESCE(approved_at, ?) WHERE id = ?", (now(), version_id))
            connection.execute("UPDATE automations SET active_version_id = ?, status = 'ACTIVE', updated_at = ? WHERE id = ?", (version_id, now(), automation_id))
            self._audit(connection, "automation", automation_id, "rolled_back", {"active_version_id": version_id})
        return self.get_automation(automation_id)

    def propose_repair(self, automation_id: str, run_id: str | None = None, *, model: str | None = None, recipe_file: str | None = None) -> dict[str, Any]:
        provider = "fixture" if recipe_file else "ollama" if model else "manual-review"
        with self.telemetry.span("repair.propose", provider=provider, has_run=bool(run_id)):
            return self._propose_repair(automation_id, run_id, model=model, recipe_file=recipe_file)

    def _propose_repair(self, automation_id: str, run_id: str | None = None, *, model: str | None = None, recipe_file: str | None = None) -> dict[str, Any]:
        automation = self.get_automation(automation_id)
        active = automation.get("active_version")
        if not active:
            raise MoltError("APPROVAL_REQUIRED", "Automation has no active recipe to repair.")
        if run_id:
            run = self.get_run(run_id)
            drift = {"run_id": run_id, "error_code": run.get("error_code"), "error_message": run.get("error_message"), "input": run.get("input")}
            profile = self.profile(run["input"]) if run.get("input") and Path(run["input"]).is_file() else {}
        else:
            drift, profile = {"reason": "user_requested_repair"}, {}
        if recipe_file:
            candidate = load_fixture_recipe(Path(recipe_file))
            metadata = {"provider": "fixture", "llm_calls": 0}
        elif model:
            candidate = None
            metadata = {"provider": "ollama", "llm_calls": 0, "attempts": 0}
            last_error: MoltError | None = None
            for attempt in range(1, self.config.ollama_max_retries + 2):
                try:
                    with self.telemetry.span("repair.propose_gemma", attempt=attempt):
                        candidate, call_metadata = generate_recipe(model, "Repair the active recipe using this drift report", profile, endpoint=self.config.ollama_base_url, active_recipe=active["recipe"], drift_report=drift, feedback=str(last_error) if last_error else None, timeout=self.config.ollama_timeout_seconds, max_response_bytes=self.config.ollama_max_response_bytes)
                    metadata.update(call_metadata)
                    metadata["attempts"] = attempt
                    break
                except MoltError as exc:
                    last_error = exc
                    metadata["attempts"] = attempt
            if candidate is None:
                raise last_error or MoltError("MODEL_RESPONSE_INVALID", "Repair proposal failed after the configured attempts.")
        else:
            candidate = active["recipe"]
            metadata = {"provider": "manual-review", "llm_calls": 0, "note": "Candidate copied for local review; supply a model for a generated repair."}
        candidate_version = self.create_version(automation_id, candidate, created_from="repair", model_name=model, metadata=metadata, base_version_id=active["id"])
        proposal_id = new_id("repair")
        with self.db.transaction() as connection:
            connection.execute("INSERT INTO repair_proposals(id,automation_id,base_version_id,candidate_version_id,source_run_id,drift_report_json,operation_diff_json,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)", (proposal_id, automation_id, active["id"], candidate_version["id"], run_id, json_text(drift), json_text(operation_diff(active["recipe"], candidate)), "PROPOSED", now()))
            self._audit(connection, "repair_proposal", proposal_id, "proposed", {"base_version_id": active["id"], "candidate_version_id": candidate_version["id"]})
        return self.get_repair(proposal_id)

    def get_repair(self, proposal_id: str) -> dict[str, Any]:
        with closing(self.db.connect()) as connection:
            proposal = row_dict(connection.execute("SELECT * FROM repair_proposals WHERE id = ?", (proposal_id,)).fetchone())
        if not proposal:
            raise MoltError("NOT_FOUND", "Repair proposal was not found.")
        proposal["drift_report"] = json.loads(proposal.pop("drift_report_json"))
        proposal["operation_diff"] = json.loads(proposal.pop("operation_diff_json"))
        proposal["candidate"] = self.get_version(proposal["candidate_version_id"])
        return proposal

    def verify_repair(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_repair(proposal_id)
        with self.telemetry.span("repair.run_regression_suite", recipe_version=proposal["candidate_version_id"]):
            result = self.verify_version(proposal["candidate_version_id"])
        with self.db.transaction() as connection:
            connection.execute("UPDATE repair_proposals SET verification_run_id = ?, status = ? WHERE id = ?", (result["verification_id"], "VERIFIED" if result["status"] == "PASS" else "REJECTED", proposal_id))
        return self.get_repair(proposal_id)

    def approve_repair(self, proposal_id: str) -> dict[str, Any]:
        proposal = self.get_repair(proposal_id)
        if proposal["status"] != "VERIFIED":
            raise MoltError("APPROVAL_REQUIRED", "Repair must pass verification before approval.")
        active = self.get_automation(proposal["automation_id"])["active_version"]
        if not active or active["id"] != proposal["base_version_id"]:
            raise MoltError("STALE_REPAIR", "Repair is based on an older active recipe.")
        self.approve_version(proposal["candidate_version_id"])
        with self.db.transaction() as connection:
            connection.execute("UPDATE repair_proposals SET status = 'APPROVED', user_decision = 'approved', decision_at = ? WHERE id = ?", (now(), proposal_id))
        return self.get_repair(proposal_id)

    def reject_repair(self, proposal_id: str) -> dict[str, Any]:
        with self.db.transaction() as connection:
            connection.execute("UPDATE repair_proposals SET status = 'REJECTED', user_decision = 'rejected', decision_at = ? WHERE id = ?", (now(), proposal_id))
        return self.get_repair(proposal_id)

    def run(self, automation_id: str, input_path: str | Path, *, output_path: str | Path | None = None, baseline_calls: int = 1, use_checkpoints: bool = False) -> dict[str, Any]:
        automation = self.get_automation(automation_id)
        active = automation.get("active_version")
        if not active:
            raise MoltError("APPROVAL_REQUIRED", "Automation has no active recipe.")
        source = self._safe_path(input_path)
        output = Path(output_path).resolve() if output_path else (self.config.done_dir / f"{source.stem}-{fingerprint_file(source)}.csv")
        try:
            output.relative_to(self.config.workspace)
        except ValueError as exc:
            raise MoltError("FILE_ACCESS_DENIED", "Output is outside the configured workspace.") from exc
        run_id = new_id("run")
        file_fp = fingerprint_file(source)
        idempotency_key = f"{automation_id}:{active['id']}:{file_fp}"
        checkpoint_dir = self.config.checkpoints_dir / hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:24] if use_checkpoints else None
        with closing(self.db.connect()) as connection:
            existing = connection.execute("SELECT id, status FROM execution_runs WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if existing:
            raise MoltError("DUPLICATE_FILE_EVENT", f"File was already recorded as run {existing['id']}.", details={"run_id": existing["id"], "status": existing["status"]})
        checkpoint_done = bool(checkpoint_dir and (checkpoint_dir / "state.json").exists() and json.loads((checkpoint_dir / "state.json").read_text(encoding="utf-8")).get("status") == "done")
        if output.exists() and not checkpoint_done:
            raise MoltError("OUTPUT_WRITE_FAILED", "Output already exists; overwrite is disabled.")
        input_artifact = self._artifact(source, "input")
        started = time.perf_counter()
        record: dict[str, Any]
        headers: list[str] = []
        rows: list[dict[str, str]] = []
        actual_rows: list[dict[str, str]] = []
        formula_warnings: list[dict[str, Any]] = []
        error_details: dict[str, Any] = {}
        try:
            with self.telemetry.span("automation.check_drift", recipe_version=active["id"]) as drift_event:
                headers, rows = read_csv(source)
                check_contract(active["recipe"], headers)
                self.telemetry.annotate(drift_event, input_rows=len(rows), column_count=len(headers), drift_category="compatible")
            if len(rows) > self.config.max_rows:
                raise MoltError("INPUT_LIMIT_EXCEEDED", "CSV exceeds the configured row limit.")
            with self.telemetry.span("automation.execute_approved_recipe", operation_count=len(active["recipe"].get("operations", [])), input_rows=len(rows), column_count=len(headers)) as execution_event:
                if checkpoint_dir is not None:
                    actual_headers, actual_rows, _ = execute_recipe_resumable(active["recipe"], headers, rows, checkpoint_dir, resume=checkpoint_done)
                else:
                    actual_headers, actual_rows = execute_recipe(active["recipe"], headers, rows)
                self.telemetry.annotate(execution_event, output_rows=len(actual_rows))
            if time.perf_counter() - started > self.config.max_execution_seconds:
                raise MoltError("EXECUTION_TIMEOUT", "Execution exceeded the configured time limit.")
            formula_warnings = formula_injection_warnings(actual_rows)
            write_csv_atomic(output, actual_headers, actual_rows)
            status = "SUCCEEDED"
            error_code = None
            error_message = None
            output_artifact = self._artifact(output, "output")
        except MoltError as exc:
            error_details = exc.details
            status, error_code, error_message, actual_rows, output_artifact = ("BLOCKED_DRIFT" if exc.code in {"REQUIRED_COLUMN_MISSING", "UNMAPPED_VALUE", "INPUT_TYPE_MISMATCH", "INVARIANT_FAILED"} else "FAILED", exc.code, exc.message, [], None)
            quarantine = self.config.quarantine_dir / f"{source.stem}-{run_id}{source.suffix}"
            shutil.copy2(source, quarantine)
            quarantine_artifact = self._artifact(quarantine, "quarantine")
        else:
            quarantine_artifact = None
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record = {"id": run_id, "run_id": run_id, "automation_id": automation_id, "recipe_version_id": active["id"], "input": str(source), "output": str(output) if status == "SUCCEEDED" else None, "status": status, "file_fingerprint": file_fp, "rows_read": len(rows), "rows_written": len(actual_rows), "llm_calls": 0, "baseline_llm_calls": baseline_calls, "duration_ms": duration_ms, "error_code": error_code, "error_message": error_message, "error_details": error_details, "warnings": formula_warnings if status == "SUCCEEDED" else []}
        with self.db.transaction() as connection:
            try:
                connection.execute("INSERT INTO execution_runs(id,automation_id,recipe_version_id,input_artifact_id,output_artifact_id,quarantine_artifact_id,file_fingerprint,schema_fingerprint,idempotency_key,status,rows_read,rows_written,llm_calls,baseline_llm_calls,duration_ms,error_code,error_message,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, automation_id, active["id"], input_artifact, output_artifact, quarantine_artifact, file_fp, schema_fingerprint(headers) if 'headers' in locals() else None, idempotency_key, status, record["rows_read"], record["rows_written"], 0, baseline_calls, duration_ms, error_code, error_message, now(), now()))
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    raise MoltError("DUPLICATE_FILE_EVENT", "This file fingerprint was already processed by this recipe.") from exc
                raise
            connection.execute("INSERT INTO ledger_events(id,automation_id,run_id,event_type,baseline_id,actual_llm_calls,baseline_llm_calls,latency_ms,details_json,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (new_id("ledger"), automation_id, run_id, "execution", "one_call_per_file", 0, baseline_calls, duration_ms, json_text({"status": status}), now()))
            self._audit(connection, "execution_run", run_id, "completed", {"status": status, "error_code": error_code})
        report_path = self.config.reports_dir / f"{run_id}.json"
        report_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record

    def metrics(self) -> dict[str, Any]:
        with closing(self.db.connect()) as connection:
            counts = connection.execute("SELECT COUNT(*) AS total_runs, SUM(CASE WHEN status='SUCCEEDED' THEN 1 ELSE 0 END) AS successful_runs, SUM(CASE WHEN status IN ('BLOCKED_DRIFT','QUARANTINED') THEN 1 ELSE 0 END) AS quarantined, SUM(llm_calls) AS actual_llm_calls, SUM(baseline_llm_calls) AS baseline_llm_calls, AVG(duration_ms) AS mean_duration_ms FROM execution_runs").fetchone()
            active = connection.execute("SELECT COUNT(*) AS value FROM recipe_versions WHERE status='ACTIVE'").fetchone()["value"]
            pending = connection.execute("SELECT COUNT(*) AS value FROM recipe_versions WHERE status='AWAITING_APPROVAL'").fetchone()["value"]
        values = dict(counts)
        values.update({"active_recipes": active, "pending_repairs": pending, "calls_avoided": (values.get("baseline_llm_calls") or 0) - (values.get("actual_llm_calls") or 0), "duration_sample_size": values.get("total_runs") or 0})
        return {key: (round(value, 2) if isinstance(value, float) else value or 0) for key, value in values.items()}

    def configure_watched_folder(self, automation_id: str, *, enabled: bool = False, poll_interval_ms: int = 1500, max_file_bytes: int | None = None) -> dict[str, Any]:
        self.get_automation(automation_id)
        folder_id = new_id("watch")
        timestamp = now()
        with self.db.transaction() as connection:
            existing = connection.execute("SELECT id FROM watched_folders WHERE automation_id = ?", (automation_id,)).fetchone()
            if existing:
                folder_id = existing["id"]
                connection.execute("UPDATE watched_folders SET enabled = ?, poll_interval_ms = ?, max_file_bytes = ?, updated_at = ? WHERE id = ?", (int(enabled), poll_interval_ms, max_file_bytes or self.config.max_file_bytes, timestamp, folder_id))
            else:
                connection.execute("INSERT INTO watched_folders(id,automation_id,root_path,input_path,done_path,quarantine_path,reports_path,archive_path,poll_interval_ms,max_file_bytes,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (folder_id, automation_id, str(self.config.workspace), str(self.config.input_dir), str(self.config.done_dir), str(self.config.quarantine_dir), str(self.config.reports_dir), str(self.config.archive_dir), poll_interval_ms, max_file_bytes or self.config.max_file_bytes, int(enabled), timestamp, timestamp))
        with closing(self.db.connect()) as connection:
            row = row_dict(connection.execute("SELECT * FROM watched_folders WHERE id = ?", (folder_id,)).fetchone())
        return row or {}

    def list_watched_folders(self) -> list[dict[str, Any]]:
        with closing(self.db.connect()) as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM watched_folders ORDER BY created_at").fetchall()]

    def _audit(self, connection: Any, entity_type: str, entity_id: str, event_type: str, details: dict[str, Any]) -> None:
        connection.execute("INSERT INTO audit_events(id,entity_type,entity_id,event_type,details_json,created_at) VALUES(?,?,?,?,?,?)", (new_id("audit"), entity_type, entity_id, event_type, json_text(details), now()))
