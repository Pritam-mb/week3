from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MoltConfig:
    workspace: Path
    max_file_bytes: int = 10 * 1024 * 1024
    max_rows: int = 100_000
    max_operations: int = 30
    max_recipe_bytes: int = 128 * 1024
    max_execution_seconds: int = 120
    poll_interval_seconds: float = 1.5
    host: str = "127.0.0.1"
    port: int = 8765
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma3:4b"
    ollama_timeout_seconds: float = 30.0
    ollama_max_retries: int = 2
    ollama_max_response_bytes: int = 512 * 1024
    mastra_repair_url: str = "http://127.0.0.1:4112"
    mastra_timeout_seconds: float = 30.0
    local_only: bool = True
    sentry_dsn: str = ""
    tabpfn_enabled: bool = False
    tabpfn_license_accepted: bool = False
    tabpfn_model: str = "default"
    tabpfn_device: str = "auto"
    tabpfn_max_rows: int = 5_000
    temporal_address: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "molt"
    temporal_activity_timeout_seconds: int = 300

    @property
    def database(self) -> Path:
        return self.workspace / "molt.sqlite3"

    @property
    def input_dir(self) -> Path:
        return self.workspace / "in"

    @property
    def done_dir(self) -> Path:
        return self.workspace / "done"

    @property
    def quarantine_dir(self) -> Path:
        return self.workspace / "quarantine"

    @property
    def reports_dir(self) -> Path:
        return self.workspace / "reports"

    @property
    def archive_dir(self) -> Path:
        return self.workspace / "archive"

    @property
    def checkpoints_dir(self) -> Path:
        return self.workspace / "checkpoints"

    @property
    def uploads_dir(self) -> Path:
        return self.workspace / "uploads"

    def prepare(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        for directory in (self.input_dir, self.done_dir, self.quarantine_dir, self.reports_dir, self.archive_dir, self.checkpoints_dir, self.uploads_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def as_public_dict(self) -> dict[str, object]:
        return {
            "workspace": str(self.workspace), "host": self.host, "port": self.port,
            "ollama_base_url": self.ollama_base_url, "ollama_model": self.ollama_model,
            "ollama_timeout_seconds": self.ollama_timeout_seconds, "ollama_max_retries": self.ollama_max_retries,
            "mastra_repair_url": self.mastra_repair_url, "mastra_timeout_seconds": self.mastra_timeout_seconds,
            "max_file_bytes": self.max_file_bytes, "max_rows": self.max_rows,
            "local_only": self.local_only, "sentry_configured": bool(self.sentry_dsn),
            "tabpfn_enabled": self.tabpfn_enabled, "tabpfn_license_accepted": self.tabpfn_license_accepted,
            "tabpfn_model": self.tabpfn_model, "tabpfn_device": self.tabpfn_device, "tabpfn_max_rows": self.tabpfn_max_rows,
            "temporal": {"address": self.temporal_address, "namespace": self.temporal_namespace, "task_queue": self.temporal_task_queue, "activity_timeout_seconds": self.temporal_activity_timeout_seconds},
        }


def _env_file_values() -> dict[str, str]:
    values: dict[str, str] = {}
    env_file = Path(os.environ.get("MOLT_ENV_FILE", ".env"))
    if not env_file.is_file():
        return values
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _value(name: str, values: dict[str, str], default: str) -> str:
    # An empty process variable is commonly left behind by shell setup and
    # should not hide a deliberate value from the workspace .env file.
    process_value = os.environ.get(name)
    if process_value:
        return process_value
    return values.get(name, default)


def _int(name: str, values: dict[str, str], default: int) -> int:
    return int(_value(name, values, str(default)))


def _float(name: str, values: dict[str, str], default: float) -> float:
    return float(_value(name, values, str(default)))


def _bool(name: str, values: dict[str, str], default: bool) -> bool:
    return _value(name, values, str(default)).lower() in {"1", "true", "yes", "on"}


def config_from_workspace(path: str | Path | None = None) -> MoltConfig:
    values = _env_file_values()
    workspace = Path(path or _value("MOLT_DATA_DIR", values, _value("MOLT_WORKSPACE", values, "workspace"))).resolve()
    return MoltConfig(
        workspace=workspace,
        max_file_bytes=_int("MOLT_MAX_UPLOAD_MB", values, 10) * 1024 * 1024,
        max_rows=_int("MOLT_MAX_ROWS", values, 100_000),
        max_operations=_int("MOLT_MAX_OPERATIONS", values, 30),
        max_recipe_bytes=_int("MOLT_MAX_RECIPE_KB", values, 128) * 1024,
        max_execution_seconds=_int("MOLT_MAX_EXECUTION_SECONDS", values, 120),
        poll_interval_seconds=_float("MOLT_POLL_INTERVAL_SECONDS", values, 1.5),
        host=_value("MOLT_HOST", values, "127.0.0.1"),
        port=_int("MOLT_PORT", values, 8765),
        ollama_base_url=_value("OLLAMA_BASE_URL", values, "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=_value("MOLT_GEMMA_MODEL", values, "gemma3:4b"),
        ollama_timeout_seconds=_float("MOLT_MODEL_TIMEOUT_SECONDS", values, 30.0),
        ollama_max_retries=_int("MOLT_MODEL_MAX_RETRIES", values, 2),
        ollama_max_response_bytes=_int("MOLT_MODEL_MAX_RESPONSE_KB", values, 512) * 1024,
        mastra_repair_url=_value("MOLT_MASTRA_REPAIR_URL", values, "http://127.0.0.1:4112").rstrip("/"),
        mastra_timeout_seconds=_float("MOLT_MASTRA_TIMEOUT_SECONDS", values, 30.0),
        local_only=_bool("MOLT_LOCAL_ONLY", values, True),
        sentry_dsn=_value("SENTRY_DSN", values, ""),
        tabpfn_enabled=_bool("MOLT_TABPFN_ENABLED", values, False),
        tabpfn_license_accepted=_bool("MOLT_TABPFN_LICENSE_ACCEPTED", values, False),
        tabpfn_model=_value("MOLT_TABPFN_MODEL", values, "default"),
        tabpfn_device=_value("MOLT_TABPFN_DEVICE", values, "auto"),
        tabpfn_max_rows=_int("MOLT_TABPFN_MAX_ROWS", values, 5_000),
        temporal_address=_value("MOLT_TEMPORAL_ADDRESS", values, "127.0.0.1:7233"),
        temporal_namespace=_value("MOLT_TEMPORAL_NAMESPACE", values, "default"),
        temporal_task_queue=_value("MOLT_TEMPORAL_TASK_QUEUE", values, "molt"),
        temporal_activity_timeout_seconds=_int("MOLT_TEMPORAL_ACTIVITY_TIMEOUT_SECONDS", values, 300),
    )
