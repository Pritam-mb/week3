from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from molt.application import MoltService
from molt.config import MoltConfig
from molt.watcher import FolderWatcher


ROOT = Path(__file__).resolve().parents[1]


class WatcherTests(unittest.TestCase):
    def test_stable_csv_is_processed_and_archived_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = MoltConfig(Path(directory))
            service = MoltService(config)
            automation = service.create_automation("Watcher", "")
            source = config.input_dir / "incoming.csv"
            shutil.copy2(ROOT / "examples/input/golden.csv", source)
            version = service.generate_candidate(automation["id"], "Normalize", service.profile(source), recipe_file=str(ROOT / "examples/recipes/expense-v1.json"))
            service.verify_version(version["id"])
            service.approve_version(version["id"])
            watcher = FolderWatcher(service, automation["id"], config)
            self.assertEqual(watcher.poll_once(), [])
            result = watcher.poll_once()
            self.assertEqual(result[0]["status"], "SUCCEEDED")
            self.assertFalse(source.exists())
            self.assertTrue(list(config.archive_dir.glob("incoming.csv")))
            self.assertTrue(list(config.done_dir.glob("incoming-*.csv")))


if __name__ == "__main__":
    unittest.main()
