from __future__ import annotations

import time
from pathlib import Path

from .application import MoltService
from .config import MoltConfig
from .core import MoltError, fingerprint_file


class FolderWatcher:
    def __init__(self, service: MoltService, automation_id: str, config: MoltConfig):
        self.service = service
        self.automation_id = automation_id
        self.config = config
        self.observed: dict[Path, tuple[int, int]] = {}

    def poll_once(self) -> list[dict]:
        results = []
        self.config.input_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.config.input_dir.glob("*.csv")):
            if path.name.startswith(".") or path.suffix.lower() != ".csv" or path.is_symlink():
                continue
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            previous = self.observed.get(path)
            self.observed[path] = signature
            if previous != signature:
                continue
            try:
                result = self.service.run(self.automation_id, path)
            except MoltError as exc:
                result = {"status": "FAILED", "error_code": exc.code, "error_message": exc.message, "input": str(path)}
            results.append(result)
            if result.get("status") == "SUCCEEDED":
                archive = self.config.archive_dir / path.name
                if not archive.exists():
                    path.replace(archive)
            elif result.get("status") == "BLOCKED_DRIFT":
                if path.exists():
                    quarantine = self.config.quarantine_dir / f"{path.stem}-{fingerprint_file(path)}{path.suffix}"
                    if not quarantine.exists():
                        path.replace(quarantine)
        return results

    def run_forever(self) -> None:
        print(f"Watching {self.config.input_dir} for automation {self.automation_id}")
        try:
            while True:
                self.poll_once()
                time.sleep(self.config.poll_interval_seconds)
        except KeyboardInterrupt:
            print("\nWatcher stopped.")
