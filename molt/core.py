from __future__ import annotations

import csv
import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from .privacy import safe_profile_context


class MoltError(Exception):
    """A safe, user-facing failure with a stable error code."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


SUPPORTED_OPERATIONS = {
    "rename_column",
    "trim",
    "normalize_case",
    "coerce_date",
    "parse_decimal",
    "map_values",
    "split_column",
    "dedupe",
    "filter_rows",
    "select_columns",
    "reorder_columns",
    "drop_empty_rows",
    "fill_null",
    "validate_values",
}

OPERATION_FIELDS = {
    "rename_column": {"type", "source", "destination"},
    "trim": {"type", "columns"},
    "normalize_case": {"type", "columns", "mode"},
    "coerce_date": {"type", "column", "input_formats", "output_format", "on_error"},
    "parse_decimal": {
        "type",
        "column",
        "decimal_separator",
        "thousands_separator",
        "decimal_places",
        "on_error",
    },
    "map_values": {"type", "column", "mapping", "on_unmapped", "keep_known"},
    "split_column": {"type", "column", "delimiter", "output_columns", "on_missing"},
    "dedupe": {"type", "key_columns", "keep"},
    "filter_rows": {"type", "condition", "on_no_match"},
    "select_columns": {"type", "columns"},
    "reorder_columns": {"type", "columns", "preserve_extra_columns"},
    "drop_empty_rows": {"type", "columns"},
    "fill_null": {"type", "columns", "value"},
    "validate_values": {"type", "column", "allowed_values", "min", "max", "on_error"},
}


def _require(condition: bool, code: str, message: str, **details: Any) -> None:
    if not condition:
        raise MoltError(code, message, details=details)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MoltError("MODEL_RESPONSE_INVALID", f"Could not read JSON: {path}") from exc


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Fill backward-compatible defaults before a recipe is verified or stored."""
    normalized = copy.deepcopy(recipe)
    if isinstance(normalized, dict) and isinstance(normalized.get("operations"), list):
        for operation in normalized["operations"]:
            if isinstance(operation, dict) and operation.get("type") == "map_values":
                operation.setdefault("keep_known", True)
    return normalized


def validate_recipe(recipe: dict[str, Any]) -> dict[str, Any]:
    """Validate the closed recipe language before any input is touched."""
    recipe = normalize_recipe(recipe)
    _require(isinstance(recipe, dict), "RECIPE_SCHEMA_INVALID", "Recipe must be a JSON object.")
    required = {"schema_version", "name", "description", "input_contract", "operations", "output_contract"}
    _require(not (set(recipe) - required - {"verification_policy", "limits"}), "RECIPE_SCHEMA_INVALID", "Recipe contains unsupported top-level fields.")
    _require(required <= recipe.keys(), "RECIPE_SCHEMA_INVALID", "Recipe is missing required fields.")
    _require(recipe["schema_version"] == 1, "RECIPE_SCHEMA_INVALID", "Only schema version 1 is supported.")
    _require(isinstance(recipe["name"], str) and recipe["name"].strip(), "RECIPE_SCHEMA_INVALID", "Recipe name must be non-empty.")
    _require(isinstance(recipe["operations"], list) and 0 < len(recipe["operations"]) <= 30, "RECIPE_SCHEMA_INVALID", "Recipe must contain 1-30 operations.")

    contract = recipe["input_contract"]
    output = recipe["output_contract"]
    _require(isinstance(contract, dict), "RECIPE_SCHEMA_INVALID", "input_contract must be an object.")
    _require(isinstance(output, dict), "RECIPE_SCHEMA_INVALID", "output_contract must be an object.")
    required_columns = contract.get("required_columns")
    _require(isinstance(required_columns, list) and all(isinstance(c, str) and c for c in required_columns), "RECIPE_SCHEMA_INVALID", "required_columns must be a list of names.")
    _require(isinstance(output.get("required_columns"), list), "RECIPE_SCHEMA_INVALID", "output_contract.required_columns must be a list.")
    _require(output.get("preserve_extra_columns") is True, "RECIPE_SCHEMA_INVALID", "The MVP requires preserving extra columns.")

    available_columns = list(required_columns)
    for index, operation in enumerate(recipe["operations"]):
        _require(isinstance(operation, dict), "RECIPE_SCHEMA_INVALID", f"Operation {index + 1} must be an object.")
        op_type = operation.get("type")
        _require(op_type in SUPPORTED_OPERATIONS, "UNSUPPORTED_OPERATION", f"Unsupported operation: {op_type!r}.", operation=index + 1)
        unknown = set(operation) - OPERATION_FIELDS[op_type]
        _require(not unknown, "RECIPE_SCHEMA_INVALID", f"Operation {op_type} has unsupported arguments: {sorted(unknown)}.")
        _validate_operation(operation, available_columns)
        if operation["type"] == "rename_column":
            available_columns[available_columns.index(operation["source"])] = operation["destination"]
        elif operation["type"] == "split_column":
            available_columns.extend(column for column in operation["output_columns"] if column not in available_columns)
        elif operation["type"] == "select_columns":
            available_columns = list(operation["columns"])
        elif operation["type"] == "reorder_columns":
            available_columns = list(operation["columns"]) + ([column for column in available_columns if column not in operation["columns"]] if operation["preserve_extra_columns"] else [])
    output_required = output.get("required_columns", [])
    _require(set(output_required) <= set(available_columns), "RECIPE_SCHEMA_INVALID", "Output contract references a column not produced by the recipe.")
    return recipe


