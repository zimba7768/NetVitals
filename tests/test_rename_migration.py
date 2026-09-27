"""Carrying a user's data across the NetPulse → NetVitals rename.

Renaming an application renames its data folder with it. Left alone, that
silently orphans everything the user collected: the app looks brand new, and a
year of history sits on disk where nothing will ever read it again. These tests
exist because that failure is invisible — nothing errors, the numbers are
simply gone.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netvitals import config  # noqa: E402


class DataAdoptionTests(unittest.TestCase):
    #: Every environment variable that can steer the data folder. Setting only
    #: HOME looks right on Linux and does nothing on Windows, where Path.home()
    #: reads USERPROFILE and the data folder comes from APPDATA — so the tests
    #: silently ran against the real folder instead of a temporary one.
    HOME_VARS = ("HOME", "USERPROFILE", "APPDATA")

    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp(prefix="netvitals-home-"))
        self._saved = {name: os.environ.get(name) for name in self.HOME_VARS}
        self._override = os.environ.pop("NETVITALS_DATA_DIR", None)
        for name in self.HOME_VARS:
            os.environ[name] = str(self.home)
        importlib.reload(config)
        # Verify without creating anything: calling data_dir() here would both
        # make the folder and spend the one adoption check.
        assert self.home in self.expected_target().parents, self.expected_target()

    def tearDown(self) -> None:
        for name, value in self._saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        if self._override is not None:
            os.environ["NETVITALS_DATA_DIR"] = self._override
        shutil.rmtree(self.home, ignore_errors=True)
        importlib.reload(config)

    def expected_target(self) -> Path:
        """Where data_dir() should resolve to, computed without side effects."""
        if config.IS_WINDOWS:
            return self.home / config.APP_NAME
        return self.home / ".local" / "share" / config.APP_NAME.lower()

    def former(self) -> Path:
        """The pre-rename folder, wherever this platform would put it."""
        if config.IS_WINDOWS:
            old = self.home / config.FORMER_APP_NAME
        else:
            old = self.home / ".local" / "share" / config.FORMER_APP_NAME.lower()
        old.mkdir(parents=True, exist_ok=True)
        return old

    def test_the_database_comes_across_under_its_new_name(self) -> None:
        (self.former() / "netpulse.db").write_bytes(b"SQLite format 3\x00data")
        target = config.data_dir()
        self.assertTrue((target / "netvitals.db").is_file())
        self.assertIn(b"SQLite format 3", (target / "netvitals.db").read_bytes())

    def test_settings_and_logs_come_across(self) -> None:
        old = self.former()
        (old / "settings.json").write_text('{"units": "auto"}')
        (old / "wanip.log").write_text("earlier lookups\n")
        target = config.data_dir()
        self.assertIn("auto", (target / "settings.json").read_text())
        self.assertIn("earlier", (target / "wanip.log").read_text())

    def test_nested_folders_come_across(self) -> None:
        assets = self.former() / "assets"
        assets.mkdir()
        (assets / "check.png").write_bytes(b"png")
        self.assertTrue((config.data_dir() / "assets" / "check.png").is_file())

    def test_the_old_folder_is_left_untouched(self) -> None:
        # Copy, never move: if anything goes wrong the user still has their
        # data where it was, and the worst case is starting empty rather than
        # losing a year of history.
        old = self.former()
        (old / "netpulse.db").write_bytes(b"data")
        config.data_dir()
        self.assertTrue((old / "netpulse.db").is_file())

    def test_existing_data_is_never_overwritten(self) -> None:
        # Someone who already ran NetVitals must not have it clobbered by a
        # stale NetPulse folder sitting alongside.
        (self.former() / "netpulse.db").write_bytes(b"old")
        target = self.expected_target()
        target.mkdir(parents=True)
        (target / "netvitals.db").write_bytes(b"current")
        self.assertEqual(config.data_dir().joinpath("netvitals.db").read_bytes(),
                         b"current")

    def test_a_fresh_install_with_no_history_is_fine(self) -> None:
        target = config.data_dir()
        self.assertTrue(target.is_dir())
        self.assertEqual(list(target.iterdir()), [])

    def test_an_explicit_override_is_left_alone(self) -> None:
        # NETVITALS_DATA_DIR means the caller has chosen the path; adopting a
        # folder into it would be surprising.
        chosen = self.home / "chosen"
        os.environ["NETVITALS_DATA_DIR"] = str(chosen)
        self.addCleanup(os.environ.pop, "NETVITALS_DATA_DIR", None)
        (self.former() / "netpulse.db").write_bytes(b"old")
        self.assertEqual(config.data_dir(), chosen)
        self.assertFalse((chosen / "netvitals.db").exists())


class FormerAutostartTests(unittest.TestCase):
    """The pre-rename startup entry must not be left behind.

    Windows keeps both names happily, so an upgrade would start the app twice:
    once as NetVitals, once as NetPulse from wherever that copy used to live.
    """

    def test_it_reports_nothing_removed_off_windows(self) -> None:
        from netvitals import autostart
        self.assertFalse(autostart.clear_former_autostart())

    def test_the_former_names_are_the_ones_actually_used_before(self) -> None:
        from netvitals import autostart
        self.assertEqual(autostart.FORMER_TASK_NAME, "NetPulse")
        self.assertEqual(autostart.FORMER_APP_KEY, "NetPulse")
        self.assertNotEqual(autostart.TASK_NAME, autostart.FORMER_TASK_NAME)


if __name__ == "__main__":
    unittest.main()
