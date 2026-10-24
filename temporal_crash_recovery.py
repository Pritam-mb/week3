"""Run a real local Temporal workflow with one injected activity failure.

This is an evidence-producing integration check. It starts Temporal's local
development server through the Temporal Python test environment, runs Molt's
real workflow and activity, injects one checkpointed failure after step 1, and
lets Temporal retry the activity. Only aggregate results are written.
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from temporalio.testing import WorkflowEnvironment
from temporalio.api.enums.v1 import EventType
from temporalio.worker import Worker
from temporalio.worker.workflow_sandbox import SandboxRestrictions, SandboxedWorkflowRunner

from molt.application import MoltService
from molt.config import MoltConfig
from molt.temporal import MoltApprovedRunWorkflow, build_run_request, molt_execute_activity


ROOT = Path(__file__).resolve().parent
TASK_QUEUE = "molt-crash-evidence"


def _event_type(event: Any) -> str:
    return EventType.Name(event.event_type).removeprefix("EVENT_TYPE_")


def activity_attempts(history: list[Any]) -> int:
    # Intermediate activity retries may be omitted from history. The final
    # started event's attempt field, not a count of events, is authoritative
    # for this workflow's single activity.
    return max((event.activity_task_started_event_attributes.attempt for event in history
                if event.event_type == EventType.EVENT_TYPE_ACTIVITY_TASK_STARTED), default=0)


async def run() -> dict[str, Any]:
    if MoltApprovedRunWorkflow is None or molt_execute_activity is None:
        raise RuntimeError("Temporal SDK is unavailable")

    with tempfile.TemporaryDirectory(prefix="molt-temporal-crash-") as directory:
        root = Path(directory)
        config = MoltConfig(root)
        service = MoltService(config)
        source = config.input_dir / "golden.csv"
        source.write_bytes((ROOT / "examples/input/golden.csv").read_bytes())
        automation = service.create_automation("Temporal crash recovery", "Evidence workflow")
        version = service.generate_candidate(
            automation["id"],
            "Normalize the fixture",
            service.profile(source),
            recipe_file=str(ROOT / "examples/recipes/expense-v1.json"),
        )
        verification = service.verify_version(version["id"])
        if verification["status"] != "PASS":
            raise RuntimeError("Fixture recipe did not pass verification")
        service.approve_version(version["id"])
        request = build_run_request(root, automation["id"], source)
        workflow_id = "molt-crash-recovery-evidence"
        previous = os.environ.get("MOLT_CRASH_AT")
        os.environ["MOLT_CRASH_AT"] = "1"
        try:
            async with await WorkflowEnvironment.start_local(dev_server_log_level="never") as environment:
                worker = Worker(
                    environment.client,
                    task_queue=TASK_QUEUE,
                    workflows=[MoltApprovedRunWorkflow],
                    activities=[molt_execute_activity],
                    workflow_runner=SandboxedWorkflowRunner(
                        restrictions=SandboxRestrictions.default.with_passthrough_modules("molt.temporal")
                    ),
                )
                async with worker:
                    result = await environment.client.execute_workflow(
                        MoltApprovedRunWorkflow.run,
                        request,
                        id=workflow_id,
                        task_queue=TASK_QUEUE,
                    )
                    handle = environment.client.get_workflow_handle(workflow_id)
                    history = [event async for event in handle.fetch_history_events()]
        finally:
            if previous is None:
                os.environ.pop("MOLT_CRASH_AT", None)
            else:
                os.environ["MOLT_CRASH_AT"] = previous

        attempts = activity_attempts(history)
        checkpoint_state = list(config.checkpoints_dir.glob("*/state.json"))
        return {
            "status": "COMPLETE" if result.get("status") == "SUCCEEDED" and attempts >= 2 else "FAILED",
            "workflow": {
                "result_status": result.get("status"),
                "temporal_outcome": result.get("temporal_outcome"),
                "llm_calls": result.get("llm_calls"),
                "rows_read": result.get("rows_read"),
                "rows_written": result.get("rows_written"),
            },
            "failure_injection": {
                "mode": "MOLT_CRASH_AT",
                "after_step": 1,
                "activity_attempts": attempts,
                "history_event_types": [_event_type(event) for event in history],
                "checkpoint_created": bool(checkpoint_state),
                "checkpoint_resumed": result.get("status") == "SUCCEEDED" and attempts >= 2,
            },
            "claim_boundary": "Real local Temporal server and worker workflow; one injected activity failure and Temporal retry. Not a production durability claim.",
        }


def main() -> int:
    result = asyncio.run(run())
    evidence = ROOT / "evidence" / "temporal-crash-recovery.json"
    evidence.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