def _validate_operation(operation: dict[str, Any], required_columns: list[str]) -> None:
    op_type = operation["type"]
    if op_type == "rename_column":
        _require(isinstance(operation.get("source"), str) and operation["source"] in required_columns, "RECIPE_SCHEMA_INVALID", "rename_column.source must be a required column.")
        _require(isinstance(operation.get("destination"), str) and operation["destination"] not in required_columns, "RECIPE_SCHEMA_INVALID", "rename_column.destination must be a new column.")
    elif op_type in {"trim", "normalize_case"}:
        _require(isinstance(operation.get("columns"), list) and operation["columns"], "RECIPE_SCHEMA_INVALID", f"{op_type}.columns is required.")
        _require(all(isinstance(column, str) for column in operation["columns"]), "RECIPE_SCHEMA_INVALID", f"{op_type}.columns must contain strings.")
        _require(set(operation["columns"]) <= set(required_columns), "RECIPE_SCHEMA_INVALID", f"{op_type} references an undeclared column.")
        if op_type == "normalize_case":
            _require(operation.get("mode") in {"lower", "upper", "title"}, "RECIPE_SCHEMA_INVALID", "normalize_case.mode must be lower, upper, or title.")
    elif op_type == "split_column":
        _require(operation.get("column") in required_columns, "RECIPE_SCHEMA_INVALID", "split_column.column must be a required column.")
        _require(isinstance(operation.get("delimiter"), str), "RECIPE_SCHEMA_INVALID", "split_column.delimiter is required.")
        _require(isinstance(operation.get("output_columns"), list) and operation["output_columns"], "RECIPE_SCHEMA_INVALID", "split_column.output_columns is required.")
        _require(operation.get("on_missing") in {"fail", "fill_empty"}, "RECIPE_SCHEMA_INVALID", "split_column.on_missing must be fail or fill_empty.")
    elif op_type == "coerce_date":
        _require(isinstance(operation.get("column"), str) and operation["column"] in required_columns, "RECIPE_SCHEMA_INVALID", "coerce_date.column must be a required column.")
        _require(isinstance(operation.get("input_formats"), list) and operation["input_formats"] and all(isinstance(item, str) for item in operation["input_formats"]), "RECIPE_SCHEMA_INVALID", "coerce_date.input_formats is required.")
        _require(isinstance(operation.get("output_format"), str), "RECIPE_SCHEMA_INVALID", "coerce_date.output_format is required.")
        _require(operation.get("on_error") == "fail", "RECIPE_SCHEMA_INVALID", "coerce_date must fail on invalid values in the MVP.")
    elif op_type == "parse_decimal":
        _require(isinstance(operation.get("column"), str) and operation["column"] in required_columns, "RECIPE_SCHEMA_INVALID", "parse_decimal.column must be a required column.")
        _require(operation.get("on_error") == "fail", "RECIPE_SCHEMA_INVALID", "parse_decimal must fail on invalid values in the MVP.")
        _require(operation.get("decimal_separator") in {".", ","}, "RECIPE_SCHEMA_INVALID", "decimal_separator must be '.' or ','.")
        _require(isinstance(operation.get("thousands_separator"), str), "RECIPE_SCHEMA_INVALID", "thousands_separator is required.")
        if "decimal_places" in operation:
            _require(isinstance(operation["decimal_places"], int) and 0 <= operation["decimal_places"] <= 6, "RECIPE_SCHEMA_INVALID", "decimal_places must be an integer from 0 to 6.")
    elif op_type == "map_values":
        _require(isinstance(operation.get("column"), str) and operation["column"] in required_columns, "RECIPE_SCHEMA_INVALID", "map_values.column must be a required column.")
        _require(isinstance(operation.get("mapping"), dict), "RECIPE_SCHEMA_INVALID", "map_values.mapping is required.")
        _require(all(isinstance(key, str) and isinstance(value, str) for key, value in operation["mapping"].items()), "RECIPE_SCHEMA_INVALID", "map_values.mapping must map strings to strings.")
        _require(operation.get("on_unmapped") in {"fail", "preserve"}, "RECIPE_SCHEMA_INVALID", "on_unmapped must be fail or preserve.")
        _require(isinstance(operation.get("keep_known"), bool), "RECIPE_SCHEMA_INVALID", "map_values.keep_known must be a boolean.")
    elif op_type == "dedupe":
        _require(isinstance(operation.get("key_columns"), list) and operation["key_columns"], "RECIPE_SCHEMA_INVALID", "dedupe.key_columns is required.")
        _require(set(operation["key_columns"]) <= set(required_columns), "RECIPE_SCHEMA_INVALID", "dedupe references an undeclared column.")
        _require(operation.get("keep") in {"first", "last"}, "RECIPE_SCHEMA_INVALID", "dedupe.keep must be first or last.")
    elif op_type in {"select_columns", "reorder_columns", "drop_empty_rows", "fill_null"}:
        _require(isinstance(operation.get("columns"), list) and operation["columns"], "RECIPE_SCHEMA_INVALID", f"{op_type}.columns is required.")
        _require(set(operation["columns"]) <= set(required_columns), "RECIPE_SCHEMA_INVALID", f"{op_type} references an undeclared column.")
        if op_type == "reorder_columns":
            _require(operation.get("preserve_extra_columns") in {True, False}, "RECIPE_SCHEMA_INVALID", "reorder_columns.preserve_extra_columns is required.")
        if op_type == "fill_null":
            _require("value" in operation and isinstance(operation["value"], str), "RECIPE_SCHEMA_INVALID", "fill_null.value is required.")
    elif op_type == "filter_rows":
        condition = operation.get("condition")
        _require(isinstance(condition, dict), "RECIPE_SCHEMA_INVALID", "filter_rows.condition must be a declarative object.")
        _require(condition.get("column") in required_columns, "RECIPE_SCHEMA_INVALID", "filter_rows.condition.column must be a required column.")
        _require(condition.get("operator") in {"eq", "neq", "contains", "in", "gt", "gte", "lt", "lte"}, "RECIPE_SCHEMA_INVALID", "filter_rows uses an unsupported operator.")
        _require("value" in condition, "RECIPE_SCHEMA_INVALID", "filter_rows.condition.value is required.")
        _require(operation.get("on_no_match") in {"keep_empty", "fail"}, "RECIPE_SCHEMA_INVALID", "filter_rows.on_no_match must be keep_empty or fail.")
    elif op_type == "validate_values":
        _require(operation.get("column") in required_columns, "RECIPE_SCHEMA_INVALID", "validate_values.column must be a required column.")
        _require(operation.get("on_error") == "fail", "RECIPE_SCHEMA_INVALID", "validate_values must fail on invalid values.")
        _require(any(key in operation for key in ("allowed_values", "min", "max")), "RECIPE_SCHEMA_INVALID", "validate_values needs a constraint.")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            _require(reader.fieldnames is not None, "INPUT_TYPE_MISMATCH", f"CSV has no header: {path.name}.")
            headers = list(reader.fieldnames)
            _require(all(headers), "INPUT_TYPE_MISMATCH", "CSV contains an empty column name.")
            _require(len(set(headers)) == len(headers), "INPUT_TYPE_MISMATCH", "CSV contains duplicate column names.")
            rows = [dict(row) for row in reader]
            _require(all(None not in row for row in rows), "INPUT_TYPE_MISMATCH", "CSV contains rows with more fields than its header.")
    except MoltError:
        raise
    except (OSError, csv.Error, UnicodeError) as exc:
        raise MoltError("INPUT_TYPE_MISMATCH", f"Could not parse CSV {path.name}: {exc}") from exc
    return headers, rows


