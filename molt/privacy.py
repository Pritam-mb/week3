from __future__ import annotations

import hashlib
import json
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


_SAFE_FEEDBACK_MESSAGES = {
    "golden_output": "The deterministic output did not match the independently authored expected CSV.",
    "idempotence": "Applying the recipe a second time changed the canonical output.",
    "empty_input": "The recipe did not safely handle a header-only input.",
    "column_order_invariant": "The recipe changed behavior when input columns were reordered.",
    "required_column_guard": "The recipe did not reject an input missing a required column.",
    "extra_column_preservation": "The recipe did not preserve declared extra columns.",
    "UNMAPPED_VALUE": "A map_values operation rejected an already canonical value. For the affected column, retain the source mappings and add identity mappings such as Food: Food, Transport: Transport, and Books: Books when those are canonical values in the task.",
}


_SAFE_MODEL_ERROR_MESSAGES = {
    "RECIPE_SCHEMA_INVALID": "The previous JSON shape did not satisfy Molt's required schema; include every required field and use exact canonical operation fields.",
    "UNSUPPORTED_OPERATION": "The previous candidate used an operation outside Molt's allowlist; use only the operations listed in the compiler instructions.",
    "MODEL_RESPONSE_INVALID": "The previous response was not a valid constrained recipe JSON object.",
    "MODEL_PROMPT_TOO_LARGE": "The previous model context exceeded Molt's prompt budget; keep the recipe concise.",
}


def safe_model_error(code: str) -> dict[str, str]:
    """Return a stable, non-sensitive model retry message for a Molt error."""
    safe_code = str(code)[:80]
    return {"kind": "generation_error", "code": safe_code, "message": _SAFE_MODEL_ERROR_MESSAGES.get(safe_code, "The previous model attempt was rejected by Molt.")}


def safe_verification_feedback(
    result: dict[str, Any],
    *,
    max_failures: int = 8,
    max_bytes: int = 4096,
) -> dict[str, Any]:
    """Build bounded feedback without sending fixture values or filesystem paths."""
    failures: list[dict[str, str]] = []
    for item in result.get("results", []):
        if not isinstance(item, dict) or item.get("status") != "FAIL":
            continue
        check = str(item.get("check", "verification")).strip()[:80]
        failure: dict[str, Any] = {
            "fixture": f"fixture_{len(failures) + 1}",
            "check": check,
            "code": check,
            "message": _SAFE_FEEDBACK_MESSAGES.get(check, "An independent verification check failed."),
        }
        structure = item.get("structure")
        if check == "golden_output" and isinstance(structure, dict):
            failure["structure"] = {
                "actual_rows": int(structure.get("actual_rows", 0) or 0),
                "expected_rows": int(structure.get("expected_rows", 0) or 0),
                "first_difference_row": structure.get("first_difference_row"),
                "different_columns": [str(column)[:80] for column in structure.get("different_columns", [])[:12]],
            }
        context = item.get("context")
        if check == "UNMAPPED_VALUE" and isinstance(context, dict) and isinstance(context.get("column"), str):
            failure["context"] = {"column": context["column"][:80]}
        failures.append(failure)
        if len(failures) >= max_failures:
            break

    feedback: dict[str, Any] = {
        "kind": "verification_feedback",
        "status": str(result.get("status", "FAIL")),
        "checks_failed": int(result.get("checks_failed", len(failures)) or 0),
        "failures": failures,
        "truncated": len(failures) < int(result.get("checks_failed", len(failures)) or 0),
        "omitted_failures": max(0, int(result.get("checks_failed", len(failures)) or 0) - len(failures)),
    }
    encoded = json.dumps(feedback, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) <= max_bytes:
        return feedback
    feedback["failures"] = feedback["failures"][:1]
    feedback["truncated"] = True
    feedback["omitted_failures"] = max(0, int(result.get("checks_failed", 0) or 0) - len(feedback["failures"]))
    if len(json.dumps(feedback, sort_keys=True, separators=(",", ":")).encode("utf-8")) <= max_bytes:
        return feedback
    minimal = {"kind": "verification_feedback", "truncated": True}
    if len(json.dumps(minimal, separators=(",", ":")).encode("utf-8")) > max_bytes:
        return {}
    return minimal
