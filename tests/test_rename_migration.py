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

    None of these tests call the real thing on a real machine. An earlier
    version did, and deleting a scheduled task is not something a test run
    should do to the person running it — the same mistake as reading the real
    %APPDATA% folder, one layer down.
    """

    def setUp(self) -> None:
        from netvitals import autostart
        self.autostart = autostart
        self._is_windows = autostart.IS_WINDOWS
        self._run = autostart._run

    def tearDown(self) -> None:
        self.autostart.IS_WINDOWS = self._is_windows
        self.autostart._run = self._run

    def pretend(self, windows: bool, task_exists: bool,
                delete_works: bool = True) -> list[list[str]]:
        """Stand in for schtasks. Returns the commands it was asked to run."""
        calls: list[list[str]] = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            if "/Query" in args:
                return (0 if task_exists else 1), ""
            if "/Delete" in args:
                return (0 if delete_works else 1), ""
            return 1, ""

        self.autostart.IS_WINDOWS = windows
        self.autostart._run = fake_run
        return calls

    def test_it_does_nothing_off_windows(self) -> None:
        self.pretend(windows=False, task_exists=True)
        self.assertFalse(self.autostart.clear_former_autostart())

    def test_it_removes_a_former_task_when_one_exists(self) -> None:
        calls = self.pretend(windows=True, task_exists=True)
        self.assertTrue(self.autostart.clear_former_autostart())
        deletes = [c for c in calls if "/Delete" in c]
        self.assertTrue(deletes, "nothing was deleted")
        self.assertIn(self.autostart.FORMER_TASK_NAME, deletes[0])

    def test_it_never_touches_the_current_task(self) -> None:
        # Removing our own startup entry while tidying up the old one would
        # be a spectacular own goal.
        calls = self.pretend(windows=True, task_exists=True)
        self.autostart.clear_former_autostart()
        for call in calls:
            self.assertNotIn(self.autostart.TASK_NAME, call)

    def test_a_missing_task_is_not_an_error(self) -> None:
        calls = self.pretend(windows=True, task_exists=False)
        self.autostart.clear_former_autostart()
        self.assertFalse([c for c in calls if "/Delete" in c],
                         "tried to delete a task that does not exist")

    def test_a_failed_delete_is_reported_as_nothing_removed(self) -> None:
        self.pretend(windows=True, task_exists=True, delete_works=False)
        self.assertFalse(self.autostart.clear_former_autostart())

    def test_the_former_names_are_the_ones_actually_used_before(self) -> None:
        self.assertEqual(self.autostart.FORMER_TASK_NAME, "NetPulse")
        self.assertEqual(self.autostart.FORMER_APP_KEY, "NetPulse")
        self.assertNotEqual(self.autostart.TASK_NAME,
                            self.autostart.FORMER_TASK_NAME)


if __name__ == "__main__":
    unittest.main()
