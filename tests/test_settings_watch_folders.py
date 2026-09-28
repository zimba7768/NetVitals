"""Watched folders: an empty list must mean "none, on purpose" — not
"unconfigured, please fill in the defaults again."

Removing every default watched folder (Desktop, Documents, Pictures, Videos,
Music) is exactly what someone does to get away from one that turns out to
be a slow network or cloud-sync drive. If that choice does not survive a
restart, the drive that caused the problem in the first place comes right
back the next time the app launches.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netvitals.config import Settings, default_watch_folders


class WatchFoldersPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-settings-")
        self.path = Path(self.dir) / "settings.json"

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_never_configured_gets_the_defaults(self) -> None:
        settings = Settings(path=self.path)
        self.assertEqual(settings.get("watch_folders"), default_watch_folders())

    def test_an_explicit_empty_list_survives_a_reload(self) -> None:
        settings = Settings(path=self.path)
        settings.set("watch_folders", [])
        reloaded = Settings(path=self.path)
        self.assertEqual(reloaded.get("watch_folders"), [])

    def test_a_chosen_subset_survives_a_reload(self) -> None:
        settings = Settings(path=self.path)
        settings.set("watch_folders", [self.dir])
        reloaded = Settings(path=self.path)
        self.assertEqual(reloaded.get("watch_folders"), [self.dir])


if __name__ == "__main__":
    unittest.main()