def profile_csv(path: Path) -> dict[str, Any]:
    headers, rows = read_csv(path)
    null_counts = {header: sum(not (row.get(header) or "").strip() for row in rows) for header in headers}
    duplicate_rows = len(rows) - len({tuple(row.get(h, "") for h in headers) for row in rows})
    inferred_types: dict[str, str] = {}
    parse_rates: dict[str, float] = {}
    for header in headers:
        values = [(row.get(header) or "").strip() for row in rows if (row.get(header) or "").strip()]
        if not values:
            inferred_types[header] = "empty"
            parse_rates[header] = 1.0
        else:
            numeric = 0
            dates = 0
            for value in values:
                try:
                    Decimal(value.replace(",", ""))
                    numeric += 1
                except InvalidOperation:
                    pass
                for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
                    try:
                        datetime.strptime(value, date_format)
                        dates += 1
                        break
                    except ValueError:
                        continue
            if numeric == len(values): inferred_types[header] = "decimal"
            elif dates == len(values): inferred_types[header] = "date"
            else: inferred_types[header] = "string"
            parse_rates[header] = round(max(numeric, dates) / len(values), 3)
    profile = {
        "file": path.name,
        "columns": headers,
        "row_count": len(rows),
        "column_count": len(headers),
        "size_bytes": path.stat().st_size,
        "null_counts": null_counts,
        "duplicate_row_count": duplicate_rows,
        "inferred_types": inferred_types,
        "parse_success_rates": parse_rates,
        "delimiter": ",",
        "sample": [{key: value for key, value in row.items()} for row in rows[:3]],
    }
    profile["model_context"] = safe_profile_context(profile)
    return profile


