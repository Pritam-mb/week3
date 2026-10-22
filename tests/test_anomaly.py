from __future__ import annotations

import json
import tempfile
import threading
import types
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from molt.anomaly import AnomalyAnalyzer
from molt.application import MoltService
from molt.config import MoltConfig
from molt.http_api import MoltHandler


class FakeTabPFNClassifier:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.classes_: list[str] = []

    def fit(self, x: list[list[float | None]], y: list[str]) -> "FakeTabPFNClassifier":
        self.classes_ = sorted(set(y))
        return self

    def predict_proba(self, x: list[list[float | None]]) -> list[list[float]]:
        # A deterministic stand-in for the supported classifier API. It lets
        # the test prove the Molt boundary without downloading model weights.
        anomaly_index = self.classes_.index("anomaly")
        normal_index = self.classes_.index("normal")
        values: list[list[float]] = []
        for row in x:
            is_large = float(row[0] or 0) >= 100
            probabilities = [0.1, 0.1]
            probabilities[anomaly_index if is_large else normal_index] = 0.9
            probabilities[normal_index if is_large else anomaly_index] = 0.1
            values.append(probabilities)
        return values


def fake_tabpfn() -> types.SimpleNamespace:
    return types.SimpleNamespace(__version__="test-version", TabPFNClassifier=FakeTabPFNClassifier)


class AnomalyAnalyzerTests(unittest.TestCase):
    def test_disabled_optional_package_has_honest_readiness_and_no_analysis(self) -> None:
        analyzer = AnomalyAnalyzer(enabled=False)
        result = analyzer.analyze(Path("not-created.csv"))
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["code"], "TABPFN_DISABLED")
        self.assertEqual(result["readiness"]["package"]["state"], "disabled")
        self.assertEqual(result["readiness"]["license"]["state"], "not_confirmed")

    def test_missing_package_does_not_break_core_or_expose_rows(self) -> None:
        def missing_package() -> object:
            raise ModuleNotFoundError("optional dependency absent")

        analyzer = AnomalyAnalyzer(enabled=True, package_loader=missing_package)
        result = analyzer.analyze(Path("customer-secret.csv"))
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertEqual(result["code"], "TABPFN_UNAVAILABLE")
        self.assertNotIn("customer-secret.csv", result["reason"])
        self.assertEqual(result["flagged_rows"], [])

    def test_unlabeled_csv_is_not_misrepresented_as_anomaly_detection(self) -> None:
        analyzer = AnomalyAnalyzer(enabled=True, license_accepted=True, package_loader=fake_tabpfn)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "values.csv"
            path.write_text("value\n1\n2\n", encoding="utf-8")
            result = analyzer.analyze(path)
        self.assertEqual(result["status"], "UNSUPPORTED_TASK")
        self.assertEqual(result["code"], "TABPFN_UNSUPPORTED_TASK")
        self.assertIn("not unlabeled anomaly detection", result["reason"])

    def test_supported_supervised_triage_is_holdout_redacted_and_non_mutating(self) -> None:
        analyzer = AnomalyAnalyzer(
            enabled=True,
            license_accepted=True,
            package_loader=fake_tabpfn,
            max_rows=100,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "labeled.csv"
            rows = [
                "record_id,email,customer_name,amount,label",
                *[f"r-{index},secret{index}@example.test,Person {index},{index},normal" for index in range(1, 6)],
                *[f"r-{index},secret{index}@example.test,Person {index},{100 + index},anomaly" for index in range(1, 6)],
            ]
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            before = path.read_bytes()
            result = analyzer.analyze(path, label_column="label", anomaly_label="anomaly")
            after = path.read_bytes()

        self.assertEqual(result["status"], "COMPLETE")
        self.assertTrue(result["eligible"])
        self.assertEqual(result["split"]["random_seed"], 0)
        self.assertGreater(result["rows_scored"], 0)
        self.assertGreater(result["rows_flagged"], 0)
        self.assertEqual(result["features"], ["amount"])
        self.assertEqual(before, after)
        self.assertEqual(result["rows_changed"], 0)
        self.assertTrue(result["source_preserved"])
        self.assertTrue(all("secret" not in str(flag) and "Person" not in str(flag) for flag in result["flagged_rows"]))
        self.assertTrue(any(flag["row_redacted"]["email"] == "<REDACTED_COLUMN>" for flag in result["flagged_rows"]))
        self.assertTrue(any(flag["row_redacted"]["customer_name"] == "<REDACTED_COLUMN>" for flag in result["flagged_rows"]))

    def test_service_health_reports_states_without_changing_core_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = MoltConfig(Path(directory), tabpfn_enabled=True)
            service = MoltService(config)
            health = service.health()
        self.assertIn(health["tabpfn"]["readiness"], {"license_not_confirmed", "unsupported_api", "unavailable", "ready_for_supervised_triage"})
        self.assertTrue(health["config"]["local_only"])

    def test_http_anomaly_route_forwards_explicit_supervised_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = MoltConfig(Path(directory))
            service = MoltService(config)
            service.anomaly = AnomalyAnalyzer(enabled=True, license_accepted=True, package_loader=fake_tabpfn)
            path = config.workspace / "labeled.csv"
            path.write_text(
                "amount,label\n" + "\n".join([f"{index},normal" for index in range(1, 6)] + [f"{100 + index},anomaly" for index in range(1, 6)]) + "\n",
                encoding="utf-8",
            )
            handler = type("TestMoltHandler", (MoltHandler,), {"service": service})
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request(
                    "POST",
                    "/api/automations/unused/anomaly-analysis",
                    body=json.dumps({"path": str(path), "label_column": "label", "anomaly_label": "anomaly"}),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                payload = json.loads(response.read())
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "COMPLETE")
        self.assertEqual(payload["advisory_only"], True)


if __name__ == "__main__":
    unittest.main()
