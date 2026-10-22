from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from molt.application import MoltService
from molt.config import MoltConfig
from molt.http_api import MoltHandler
from http.server import ThreadingHTTPServer


class HTTPTests(unittest.TestCase):
    def test_health_metrics_dashboard_and_create_automation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            handler = type("TestMoltHandler", (MoltHandler,), {"service": service})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("GET", "/api/health")
                health = json.loads(connection.getresponse().read())
                self.assertEqual(health["status"], "ok")
                connection.request("POST", "/api/automations", body=json.dumps({"name": "HTTP workflow"}), headers={"Content-Type": "application/json"})
                created = json.loads(connection.getresponse().read())
                self.assertEqual(created["name"], "HTTP workflow")
                connection.request("GET", "/")
                self.assertEqual(connection.getresponse().status, 200)
            finally:
                connection.close()
                server.shutdown()
                server.server_close()

    def test_csv_upload_profile_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            handler = type("TestMoltHandler", (MoltHandler,), {"service": service})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            boundary = "----molt-test-boundary"
            csv_body = b"transaction_id,date,merchant,amount,category\nt-1,2026-01-01,Shop,1.00,Food\n"
            body = b"--" + boundary.encode() + b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"input.csv\"\r\nContent-Type: text/csv\r\n\r\n" + csv_body + b"\r\n--" + boundary.encode() + b"--\r\n"
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request("POST", "/api/files/profile", body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))})
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 201)
                self.assertEqual(payload["profile"]["row_count"], 1)
            finally:
                connection.close()
                server.shutdown()
                server.server_close()

    def test_profile_compile_preview_verify_approve_and_run_routes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = MoltService(MoltConfig(Path(directory)))
            input_path = Path(directory) / "orders.csv"
            input_path.write_bytes((Path(__file__).resolve().parents[1] / "examples/orders_input.csv").read_bytes())
            handler = type("TestMoltHandler", (MoltHandler,), {"service": service})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=10)
            try:
                def post(path: str, value: dict) -> tuple[int, dict]:
                    connection.request("POST", path, body=json.dumps(value), headers={"Content-Type": "application/json"})
                    response = connection.getresponse()
                    return response.status, json.loads(response.read())

                status, automation = post("/api/automations", {"name": "Orders API", "description": "Normalize orders", "input_reference": str(input_path)})
                self.assertEqual(status, 201)
                automation_id = automation["id"]
                status, profile = post(f"/api/automations/{automation_id}/profile", {"input_reference": str(input_path)})
                self.assertEqual(status, 200)
                status, candidate = post(f"/api/automations/{automation_id}/compile", {"path": str(input_path), "description": "Normalize orders", "recipe_file": str(Path(__file__).resolve().parents[1] / "examples/recipes/orders-v1.json")})
                self.assertEqual(status, 201)
                version_id = candidate["id"]
                status, preview = post(f"/api/automations/{automation_id}/preview", {"path": str(input_path)})
                self.assertEqual(status, 200)
                self.assertEqual(preview["rows_out"], 3)
                status, verification = post(f"/api/recipes/{version_id}/verify", {})
                self.assertEqual(status, 200)
                self.assertEqual(verification["status"], "PASS")
                status, active = post(f"/api/recipes/{version_id}/approve", {})
                self.assertEqual(status, 200)
                self.assertEqual(active["status"], "ACTIVE")
                status, run = post(f"/api/automations/{automation_id}/runs", {"path": str(input_path)})
                self.assertEqual(status, 201)
                self.assertEqual(run["status"], "SUCCEEDED")
            finally:
                connection.close()
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