def fingerprint_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def schema_fingerprint(headers: Iterable[str]) -> str:
    return hashlib.sha256(json.dumps(list(headers), separators=(",", ":")).encode()).hexdigest()[:16]


def check_contract(recipe: dict[str, Any], headers: list[str]) -> None:
    required = recipe["input_contract"]["required_columns"]
    missing = [column for column in required if column not in headers]
    if missing:
        raise MoltError("REQUIRED_COLUMN_MISSING", f"Missing required column(s): {', '.join(missing)}.", details={"missing": missing, "expected": required, "observed": headers})
    if recipe["input_contract"].get("allow_extra_columns") is False:
        extras = [column for column in headers if column not in required]
        if extras:
            raise MoltError("INPUT_TYPE_MISMATCH", f"Unexpected column(s): {', '.join(extras)}.", details={"extra": extras})


def _parse_date(value: str, formats: list[str], output_format: str) -> str:
    for date_format in formats:
        try:
            return datetime.strptime(value.strip(), date_format).strftime(output_format)
        except ValueError:
            continue
    raise MoltError("INPUT_TYPE_MISMATCH", f"Invalid date value: {value!r}.")


def _parse_decimal(value: str, operation: dict[str, Any]) -> str:
    raw = value.strip()
    thousands = operation["thousands_separator"]
    decimal_separator = operation["decimal_separator"]
    if thousands and thousands == decimal_separator:
        raise MoltError("RECIPE_SCHEMA_INVALID", "Decimal and thousands separators must differ.")
    if thousands:
        raw = raw.replace(thousands, "")
    if decimal_separator != ".":
        raw = raw.replace(decimal_separator, ".")
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise MoltError("INPUT_TYPE_MISMATCH", f"Invalid decimal value: {value!r}.") from exc
    if "decimal_places" in operation:
        places = operation["decimal_places"]
        number = number.quantize(Decimal("1." + "0" * places), rounding=ROUND_HALF_UP)
    return format(number, "f")


