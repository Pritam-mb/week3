from __future__ import annotations

import hashlib
import re
from typing import Any


SECRET_NAME = re.compile(r"(password|passwd|secret|token|api[_-]?key|authorization|ssn|email|phone|name|address|birth|dob|zip|postal)", re.I)


def is_sensitive_field(name: str) -> bool:
    return bool(SECRET_NAME.search(name))


def mask_value(value: Any, index: int = 0) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return f"<VALUE_{index + 1}_{digest}>"


def redact_sample(row: dict[str, Any], *, reveal_values: bool = False) -> dict[str, Any]:
    if reveal_values:
        return dict(row)
    result: dict[str, Any] = {}
    for index, (key, value) in enumerate(row.items()):
        result[key] = "<REDACTED_COLUMN>" if is_sensitive_field(key) else mask_value(value, index)
    return result


def safe_profile_context(profile: dict[str, Any], *, reveal_values: bool = False) -> dict[str, Any]:
    context = {key: value for key, value in profile.items() if key not in {"sample", "model_context"}}
    context["sample"] = [redact_sample(row, reveal_values=reveal_values) for row in profile.get("sample", [])]
    context["privacy"] = {"values_masked": not reveal_values, "raw_rows_sent": bool(reveal_values)}
    return context
