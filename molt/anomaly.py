from __future__ import annotations

import importlib
import importlib.metadata
import random
import re
from pathlib import Path
from typing import Any, Callable

from .core import MoltError, read_csv
from .privacy import is_sensitive_field, redact_sample


_IDENTIFIER_NAME = re.compile(r"(^|[_-])(id|uuid|identifier|key)$|(^|[_-])(account|customer|order)[_-]?(id|number|no)?$", re.I)
_MIN_ROWS = 10
_MIN_TRAIN_ROWS_PER_CLASS = 2
_DEFAULT_TEST_FRACTION = 0.25


def _default_package_loader() -> Any:
    return importlib.import_module("tabpfn")


class AnomalyAnalyzer:
    """Optional, advisory TabPFN boundary.

    TabPFN's supported core API is supervised classification/regression, not
    unlabeled anomaly detection.  Molt only runs the supported binary
    classification interface when the caller supplies an explicit target
    column and anomaly label.  The result is a holdout triage signal; it is
    never used by the deterministic workflow to change a CSV.
    """

    def __init__(
        self,
        enabled: bool = False,
        *,
        license_accepted: bool = False,
        model: str = "default",
        device: str = "auto",
        max_rows: int = 5_000,
        package_loader: Callable[[], Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self.license_accepted = license_accepted
        self.model = model
        self.device = device
        self.max_rows = max_rows
        self._package_loader = package_loader or _default_package_loader
        self.package: Any | None = None
        self.package_version: str | None = None
        self.package_error: str | None = None
        self._inspect_package()

    def _inspect_package(self) -> None:
        if not self.enabled:
            return
        try:
            self.package = self._package_loader()
            self.package_version = getattr(self.package, "__version__", None)
            if not self.package_version:
                try:
                    self.package_version = importlib.metadata.version("tabpfn")
                except importlib.metadata.PackageNotFoundError:
                    self.package_version = "unknown"
        except Exception as exc:  # optional dependencies must not break Molt
            self.package_error = type(exc).__name__

    @property
    def api_supported(self) -> bool:
        classifier = getattr(self.package, "TabPFNClassifier", None)
        return callable(classifier) and callable(getattr(classifier, "fit", None)) and callable(getattr(classifier, "predict_proba", None))

    @property
    def available(self) -> bool:
        """Compatibility summary: package import succeeded, not license/readiness."""
        return self.package is not None

    @property
    def reason(self) -> str:
        return str(self.readiness()["reason"])

    def readiness(self) -> dict[str, Any]:
        """Return separate package/config/license/API/readiness states."""
        package_state = "disabled" if not self.enabled else ("present" if self.package is not None else "missing")
        if not self.enabled:
            readiness = "disabled"
            reason = "TabPFN is disabled by configuration; Molt's core workflow is available."
        elif self.package is None:
            readiness = "unavailable"
            reason = "TabPFN is enabled but the optional package could not be imported."
        elif not self.api_supported:
            readiness = "unsupported_api"
            reason = "The installed TabPFN package does not expose the supported classifier API required by Molt."
        elif not self.license_accepted:
            readiness = "license_not_confirmed"
            reason = "TabPFN model-weight license/access has not been explicitly acknowledged in Molt configuration."
        else:
            readiness = "ready_for_supervised_triage"
            reason = "Supported binary classification API detected; an explicit target column is still required."
        return {
            "enabled": self.enabled,
            "package": {
                "state": package_state,
                "version": self.package_version,
                "import_error": self.package_error,
            },
            "config": {
                "state": "enabled" if self.enabled else "disabled",
                "mode": "local",
                "model": self.model,
                "device": self.device,
                "max_rows": self.max_rows,
            },
            "license": {
                "state": "acknowledged" if self.license_accepted else "not_confirmed",
                "note": "Package code and model weights may have different license terms; verify the selected weights before use.",
            },
            "api": {
                "state": "supported" if self.api_supported else "unsupported",
                "supported_task": "supervised_binary_classification" if self.api_supported else None,
                "unlabeled_anomaly_detection": "not_supported_by_core_api",
            },
            "readiness": readiness,
            "reason": reason,
        }

    def _base_result(self, csv_path: Path) -> dict[str, Any]:
        return {
            "input": csv_path.name,
            "advisory_only": True,
            "rows_changed": 0,
            "source_preserved": True,
            "flagged_rows": [],
            "warning": "Unusual does not mean invalid. Anomaly analysis never deletes, rewrites, or quarantines rows.",
            "readiness": self.readiness(),
        }

    def _not_eligible(self, result: dict[str, Any], reason: str, *, code: str = "TABPFN_INELIGIBLE", status: str = "INELIGIBLE") -> dict[str, Any]:
        result.update({"status": status, "eligible": False, "code": code, "reason": reason})
        return result

    @staticmethod
    def public_result(result: dict[str, Any]) -> dict[str, Any]:
        """Return an aggregate-only API response for dashboard consumers.

        The internal analyzer retains redacted flagged-row details for local
        callers and tests. The HTTP boundary never exposes those payloads.
        """
        allowed = {
            "status", "code", "eligible", "advisory_only", "rows_changed",
            "source_preserved", "warning", "readiness", "reason", "error_type",
            "method", "target", "features", "split", "threshold", "rows_scored",
            "rows_flagged", "holdout_metrics", "limitations",
        }
        return {key: result[key] for key in allowed if key in result}

    @staticmethod
    def _numeric_columns(headers: list[str], rows: list[dict[str, str]], excluded: set[str]) -> list[str]:
        columns: list[str] = []
        for column in headers:
            if column in excluded or is_sensitive_field(column) or _IDENTIFIER_NAME.search(column):
                continue
            values = [(row.get(column) or "").strip() for row in rows]
            try:
                if values and all(not value or _as_float(value) is not None for value in values):
                    if any(value for value in values):
                        columns.append(column)
            except (TypeError, ValueError):
                continue
        return columns

    def _features(self, headers: list[str], rows: list[dict[str, str]], target: str, requested: list[str] | None) -> tuple[list[str], str | None]:
        excluded = {target}
        if requested is not None:
            if not isinstance(requested, list) or not all(isinstance(column, str) for column in requested):
                return [], "feature_columns must be a list of column names."
            unknown = [column for column in requested if column not in headers]
            if unknown:
                return [], f"Requested feature column(s) are absent: {', '.join(unknown)}."
            if target in requested:
                return [], "The target column cannot also be used as a feature."
            unsafe = [column for column in requested if is_sensitive_field(column) or _IDENTIFIER_NAME.search(column)]
            if unsafe:
                return [], "Sensitive or identifier columns cannot be used as anomaly features."
            non_numeric = [column for column in requested if not all(not (row.get(column) or "").strip() or _as_float(row.get(column, "")) is not None for row in rows)]
            if non_numeric:
                return [], "Molt's supported TabPFN path currently accepts numeric features only."
            if not any((row.get(column) or "").strip() for column in requested for row in rows):
                return [], "At least one requested feature must contain a numeric value."
            return requested, None
        columns = self._numeric_columns(headers, rows, excluded)
        return columns, None

    def analyze(
        self,
        csv_path: Path,
        *,
        label_column: str | None = None,
        anomaly_label: str | None = None,
        feature_columns: list[str] | None = None,
        test_fraction: float = _DEFAULT_TEST_FRACTION,
    ) -> dict[str, Any]:
        result = self._base_result(csv_path)
        if not self.enabled:
            return self._not_eligible(result, "TabPFN is disabled by configuration.", code="TABPFN_DISABLED", status="UNAVAILABLE")
        if self.package is None:
            return self._not_eligible(result, "TabPFN is not installed or could not be imported.", code="TABPFN_UNAVAILABLE", status="UNAVAILABLE")
        if not self.api_supported:
            return self._not_eligible(result, "The installed package does not support the classifier API used by this integration.", code="TABPFN_UNSUPPORTED_API", status="UNAVAILABLE")
        if not self.license_accepted:
            return self._not_eligible(result, "Explicit TabPFN model-license/access acknowledgment is required before local inference.", code="TABPFN_LICENSE_NOT_CONFIRMED", status="NOT_READY")
        if label_column is None:
            return self._not_eligible(result, "The installed core TabPFN API supports supervised classification, not unlabeled anomaly detection. Supply label_column and anomaly_label for supervised triage.", code="TABPFN_UNSUPPORTED_TASK", status="UNSUPPORTED_TASK")
        if anomaly_label is None:
            return self._not_eligible(result, "anomaly_label is required; Molt will not invent a target or anomaly class.", code="TABPFN_TARGET_REQUIRED")
        if not isinstance(label_column, str) or not isinstance(anomaly_label, str):
            return self._not_eligible(result, "label_column and anomaly_label must be strings.", code="TABPFN_TARGET_REQUIRED")
        label_column = label_column.strip()
        anomaly_label = anomaly_label.strip()
        if not label_column:
            return self._not_eligible(result, "The installed core TabPFN API supports supervised classification, not unlabeled anomaly detection. Supply label_column and anomaly_label for supervised triage.", code="TABPFN_UNSUPPORTED_TASK", status="UNSUPPORTED_TASK")
        if not anomaly_label:
            return self._not_eligible(result, "anomaly_label is required; Molt will not invent a target or anomaly class.", code="TABPFN_TARGET_REQUIRED")
        if not 0.1 <= test_fraction <= 0.5:
            return self._not_eligible(result, "test_fraction must be between 0.1 and 0.5 for a bounded holdout.")

        try:
            headers, rows = read_csv(csv_path)
        except MoltError as exc:
            return self._not_eligible(result, "CSV could not be read for advisory analysis.", code=exc.code)
        if len(rows) > self.max_rows:
            return self._not_eligible(result, "CSV exceeds the configured TabPFN analysis row limit.", code="TABPFN_INPUT_LIMIT_EXCEEDED")
        if len(rows) < _MIN_ROWS:
            return self._not_eligible(result, f"At least {_MIN_ROWS} rows are required for a supervised holdout.")
        if label_column not in headers:
            return self._not_eligible(result, "The requested label column is not present in the CSV.", code="TABPFN_TARGET_MISSING")

        labels = [(row.get(label_column) or "").strip() for row in rows]
        classes = sorted(set(labels))
        if "" in classes or len(classes) != 2 or anomaly_label not in classes:
            return self._not_eligible(result, "The target must contain exactly two non-empty classes and include anomaly_label.", code="TABPFN_TARGET_NOT_BINARY")
        features, feature_error = self._features(headers, rows, label_column, feature_columns)
        if feature_error:
            return self._not_eligible(result, feature_error, code="TABPFN_FEATURES_INELIGIBLE")
        if not features:
            return self._not_eligible(result, "No approved numeric, non-sensitive feature columns were found.", code="TABPFN_FEATURES_INELIGIBLE")

        by_class = {value: [index for index, label in enumerate(labels) if label == value] for value in classes}
        if any(len(indexes) < _MIN_TRAIN_ROWS_PER_CLASS + 1 for indexes in by_class.values()):
            return self._not_eligible(result, "Each target class needs at least three rows for a train/holdout split.", code="TABPFN_TARGET_TOO_SMALL")
        train_indices: list[int] = []
        test_indices: list[int] = []
        rng = random.Random(0)
        for indexes in by_class.values():
            shuffled = list(indexes)
            rng.shuffle(shuffled)
            test_count = max(1, round(len(shuffled) * test_fraction))
            test_count = min(test_count, len(shuffled) - _MIN_TRAIN_ROWS_PER_CLASS)
            test_indices.extend(shuffled[:test_count])
            train_indices.extend(shuffled[test_count:])
        train_indices.sort()
        test_indices.sort()

        x_values = [[_as_float(row.get(column, "")) for column in features] for row in rows]
        x_train = [x_values[index] for index in train_indices]
        y_train = [labels[index] for index in train_indices]
        x_test = [x_values[index] for index in test_indices]
        try:
            classifier_args: dict[str, Any] = {"device": self.device, "show_progress_bar": False}
            if self.model != "default":
                classifier_args["model_path"] = self.model
            classifier = self.package.TabPFNClassifier(**classifier_args)
            classifier.fit(x_train, y_train)
            probabilities = classifier.predict_proba(x_test)
            fitted_classes = [str(value) for value in classifier.classes_]
            anomaly_index = fitted_classes.index(anomaly_label)
        except Exception as exc:  # inference/configuration failure is advisory only
            result.update({"status": "FAILED", "eligible": True, "code": "TABPFN_ANALYSIS_FAILED", "reason": "TabPFN inference did not complete; no anomaly result was produced.", "error_type": type(exc).__name__})
            return result

        threshold = 0.5
        flagged: list[dict[str, Any]] = []
        confusion = {"true_positives": 0, "false_positives": 0, "true_negatives": 0, "false_negatives": 0}
        redact_target = is_sensitive_field(label_column)
        for position, row_index in enumerate(test_indices):
            score = float(probabilities[position][anomaly_index])
            predicted_positive = score >= threshold
            observed_positive = labels[row_index] == anomaly_label
            if predicted_positive:
                confusion["true_positives" if observed_positive else "false_positives"] += 1
                flagged.append({
                    "row_number": row_index + 2,
                    "score": round(score, 6),
                    "predicted_label": "<REDACTED_COLUMN>" if redact_target else anomaly_label,
                    "observed_label": "<REDACTED_COLUMN>" if redact_target else labels[row_index],
                    "row_redacted": redact_sample(rows[row_index]),
                })
            else:
                confusion["false_negatives" if observed_positive else "true_negatives"] += 1
        tp, fp = confusion["true_positives"], confusion["false_positives"]
        tn, fn = confusion["true_negatives"], confusion["false_negatives"]
        safe_anomaly_label = "<REDACTED_COLUMN>" if redact_target else anomaly_label
        result.update({
            "status": "COMPLETE",
            "eligible": True,
            "code": "TABPFN_ADVISORY_COMPLETE",
            "method": "TabPFN supervised binary classification on a deterministic stratified holdout; rows are flagged when predicted anomaly probability is at least 0.5.",
            "target": {"column": label_column, "anomaly_label": safe_anomaly_label, "classes": ["<REDACTED_COLUMN>"] if redact_target else classes},
            "features": features,
            "split": {"train_rows": len(train_indices), "held_out_rows": len(test_indices), "test_fraction": test_fraction, "random_seed": 0},
            "threshold": threshold,
            "rows_scored": len(test_indices),
            "rows_flagged": len(flagged),
            "flagged_rows": flagged,
            "holdout_metrics": {
                "reference": "supplied held-out labels",
                "confusion_matrix": confusion,
                "precision": tp / (tp + fp) if tp + fp else 0.0,
                "recall": tp / (tp + fn) if tp + fn else 0.0,
                "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
                "accuracy": (tp + tn) / len(test_indices) if test_indices else 0.0,
                "zero_division": 0.0,
            },
            "limitations": [
                "Metrics evaluate only the deterministic holdout against supplied labels; they do not establish real-world anomaly detection quality.",
                "The supplied target is the reference label; unusual does not mean invalid.",
                "The core Molt workflow does not consume these flags.",
            ],
        })
        return result


def _as_float(value: str) -> float | None:
    try:
        return float(value.strip()) if value.strip() else None
    except (AttributeError, TypeError, ValueError):
        return None
