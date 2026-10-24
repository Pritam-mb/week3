from __future__ import annotations

import json
import mimetypes
import cgi
import io
import shutil
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .application import MoltService
from .config import MoltConfig
from .core import MoltError, fingerprint_file
from .db import new_id


WEB_ROOT = Path(__file__).resolve().parent / "web"


class MoltHandler(BaseHTTPRequestHandler):
    service: MoltService

    def _send(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, exc: Exception) -> None:
        if isinstance(exc, MoltError):
            status = 404 if exc.code == "NOT_FOUND" else 400
            self._send({"error": {"code": exc.code, "message": exc.message, "details": exc.details}}, status)
        else:
            self._send({"error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, 500)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise MoltError("REQUEST_TOO_LARGE", "Request exceeds the 1 MB JSON limit.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MoltError("INVALID_JSON", "Request body must be valid JSON.") from exc
        if not isinstance(value, dict):
            raise MoltError("INVALID_JSON", "Request body must be a JSON object.")
        return value

    def _upload_csv(self) -> dict:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise MoltError("INVALID_UPLOAD", "CSV upload must use multipart/form-data.")
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > self.service.config.max_file_bytes:
            raise MoltError("FILE_TOO_LARGE", "Upload is empty or exceeds the configured size limit.")
        raw = self.rfile.read(length)
        fields = cgi.FieldStorage(fp=io.BytesIO(raw), headers=self.headers, environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": str(length)})
        upload = fields["file"] if "file" in fields else None
        if upload is None or not getattr(upload, "file", None):
            raise MoltError("INVALID_UPLOAD", "Multipart field 'file' is required.")
        uploads = self.service.config.workspace / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        target = uploads / f"{new_id('upload')}.csv"
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        try:
            profile = self.service.profile(target)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        return {"artifact_id": self.service._artifact(target, "input"), "path": str(target), "file_fingerprint": fingerprint_file(target), "profile": profile}

    def do_GET(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                return self._send(self.service.health())
            if parsed.path == "/api/metrics":
                return self._send(self.service.metrics())
            if parsed.path == "/api/metrics/ledger":
                return self._send(self.service.metrics())
            if parsed.path == "/api/config":
                return self._send(self.service.public_config())
            if parsed.path == "/api/automations":
                return self._send({"automations": self.service.list_automations()})
            if parsed.path == "/api/watched-folders":
                return self._send({"watched_folders": self.service.list_watched_folders()})
            if parsed.path.startswith("/api/temporal-runs/"):
                workflow_id = unquote(parsed.path.rsplit("/", 1)[-1])
                query = parse_qs(parsed.query)
                from .temporal import describe_workflow
                return self._send(describe_workflow(
                    workflow_id=workflow_id,
                    address=query.get("address", [self.service.config.temporal_address])[0],
                    namespace=query.get("namespace", [self.service.config.temporal_namespace])[0],
                ))
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 3 and parts[:2] == ["api", "automations"]:
                return self._send(self.service.get_automation(parts[2]))
            if len(parts) == 3 and parts[:2] == ["api", "runs"]:
                return self._send(self.service.get_run(parts[2]))
            if len(parts) == 3 and parts[:2] == ["api", "repair-proposals"]:
                return self._send(self.service.get_repair(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "runs":
                automation = self.service.get_automation(parts[2])
                return self._send({"runs": automation["runs"]})
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "versions":
                return self._send({"versions": self.service.get_automation(parts[2])["versions"]})
            if parsed.path == "/" or parsed.path in {"/index.html", "/app.js", "/style.css", "/diff.html", "/diff.js", "/diff.css"}:
                return self._static(parsed.path)
            self._send({"error": {"code": "NOT_FOUND", "message": "Route not found."}}, 404)
        except Exception as exc:
            self._error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/api/files/profile":
                return self._send(self._upload_csv(), 201)
            body = self._body()
            parts = [part for part in parsed.path.split("/") if part]
            if parsed.path == "/api/automations":
                return self._send(self.service.create_automation(body.get("name", "Untitled automation"), body.get("description", ""), body.get("input_reference")), 201)
            if parsed.path == "/api/watched-folders":
                return self._send(self.service.configure_watched_folder(body["automation_id"], enabled=bool(body.get("enabled", False)), poll_interval_ms=int(body.get("poll_interval_ms", 1500)), max_file_bytes=body.get("max_file_bytes")), 201)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "temporal-runs":
                return self._send(self.service.start_temporal_run(
                    parts[2],
                    body.get("path") or body.get("input_reference"),
                    output_path=body.get("output_path") or body.get("output_reference"),
                    workflow_id=body.get("workflow_id"),
                    wait=bool(body.get("wait", True)),
                    activity_timeout_seconds=int(body.get("activity_timeout_seconds", self.service.config.temporal_activity_timeout_seconds)),
                    address=body.get("address"),
                    namespace=body.get("namespace"),
                    task_queue=body.get("task_queue"),
                ), 202)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "profile":
                return self._send(self.service.profile(body.get("path") or body.get("input_reference")))
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "generate-recipe":
                profile = body.get("profile") or self.service.profile(body.get("path") or body.get("input_reference"))
                return self._send(self.service.generate_candidate(parts[2], body.get("task") or body.get("description", ""), profile, recipe_file=body.get("recipe_file"), model=body.get("model")), 201)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "runs":
                return self._send(self.service.run(parts[2], body.get("path") or body.get("input_reference"), output_path=body.get("output_path") or body.get("output_reference") or None), 201)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "repair-proposals":
                return self._send(self.service.propose_repair(parts[2], body.get("run_id") or body.get("source_run_id"), model=body.get("model"), recipe_file=body.get("recipe_file")), 201)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "compile":
                profile = body.get("profile") or self.service.profile(body.get("path") or body.get("input_reference"))
                return self._send(self.service.generate_candidate(parts[2], body.get("task") or body.get("description", ""), profile, recipe_file=body.get("recipe_file"), model=body.get("model")), 201)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "validate":
                from .core import validate_recipe
                validate_recipe(body["recipe"])
                return self._send({"status": "PASS", "recipe": body["recipe"]})
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "preview":
                automation = self.service.get_automation(parts[2])
                active = automation.get("active_version") or automation.get("candidate")
                if not active:
                    raise MoltError("APPROVAL_REQUIRED", "No candidate or active recipe is available for preview.")
                source = body.get("path") or body.get("input_reference")
                profile = self.service.profile(source)
                headers, rows = __import__("molt.core", fromlist=["read_csv"]).read_csv(self.service._safe_path(source))
                from .core import execute_recipe, formula_injection_warnings
                out_headers, out_rows = execute_recipe(active["recipe"], headers, rows)
                return self._send({"status": "PREVIEW", "profile": profile, "output_columns": out_headers, "rows_in": len(rows), "rows_out": len(out_rows), "sample": out_rows[:5], "warnings": formula_injection_warnings(out_rows)})
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "tests":
                return self._send(self.service.add_fixture(parts[2], body["input_path"], body["expected_path"], name=body.get("name", "user-example"), oracle_source=body.get("oracle_source", "human_authored")), 201)
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "anomaly-analysis":
                result = self.service.anomaly_analysis(
                    body.get("path") or body.get("input_reference"),
                    label_column=body.get("label_column"),
                    anomaly_label=body.get("anomaly_label"),
                    feature_columns=body.get("feature_columns"),
                    test_fraction=float(body.get("test_fraction", 0.25)),
                )
                return self._send(self.service.anomaly.public_result(result))
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "approve":
                automation = self.service.get_automation(parts[2])
                candidate = automation.get("candidate")
                if not candidate:
                    raise MoltError("NOT_FOUND", "No candidate recipe is awaiting approval.")
                return self._send(self.service.approve_version(candidate["id"]))
            if len(parts) == 4 and parts[:2] == ["api", "automations"] and parts[3] == "rollback":
                return self._send(self.service.rollback(parts[2], body["version_id"]))
            if len(parts) == 4 and parts[:2] == ["api", "runs"] and parts[3] == "repair":
                run = self.service.get_run(parts[2])
                return self._send(self.service.propose_repair(run["automation_id"], parts[2], model=body.get("model"), recipe_file=body.get("recipe_file")), 201)
            if len(parts) == 4 and parts[:2] == ["api", "recipes"] and parts[3] == "verify":
                return self._send(self.service.verify_version(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "recipes"] and parts[3] == "approve":
                return self._send(self.service.approve_version(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "recipes"] and parts[3] == "reject":
                return self._send(self.service.reject_version(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "repair-proposals"] and parts[3] == "verify":
                return self._send(self.service.verify_repair(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "repair-proposals"] and parts[3] == "approve":
                return self._send(self.service.approve_repair(parts[2]))
            if len(parts) == 4 and parts[:2] == ["api", "repair-proposals"] and parts[3] == "reject":
                return self._send(self.service.reject_repair(parts[2]))
            self._send({"error": {"code": "NOT_FOUND", "message": "Route not found."}}, 404)
        except Exception as exc:
            self._error(exc)

    def _static(self, route: str) -> None:
        filename = "index.html" if route == "/" else route.lstrip("/")
        target = (WEB_ROOT / filename).resolve()
        try:
            target.relative_to(WEB_ROOT)
        except ValueError as exc:
            raise MoltError("FILE_ACCESS_DENIED", "Static path is outside the dashboard root.") from exc
        if not target.is_file():
            self._send({"error": {"code": "NOT_FOUND", "message": "Dashboard asset not found."}}, 404)
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[molt] {format % args}")


def serve(config: MoltConfig, host: str = "127.0.0.1", port: int = 8765) -> None:
    service = MoltService(config)
    handler = type("ConfiguredMoltHandler", (MoltHandler,), {"service": service})
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.5)
        if probe.connect_ex((host, port)) == 0:
            raise MoltError("SERVER_ALREADY_RUNNING", f"A server is already listening on {host}:{port}. Stop it or choose another port.")
    finally:
        probe.close()
    try:
        server = ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise MoltError("SERVER_BIND_FAILED", f"Could not bind {host}:{port}. It may already be in use. Stop the existing server or choose another port.") from exc
    print(f"Molt dashboard: http://{host}:{port}/")
    print(f"Workspace: {config.workspace}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Molt server.")
    finally:
        server.server_close()
