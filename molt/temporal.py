"""Optional Temporal boundary for durable Molt executions.

The normal CLI, HTTP API, and deterministic service do not import or require
the Temporal SDK.  Only this module owns that optional dependency.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from .core import MoltError, safe_name


try:  # The opt-in branch is only loaded when temporalio is installed.
    from temporalio import activity as _activity
    from temporalio import workflow as _workflow
    from temporalio.client import Client as _TemporalClient
    from temporalio.common import RetryPolicy as _RetryPolicy
    from temporalio.exceptions import ApplicationError as _ApplicationError
    from temporalio.worker import Worker as _TemporalWorker

    _TEMPORAL_IMPORT_ERROR: ImportError | None = None
except ImportError as exc:
    _activity = None
    _workflow = None
    _TemporalClient = None
    _RetryPolicy = None
    _ApplicationError = None
    _TemporalWorker = None
    _TEMPORAL_IMPORT_ERROR = exc


def _env_value(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    env_file = Path(os.environ.get("MOLT_ENV_FILE", ".env"))
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, item = line.split("=", 1)
                if key.strip() == name:
                    return item.strip().strip('"').strip("'")
    return default


TEMPORAL_TASK_QUEUE = _env_value("MOLT_TEMPORAL_TASK_QUEUE", "molt")
TEMPORAL_ADDRESS = _env_value("MOLT_TEMPORAL_ADDRESS", "127.0.0.1:7233")
TEMPORAL_NAMESPACE = _env_value("MOLT_TEMPORAL_NAMESPACE", "default")

_DRIFT_CODES = {
    "DRIFT_BLOCKED",
    "REQUIRED_COLUMN_MISSING",
    "UNMAPPED_VALUE",
    "INPUT_TYPE_MISMATCH",
    "INVARIANT_FAILED",
}
_NON_RETRYABLE_CODES = {
    "APPROVAL_REQUIRED",
    "FILE_ACCESS_DENIED",
    "DUPLICATE_FILE_EVENT",
    "INPUT_LIMIT_EXCEEDED",
    "OUTPUT_WRITE_FAILED",
    "RECIPE_SCHEMA_INVALID",
    "UNSUPPORTED_OPERATION",
}


def temporalio_available() -> bool:
    """Return whether the optional SDK can be imported."""

    return _TEMPORAL_IMPORT_ERROR is None


def require_temporal() -> None:
    """Raise an actionable error without making Temporal a core dependency."""

    if not temporalio_available():
        raise MoltError(
            "TEMPORAL_UNAVAILABLE",
            "Temporal commands require the optional temporalio package. Install it with `pip install -e .[temporal]`.",
            details={"install": "pip install -e .[temporal]", "dependency": "temporalio"},
        )


def default_workflow_id(workspace: str | Path, automation_id: str, input_path: str | Path) -> str:
    """Build a stable ID so a client retry does not create a new workflow."""

    material = f"{Path(workspace).resolve()}:{automation_id}:{Path(input_path).resolve()}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
    return f"molt-run-{safe_name(automation_id)}-{digest}"


def build_run_request(
    workspace: str | Path,
    automation_id: str,
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    activity_timeout_seconds: int = 300,
) -> dict[str, Any]:
    """Create the JSON payload shared by the CLI, workflow, and activity."""

    if not automation_id or not str(input_path):
        raise MoltError("TEMPORAL_REQUEST_INVALID", "automation_id and input_path are required.")
    return {
        "workspace": str(Path(workspace).resolve()),
        "automation_id": automation_id,
        "input_path": str(Path(input_path).resolve()),
        "output_path": str(Path(output_path).resolve()) if output_path else None,
        "activity_timeout_seconds": activity_timeout_seconds,
    }


def _drift_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "BLOCKED_DRIFT":
        return result
    return result | {
        "temporal_outcome": "drift",
        "retryable": False,
        "drift": {
            "error_code": result.get("error_code"),
            "message": result.get("error_message"),
            "details": result.get("error_details", {}),
        },
    }


def execute_run_activity(
    request: dict[str, Any],
    *,
    service_factory: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    """Call Molt's existing deterministic service from an activity.

    The service opts into its existing per-operation checkpoint files and
    database idempotency key.  A worker retry resumes or returns the recorded
    run.  Drift is data, so it does not become an activity exception.
    """

    required = {"workspace", "automation_id", "input_path"}
    if not required <= request.keys():
        raise MoltError("TEMPORAL_REQUEST_INVALID", "Temporal run request is missing required fields.")
    # Keep application imports out of the workflow module's import-time path;
    # Temporal's workflow sandbox only needs the JSON workflow definitions.
    from .config import config_from_workspace

    if service_factory is None:
        from .application import MoltService

        service_factory = MoltService
    config = config_from_workspace(request["workspace"])
    service = service_factory(config)
    try:
        result = service.run(
            request["automation_id"],
            request["input_path"],
            output_path=request.get("output_path"),
            use_checkpoints=True,
        )
    except MoltError as exc:
        if exc.code == "DUPLICATE_FILE_EVENT":
            existing_id = exc.details.get("run_id")
            if existing_id:
                replay = _drift_result(service.get_run(existing_id))
                return replay | {"temporal_outcome": "idempotent_replay", "retryable": False}
        if exc.code in _DRIFT_CODES:
            return {
                "status": "BLOCKED_DRIFT",
                "temporal_outcome": "drift",
                "retryable": False,
                "error_code": exc.code,
                "error_message": exc.message,
                "drift": {"error_code": exc.code, "message": exc.message, "details": exc.details},
            }
        raise
    normalized = _drift_result(result)
    return normalized | {"temporal_outcome": normalized.get("temporal_outcome", "completed"), "retryable": False}


if temporalio_available():  # Decorated definitions are absent when the SDK is absent.

    @_activity.defn(name="molt.execute-approved-run")
    async def molt_execute_activity(request: dict[str, Any]) -> dict[str, Any]:
        try:
            # Molt's existing service is synchronous and performs file/SQLite
            # work. Keep that work off Temporal's event loop while exposing an
            # async activity, which the Python SDK requires when no custom
            # activity executor is configured.
            return await asyncio.to_thread(execute_run_activity, request)
        except MoltError as exc:
            if _ApplicationError is not None:
                raise _ApplicationError(
                    exc.message,
                    exc.code,
                    type=exc.code,
                    non_retryable=exc.code in _NON_RETRYABLE_CODES,
                ) from exc
            raise


    @_workflow.defn(name="MoltApprovedRunWorkflow")
    class MoltApprovedRunWorkflow:
        """One durable workflow for one approved-recipe execution."""

        @_workflow.run
        async def run(self, request: dict[str, Any]) -> dict[str, Any]:
            timeout = max(1, int(request.get("activity_timeout_seconds", 300)))
            return await _workflow.execute_activity(
                molt_execute_activity,
                request,
                start_to_close_timeout=timedelta(seconds=timeout),
                retry_policy=_RetryPolicy(
                    initial_interval=timedelta(seconds=1),
                    maximum_interval=timedelta(seconds=30),
                    backoff_coefficient=2.0,
                    maximum_attempts=3,
                ),
            )

else:
    molt_execute_activity = None
    MoltApprovedRunWorkflow = None


async def _worker(*, address: str, namespace: str, task_queue: str, max_concurrent_activities: int) -> None:
    require_temporal()
    assert _TemporalClient is not None and _TemporalWorker is not None
    client = await _TemporalClient.connect(address, namespace=namespace)
    worker = _TemporalWorker(
        client,
        task_queue=task_queue,
        workflows=[MoltApprovedRunWorkflow],
        activities=[molt_execute_activity],
        max_concurrent_activities=max_concurrent_activities,
    )
    await worker.run()


def run_worker(
    *,
    address: str = TEMPORAL_ADDRESS,
    namespace: str = TEMPORAL_NAMESPACE,
    task_queue: str = TEMPORAL_TASK_QUEUE,
    max_concurrent_activities: int = 10,
) -> None:
    """Connect a worker to an already running Temporal server."""

    asyncio.run(_worker(address=address, namespace=namespace, task_queue=task_queue, max_concurrent_activities=max_concurrent_activities))


async def _start_workflow(
    request: dict[str, Any],
    *,
    workflow_id: str,
    address: str,
    namespace: str,
    task_queue: str,
    wait: bool,
) -> dict[str, Any]:
    require_temporal()
    assert _TemporalClient is not None and MoltApprovedRunWorkflow is not None
    client = await _TemporalClient.connect(address, namespace=namespace)
    handle = await client.start_workflow(MoltApprovedRunWorkflow.run, request, id=workflow_id, task_queue=task_queue)
    response: dict[str, Any] = {"workflow_id": handle.id, "run_id": handle.result_run_id}
    if wait:
        response["result"] = await handle.result()
    return response


def start_workflow(
    request: dict[str, Any],
    *,
    workflow_id: str,
    address: str = TEMPORAL_ADDRESS,
    namespace: str = TEMPORAL_NAMESPACE,
    task_queue: str = TEMPORAL_TASK_QUEUE,
    wait: bool = True,
) -> dict[str, Any]:
    """Start one workflow and optionally wait for its activity result."""

    return asyncio.run(_start_workflow(request, workflow_id=workflow_id, address=address, namespace=namespace, task_queue=task_queue, wait=wait))


def start_cli_run(
    *,
    workspace: str | Path,
    automation_id: str,
    input_path: str | Path,
    output_path: str | Path | None,
    workflow_id: str | None,
    address: str,
    namespace: str,
    task_queue: str,
    wait: bool,
    activity_timeout_seconds: int,
) -> dict[str, Any]:
    request = build_run_request(workspace, automation_id, input_path, output_path, activity_timeout_seconds=activity_timeout_seconds)
    return start_workflow(
        request,
        workflow_id=workflow_id or default_workflow_id(workspace, automation_id, input_path),
        address=address,
        namespace=namespace,
        task_queue=task_queue,
        wait=wait,
    )