def _apply_operation(operation: dict[str, Any], working_headers: list[str], working_rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
        op_type = operation["type"]
        if op_type == "rename_column":
            source = operation["source"]
            destination = operation["destination"]
            working_headers = [destination if column == source else column for column in working_headers]
            for row in working_rows:
                row[destination] = row.pop(source, "")
        elif op_type == "trim":
            for row in working_rows:
                for column in operation["columns"]:
                    row[column] = row.get(column, "").strip()
        elif op_type == "normalize_case":
            mode = operation["mode"]
            for row in working_rows:
                for column in operation["columns"]:
                    value = row.get(column, "")
                    row[column] = value.lower() if mode == "lower" else value.upper() if mode == "upper" else value.title()
        elif op_type == "coerce_date":
            for row in working_rows:
                value = row.get(operation["column"], "")
                row[operation["column"]] = _parse_date(value, operation["input_formats"], operation["output_format"])
        elif op_type == "parse_decimal":
            for row in working_rows:
                row[operation["column"]] = _parse_decimal(row.get(operation["column"], ""), operation)
        elif op_type == "map_values":
            mapping = operation["mapping"]
            column = operation["column"]
            known_values = set(mapping.values())
            keep_known = operation.get("keep_known", True)
            unmapped_count = 0
            for row in working_rows:
                value = row.get(column, "")
                if value in mapping:
                    row[column] = mapping[value]
                elif keep_known and value in known_values:
                    continue
                elif operation["on_unmapped"] == "fail":
                    unmapped_count += 1
            if unmapped_count and operation["on_unmapped"] == "fail":
                raise MoltError(
                    "UNMAPPED_VALUE",
                    f"Unmapped value in column {column}, {unmapped_count} row(s).",
                    details={"column": column, "unmapped_count": unmapped_count},
                )
        elif op_type == "split_column":
            column = operation["column"]
            output_columns = operation["output_columns"]
            for output_column in reversed(output_columns):
                if output_column not in working_headers:
                    working_headers.insert(working_headers.index(column) + 1, output_column)
            for row in working_rows:
                parts = row.get(column, "").split(operation["delimiter"])
                if len(parts) < len(output_columns) and operation["on_missing"] == "fail":
                    raise MoltError("INPUT_TYPE_MISMATCH", f"Could not split {column!r} into {output_columns}.")
                for index, output_column in enumerate(output_columns):
                    row[output_column] = parts[index].strip() if index < len(parts) else ""
        elif op_type == "dedupe":
            key_columns = operation["key_columns"]
            if operation["keep"] == "first":
                seen: set[tuple[str, ...]] = set()
                deduped = []
                for row in working_rows:
                    key = tuple(row.get(column, "") for column in key_columns)
                    if key not in seen:
                        seen.add(key)
                        deduped.append(row)
                working_rows = deduped
            else:
                seen = set()
                deduped_reversed = []
                for row in reversed(working_rows):
                    key = tuple(row.get(column, "") for column in key_columns)
                    if key not in seen:
                        seen.add(key)
                        deduped_reversed.append(row)
                working_rows = list(reversed(deduped_reversed))
        elif op_type == "filter_rows":
            condition = operation["condition"]
            column, operator, expected = condition["column"], condition["operator"], condition["value"]
            def matches(row: dict[str, str]) -> bool:
                actual = row.get(column, "")
                if operator == "eq": return actual == str(expected)
                if operator == "neq": return actual != str(expected)
                if operator == "contains": return str(expected) in actual
                if operator == "in": return actual in {str(item) for item in expected}
                try:
                    left, right = Decimal(actual), Decimal(str(expected))
                except (InvalidOperation, TypeError):
                    left, right = actual, str(expected)
                return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[operator]
            filtered = [row for row in working_rows if matches(row)]
            if not filtered and operation["on_no_match"] == "fail":
                raise MoltError("INVARIANT_FAILED", "filter_rows removed every row.")
            working_rows = filtered
        elif op_type == "select_columns":
            selected = operation["columns"]
            working_headers = selected
            working_rows = [{column: row.get(column, "") for column in selected} for row in working_rows]
        elif op_type == "reorder_columns":
            ordered = list(operation["columns"])
            if operation["preserve_extra_columns"]:
                ordered.extend(column for column in working_headers if column not in ordered)
            working_headers = ordered
        elif op_type == "drop_empty_rows":
            columns = operation["columns"]
            working_rows = [row for row in working_rows if any((row.get(column) or "").strip() for column in columns)]
        elif op_type == "fill_null":
            for row in working_rows:
                for column in operation["columns"]:
                    if not (row.get(column) or "").strip():
                        row[column] = operation["value"]
        elif op_type == "validate_values":
            allowed = set(operation.get("allowed_values", []))
            for row in working_rows:
                value = row.get(operation["column"], "")
                valid = (not allowed or value in allowed)
                try:
                    numeric = Decimal(value)
                    if "min" in operation: valid = valid and numeric >= Decimal(str(operation["min"]))
                    if "max" in operation: valid = valid and numeric <= Decimal(str(operation["max"]))
                except InvalidOperation:
                    valid = valid and not ("min" in operation or "max" in operation)
                if not valid:
                    raise MoltError("INVARIANT_FAILED", f"Value validation failed for {operation['column']}.")
        return working_headers, working_rows


def execute_recipe(recipe: dict[str, Any], headers: list[str], rows: list[dict[str, str]]) -> tuple[list[str], list[dict[str, str]]]:
    recipe = validate_recipe(recipe)
    check_contract(recipe, headers)
    working_headers = list(headers)
    working_rows = [dict(row) for row in rows]

    for operation in recipe["operations"]:
        working_headers, working_rows = _apply_operation(operation, working_headers, working_rows)

    output_columns = recipe["output_contract"]["required_columns"]
    for column in output_columns:
        _require(column in working_headers, "INVARIANT_FAILED", f"Required output column missing: {column}.")
    return working_headers, working_rows


def execute_recipe_resumable(
    recipe: dict[str, Any],
    headers: list[str],
    rows: list[dict[str, str]],
    checkpoint_dir: Path,
    *,
    resume: bool = False,
    crash_after: int | None = None,
) -> tuple[list[str], list[dict[str, str]], int]:
    """Execute one operation at a time and persist the last completed step."""
    recipe = validate_recipe(recipe)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    state_path = checkpoint_dir / "state.json"
    if resume and state_path.exists():
        state = load_json(state_path)
        working_headers, working_rows = read_csv(checkpoint_dir / state["checkpoint_file"])
        start_at = int(state["completed_steps"])
    else:
        check_contract(recipe, headers)
        working_headers = list(headers)
        working_rows = [dict(row) for row in rows]
        start_at = 0

    for index, operation in enumerate(recipe["operations"][start_at:], start=start_at):
        working_headers, working_rows = _apply_operation(operation, working_headers, working_rows)
        checkpoint_file = f"step_{index + 1}.csv"
        write_csv_atomic(checkpoint_dir / checkpoint_file, working_headers, working_rows)
        save_json(state_path, {"status": "running", "completed_steps": index + 1, "checkpoint_file": checkpoint_file})
        if crash_after is not None and index + 1 == crash_after:
            raise RuntimeError(f"simulated crash after step {crash_after}")

    save_json(state_path, {"status": "done", "completed_steps": len(recipe["operations"]), "checkpoint_file": f"step_{len(recipe['operations'])}.csv"})
    output_columns = recipe["output_contract"]["required_columns"]
    for column in output_columns:
        _require(column in working_headers, "INVARIANT_FAILED", f"Required output column missing: {column}.")
    return working_headers, working_rows, start_at


def canonical_csv(headers: list[str], rows: list[dict[str, str]]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def write_csv_atomic(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def verify_recipe(recipe: dict[str, Any], fixtures: list[tuple[Path, Path]]) -> dict[str, Any]:
    recipe = validate_recipe(recipe)
    results: list[dict[str, Any]] = []
    for input_path, expected_path in fixtures:
        try:
            headers, rows = read_csv(input_path)
            expected_headers, expected_rows = read_csv(expected_path)
            actual_headers, actual_rows = execute_recipe(recipe, headers, rows)
            matches = actual_headers == expected_headers and actual_rows == expected_rows
            result = {
                "fixture": input_path.name,
                "status": "PASS" if matches else "FAIL",
                "check": "golden_output",
                "details": "Output matches independently authored expected CSV." if matches else "Output differs from expected CSV.",
            }
            if not matches:
                first_difference = next((index for index, (actual, expected) in enumerate(zip(actual_rows, expected_rows)) if actual != expected), None)
                result["structure"] = {
                    "actual_rows": len(actual_rows),
                    "expected_rows": len(expected_rows),
                    "header_differences": [column for column in sorted(set(actual_headers) | set(expected_headers)) if column not in actual_headers or column not in expected_headers],
                    "first_difference_row": first_difference + 1 if first_difference is not None else None,
                    "different_columns": sorted({column for index, (actual, expected) in enumerate(zip(actual_rows, expected_rows)) if actual != expected for column in set(actual) | set(expected) if actual.get(column) != expected.get(column)}),
                }
            results.append(result)
            if not matches:
                continue
            renamed_sources = {operation.get("source") for operation in recipe["operations"] if operation.get("type") == "rename_column"}
            if renamed_sources and not renamed_sources <= set(expected_headers):
                results.append({"fixture": input_path.name, "status": "SKIP", "check": "idempotence", "details": "Skipped because this recipe intentionally changes the schema through rename_column."})
            else:
                second_headers, second_rows = execute_recipe(recipe, actual_headers, actual_rows)
                idempotent = canonical_csv(second_headers, second_rows) == canonical_csv(actual_headers, actual_rows)
                results.append({
                    "fixture": input_path.name,
                    "status": "PASS" if idempotent else "FAIL",
                    "check": "idempotence",
                    "details": "Applying the recipe twice produces the same canonical CSV." if idempotent else "Applying the recipe twice changed the output.",
                })
        except MoltError as exc:
            results.append({"fixture": input_path.name, "status": "FAIL", "check": exc.code, "details": exc.message, "context": {key: value for key, value in exc.details.items() if key != "value"}})
    if fixtures:
        input_path, _ = fixtures[0]
        try:
            headers, rows = read_csv(input_path)
            execute_recipe(recipe, headers, [])
            results.append({"fixture": input_path.name, "status": "PASS", "check": "empty_input", "details": "Header-only input is handled without inventing rows."})
        except MoltError as exc:
            results.append({"fixture": input_path.name, "status": "FAIL", "check": "empty_input", "details": exc.message, "context": {key: value for key, value in exc.details.items() if key != "value"}})
        try:
            reordered_headers = list(reversed(headers))
            reordered_rows = [{column: row.get(column, "") for column in reordered_headers} for row in rows]
            original_headers, original_rows = execute_recipe(recipe, headers, rows)
            shuffled_headers, shuffled_rows = execute_recipe(recipe, reordered_headers, reordered_rows)
            original_membership = sorted(json.dumps(row, sort_keys=True) for row in original_rows)
            shuffled_membership = sorted(json.dumps(row, sort_keys=True) for row in shuffled_rows)
            results.append({"fixture": input_path.name, "status": "PASS" if original_membership == shuffled_membership else "FAIL", "check": "column_order_invariant", "details": "Column names, not positions, determine transformations."})
        except MoltError as exc:
            results.append({"fixture": input_path.name, "status": "FAIL", "check": "column_order_invariant", "details": exc.message, "context": {key: value for key, value in exc.details.items() if key != "value"}})
        required_columns = recipe["input_contract"]["required_columns"]
        missing_headers = [column for column in headers if column != required_columns[0]]
        missing_rows = [{key: value for key, value in row.items() if key != required_columns[0]} for row in rows]
        try:
            execute_recipe(recipe, missing_headers, missing_rows)
            results.append({"fixture": input_path.name, "status": "FAIL", "check": "required_column_guard", "details": "Missing required column was accepted."})
        except MoltError as exc:
            results.append({"fixture": input_path.name, "status": "PASS" if exc.code == "REQUIRED_COLUMN_MISSING" else "FAIL", "check": "required_column_guard", "details": exc.message, "context": {key: value for key, value in exc.details.items() if key != "value"}})
        try:
            if recipe["output_contract"].get("preserve_extra_columns"):
                renamed_sources = {operation.get("source") for operation in recipe["operations"] if operation.get("type") == "rename_column"}
                extras = [column for column in headers if column not in recipe["input_contract"]["required_columns"] and column not in renamed_sources]
                result_headers, _ = execute_recipe(recipe, headers, rows)
                preserved = all(column in result_headers for column in extras)
                results.append({"fixture": input_path.name, "status": "PASS" if preserved else "FAIL", "check": "extra_column_preservation", "details": "Declared extra columns remain in the output."})
        except MoltError as exc:
            results.append({"fixture": input_path.name, "status": "FAIL", "check": "extra_column_preservation", "details": exc.message, "context": {key: value for key, value in exc.details.items() if key != "value"}})
    passed = sum(result["status"] in {"PASS", "SKIP"} for result in results)
    failed = sum(result["status"] == "FAIL" for result in results)
    return {"status": "PASS" if failed == 0 else "FAIL", "checks_total": len(results), "checks_passed": passed, "checks_failed": failed, "results": results}


def operation_diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_ops = before.get("operations", [])
    after_ops = after.get("operations", [])
    diff: list[str] = []
    for index in range(max(len(before_ops), len(after_ops))):
        left = before_ops[index] if index < len(before_ops) else None
        right = after_ops[index] if index < len(after_ops) else None
        if left != right:
            diff.append(f"operation {index + 1}: {json.dumps(left, sort_keys=True)} -> {json.dumps(right, sort_keys=True)}")
    return diff


def safe_name(value: str) -> str:
    """Return a filename-safe label for reports; never use it as a path."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "item"


def formula_injection_warnings(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        columns = [column for column, value in row.items() if isinstance(value, str) and value.startswith(("=", "+", "-", "@"))]
        if columns:
            warnings.append({"row": row_number, "columns": columns, "message": "Value may be interpreted as a spreadsheet formula when opened."})
    return warnings
