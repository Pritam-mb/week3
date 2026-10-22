from __future__ import annotations

import math
import os
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator


_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,99}$")
_SAFE_LABEL = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")

# Telemetry is deliberately allowlisted. A generic string attribute is never
# forwarded just because it happened to be a scalar.
_SAFE_ATTRIBUTE_KEYS = {
    "attempt", "available", "checks", "checks_failed", "checks_passed", "checks_total",
    "column_count", "configured", "drift_category", "error_class", "error_code",
    "flagged_rows", "has_run", "input_bytes", "input_rows", "model_calls", "operation_count",
    "output_published", "output_rows", "provider", "recipe_version", "row_count",
    "rows_read", "rows_written", "status",
}

_SENSITIVE_KEY_PARTS = (
    "content", "csv", "file", "path", "prompt", "response", "row", "secret", "token", "value",
)
_SAFE_SCRUB_STRING_KEYS = {
    "description", "environment", "event_id", "op", "release", "span_id", "status", "trace_id", "transaction", "type",
}


class Telemetry:
    """Optional Sentry span boundary that cannot affect Molt correctness.

    Only aggregate, allowlisted attributes are accepted. The local ``events``
    list is useful for diagnostics and tests when Sentry is disabled; it uses
    exactly the same redaction path as the SDK.
    """

    def __init__(self, dsn: str | None = None, *, sdk: Any | None = None) -> None:
        self.dsn = (dsn if dsn is not None else os.environ.get("SENTRY_DSN", "")).strip()
        self.configured = bool(self.dsn)
        self.enabled = False
        self.events: list[dict[str, Any]] = []
        self._active_spans: dict[int, Any] = {}
        self._sentry = sdk
        self._failure: str | None = None

        if not self.configured and sdk is None:
            return
        try:
            if self._sentry is None:
                import sentry_sdk  # type: ignore

                self._sentry = sentry_sdk
            if self.configured:
                self._sentry.init(
                    self.dsn,
                    send_default_pii=False,
                    traces_sample_rate=1.0,
                    before_send=self._before_send,
                    before_send_transaction=self._before_send_transaction,
                )
                self.enabled = True
            else:
                # An injected SDK is useful for tests without making a DSN-less
                # production process emit network traffic.
                self._sentry = None
        except Exception:
            self._sentry = None
            self._failure = "sdk_unavailable"

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        safe_name = self._safe_span_name(name)
        try:
            safe_attributes = self._safe_attributes(attributes)
        except Exception:
            safe_attributes = {}
        event: dict[str, Any] = {"name": safe_name, "attributes": safe_attributes}
        sentry_span = self._start_span(safe_name, safe_attributes)
        if sentry_span is not None:
            self._active_spans[id(event)] = sentry_span
        try:
            yield event
        except BaseException as exc:
            event["error_class"] = type(exc).__name__
            self._set_data(sentry_span, "error_class", type(exc).__name__)
            raise
        finally:
            event["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            try:
                self.events.append(event)
            except Exception:
                pass
            # Never pass the original exception or traceback to Sentry: both
            # can contain raw values and local paths.
            self._set_data(sentry_span, "duration_ms", event["duration_ms"])
            self._finish_span(sentry_span)
            self._active_spans.pop(id(event), None)

    def annotate(self, event: dict[str, Any], **attributes: Any) -> None:
        """Add more aggregate data after a stage has measured its result."""
        try:
            safe_attributes = self._safe_attributes(attributes)
            event_attributes = event.setdefault("attributes", {})
            if isinstance(event_attributes, dict):
                event_attributes.update(safe_attributes)
            span = self._active_spans.get(id(event))
            for key, value in safe_attributes.items():
                self._set_data(span, key, value)
        except Exception:
            pass

    def _start_span(self, name: str, attributes: dict[str, Any]) -> Any | None:
        sdk = self._sentry
        if sdk is None or not self.enabled:
            return None
        span = None
        try:
            span = sdk.start_span(op="molt", name=name)
            span.__enter__()
            for key, value in attributes.items():
                self._set_data(span, key, value)
            return span
        except Exception:
            self._finish_span(span)
            return None

    @staticmethod
    def _set_data(span: Any | None, key: str, value: Any) -> None:
        if span is None:
            return
        try:
            span.set_data(key, value)
        except Exception:
            # Sentry is an observer, never a dependency of the workflow.
            pass

    @staticmethod
    def _finish_span(span: Any | None) -> None:
        if span is None:
            return
        try:
            span.__exit__(None, None, None)
        except Exception:
            pass

    @classmethod
    def _safe_span_name(cls, name: Any) -> str:
        candidate = str(name) if isinstance(name, str) else ""
        if _SAFE_NAME.fullmatch(candidate):
            return candidate
        return "molt.unknown"

    @classmethod
    def _safe_attributes(cls, attributes: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in attributes.items():
            if not isinstance(key, str):
                continue
            lowered = key.lower()
            if lowered not in _SAFE_ATTRIBUTE_KEYS:
                continue
            if isinstance(value, bool) or value is None:
                safe[key] = value
            elif isinstance(value, int) and not isinstance(value, bool):
                safe[key] = value
            elif isinstance(value, float) and math.isfinite(value):
                safe[key] = value
            elif isinstance(value, str) and _SAFE_LABEL.fullmatch(value) and not cls._contains_sensitive_token(value):
                safe[key] = value
        return safe

    @staticmethod
    def _contains_sensitive_token(value: str) -> bool:
        lowered = value.lower()
        return any(part in lowered for part in _SENSITIVE_KEY_PARTS) or any(char in value for char in ("/", "\\", "\n", "\r"))

    @classmethod
    def _scrub_event(cls, event: Any) -> Any:
        """Keep Sentry callbacks safe even for SDK-generated event fields."""
        if not isinstance(event, dict):
            return None
        scrubbed: dict[str, Any] = {}
        for key, value in event.items():
            if not isinstance(key, str):
                continue
            lowered = key.lower()
            if lowered in {"message", "request", "breadcrumbs", "exception", "stacktrace", "contexts", "extra"}:
                continue
            if lowered not in _SAFE_ATTRIBUTE_KEYS and (
                any(part in lowered for part in _SENSITIVE_KEY_PARTS)
                or any(part in lowered for part in ("filename", "abs_path", "url", "cookie", "authorization"))
            ):
                continue
            if isinstance(value, dict):
                nested = cls._scrub_event(value)
                if nested:
                    scrubbed[key] = nested
            elif isinstance(value, list):
                nested_list = [cls._scrub_event(item) for item in value]
                nested_list = [item for item in nested_list if item]
                if nested_list:
                    scrubbed[key] = nested_list
            elif isinstance(value, (bool, int, float)):
                scrubbed[key] = value
            elif key.lower() in _SAFE_SCRUB_STRING_KEYS and isinstance(value, str) and _SAFE_LABEL.fullmatch(value) and not cls._contains_sensitive_token(value):
                scrubbed[key] = value
        return scrubbed

    @classmethod
    def _before_send(cls, event: Any, hint: Any = None) -> Any:
        del hint
        return cls._scrub_event(event)

    @classmethod
    def _before_send_transaction(cls, event: Any, hint: Any = None) -> Any:
        del hint
        return cls._scrub_event(event)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "mode": "sentry" if self.enabled else "local-only",
            "failure_isolated": True,
            **({"reason": self._failure} if self._failure else {}),
        }
