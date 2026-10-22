from __future__ import annotations

from .core import MoltError


RECIPE_TRANSITIONS = {
    "DRAFT": {"VERIFYING", "REJECTED"},
    "VERIFYING": {"AWAITING_APPROVAL", "REJECTED"},
    "AWAITING_APPROVAL": {"ACTIVE", "REJECTED"},
    "ACTIVE": {"ARCHIVED"},
    "REJECTED": set(),
    "ARCHIVED": set(),
}

RUN_TRANSITIONS = {
    "QUEUED": {"PROFILING", "CANCELLED"},
    "PROFILING": {"PRECONDITION_CHECK", "FAILED", "CANCELLED"},
    "PRECONDITION_CHECK": {"EXECUTING", "BLOCKED_DRIFT", "FAILED", "CANCELLED"},
    "EXECUTING": {"OUTPUT_VALIDATION", "FAILED", "CANCELLED"},
    "OUTPUT_VALIDATION": {"SUCCEEDED", "FAILED"},
    "BLOCKED_DRIFT": {"QUARANTINED"},
    "QUARANTINED": set(),
    "SUCCEEDED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}


def transition(current: str, target: str, *, kind: str) -> str:
    graph = RECIPE_TRANSITIONS if kind == "recipe" else RUN_TRANSITIONS
    if target not in graph.get(current, set()):
        raise MoltError("INVALID_STATE_TRANSITION", f"Cannot transition {kind} from {current} to {target}.")
    return target
