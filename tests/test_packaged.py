"""The Microsoft Store build.

One codebase serves both builds, so what differs is decided at runtime by
asking Windows whether this process is packaged. A packaged app runs at medium
integrity with no route to elevation and a read-only install directory, so
every feature that depends on either has to notice and say something the user
can actually act on.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from netpulse import autostart, config                  # noqa: E402
from netpulse.config import PROJECT_URL, Settings       # noqa: E402
from netpulse.db import Database                        # noqa: E402
from netpulse.engine import Engine                      # noqa: E402
from netpulse.ui import pages                           # noqa: E402


class PackagedFlag:
    """Set the packaged state for the duration of a test."""

    def __init__(self, test, packaged: bool) -> None:
        config._packaged = packaged
        test.addCleanup(setattr, config, "_packaged", None)


class DetectionTests(unittest.TestCase):
    def tearDown(self) -> None:
        config._packaged = None

    def test_an_ordinary_process_is_not_packaged(self) -> None:
        config._packaged = None
        os.environ.pop("NETPULSE_PACKAGED", None)
        self.assertFalse(config.is_packaged())

    def test_the_override_is_honoured_for_testing(self) -> None:
        config._packaged = None
        os.environ["NETPULSE_PACKAGED"] = "1"
        self.addCleanup(os.environ.pop, "NETPULSE_PACKAGED", None)
        self.assertTrue(config.is_packaged())

    def test_a_falsey_override_means_not_packaged(self) -> None:
        for value in ("", "0", "false"):
            config._packaged = None
            os.environ["NETPULSE_PACKAGED"] = value
            self.assertFalse(config.is_packaged(), value)
        os.environ.pop("NETPULSE_PACKAGED", None)

    def test_the_answer_is_cached(self) -> None:
        config._packaged = True
        self.assertTrue(config.is_packaged())
        self.assertTrue(config.is_packaged())


class AutostartTests(unittest.TestCase):
    def test_it_does_not_claim_to_control_startup(self) -> None:
        PackagedFlag(self, True)
        ok, message = autostart.set_enabled(True)
        self.assertFalse(ok)
        self.assertIn("Task Manager", message)

    def test_it_says_where_windows_keeps_the_switch(self) -> None:
        PackagedFlag(self, True)
        text = autostart.describe()
        self.assertIn("Startup apps", text)
        # Advice that cannot be followed is worse than none: a Store app has
        # no scheduled task and cannot make one.
        self.assertNotIn("scheduled task", text.lower())

    def test_the_desktop_build_is_unchanged(self) -> None:
        PackagedFlag(self, False)
        self.assertNotIn("Store", autostart.describe())


class UiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netpulse-pkg-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self.settings = Settings()

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def engine(self) -> Engine:
        return Engine(self.db, self.settings)

    def test_the_elevation_button_never_appears(self) -> None:
        PackagedFlag(self, True)
        page = pages.AppsPage(self.db, self.engine(), self.settings)
        page.refresh()
        self.assertFalse(page.restart_button.isVisible())
        self.assertFalse(page.restart_button.isVisibleTo(page))

    def test_it_points_at_the_desktop_build_instead(self) -> None:
        PackagedFlag(self, True)
        page = pages.AppsPage(self.db, self.engine(), self.settings)
        page.refresh()
        self.assertTrue(page.get_desktop_button.isVisibleTo(page))

    def test_the_desktop_build_keeps_its_elevation_button(self) -> None:
        PackagedFlag(self, False)
        self.settings.set("track_per_app", True)
        page = pages.AppsPage(self.db, self.engine(), self.settings)
        page.refresh()
        self.assertFalse(page.get_desktop_button.isVisibleTo(page))

    def test_the_note_blames_the_platform_not_the_user(self) -> None:
        PackagedFlag(self, True)
        # The setting being off must not be reported as the reason: in a Store
        # build it is irrelevant, and it sends the user hunting for a switch.
        self.settings.set("track_per_app", False)
        note = self.engine().per_app_note()
        self.assertIn("Store build", note)
        self.assertNotIn("switched off in Settings", note)

    def test_the_per_app_switch_is_disabled_not_merely_unticked(self) -> None:
        PackagedFlag(self, True)
        page = pages.SettingsPage(self.db, self.engine(), self.settings)
        self.assertFalse(page.per_app_check.isEnabled())
        self.assertFalse(page.autostart_check.isEnabled())

    def test_disabling_it_does_not_rewrite_the_user_setting(self) -> None:
        PackagedFlag(self, True)
        self.settings.set("track_per_app", True)
        pages.SettingsPage(self.db, self.engine(), self.settings)
        self.assertTrue(self.settings.get("track_per_app"),
                        "the Store build changed a setting the user did not")

    def test_the_project_url_is_offered_somewhere_reachable(self) -> None:
        PackagedFlag(self, True)
        engine = self.engine()
        engine.etw.available = False
        engine.etw.start()
        self.assertIn(PROJECT_URL, engine.etw.reason)


if __name__ == "__main__":
    unittest.main()
