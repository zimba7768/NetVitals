"""The Files page: its database query and browser rescan run off the
interface thread, so neither one can freeze the window regardless of how
slow the underlying work turns out to be.
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

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from netvitals.config import Settings                    # noqa: E402
from netvitals.db import Database                        # noqa: E402
from netvitals.engine import Engine                       # noqa: E402
from netvitals.ui import pages                            # noqa: E402


def pump(condition, timeout: float = 5.0) -> bool:
    """Process Qt events until ``condition()`` is true, or give up.

    The page's query runs on a background thread and reports back through a
    signal, so the result only lands once Qt's event loop gets to run —
    exactly what a real application does between frames, and exactly what a
    test has to simulate rather than skip.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return False


class FilesPageAsyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-filespage-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self.settings = Settings()
        self.engine = Engine(self.db, self.settings)
        self.page = pages.FilesPage(self.db, self.engine, self.settings)

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_query_never_runs_on_this_thread(self) -> None:
        # A slow db.recent_files() must not be able to block refresh()
        # itself — only the background thread it hands the call to.
        started = {"value": False}

        def slow_recent_files(**kwargs):
            started["value"] = True
            time.sleep(0.3)
            return []

        self.db.recent_files = slow_recent_files
        before = time.monotonic()
        self.page.refresh()
        elapsed = time.monotonic() - before
        self.assertLess(elapsed, 0.1, "refresh() blocked waiting on the query")
        self.assertTrue(pump(lambda: started["value"]))

    def test_results_populate_the_table_once_the_thread_reports_back(self) -> None:
        self.db.add_file("C:/D/a.zip", "a.zip", "C:/D", 500, ts=time.time())
        self.page.refresh()
        self.assertTrue(pump(lambda: self.page.table.rowCount() == 1))
        self.assertIn("a.zip", self.page.table.item(0, 0).text())

    def test_a_stale_result_does_not_overwrite_a_newer_one(self) -> None:
        # Two requests in flight at once, arriving out of order: the slow
        # first one must not clobber what the fast second one already showed.
        calls = []

        def controlled(**kwargs):
            calls.append(kwargs.get("search", ""))
            if kwargs.get("search") == "slow":
                time.sleep(0.2)
                return [{"path": "C:/D/old.zip", "name": "old.zip", "folder": "C:/D",
                        "size": 1, "ts": time.time(), "source": None, "app": None}]
            return [{"path": "C:/D/new.zip", "name": "new.zip", "folder": "C:/D",
                    "size": 1, "ts": time.time(), "source": None, "app": None}]

        self.db.recent_files = controlled
        self.page.search.setText("slow")
        self.page._search_timer.stop()
        self.page.refresh()                 # request 1, will take 0.2s
        self.page.search.setText("fast")
        self.page._search_timer.stop()
        self.page.refresh()                 # request 2, supersedes request 1

        self.assertTrue(pump(lambda: self.page.table.rowCount() == 1))
        time.sleep(0.25)                    # let the slow one land too, if it's going to
        pump(lambda: False, timeout=0.3)
        self.assertEqual(self.page.table.item(0, 0).text(), "new.zip")

    def test_rescan_disables_the_button_and_runs_off_thread(self) -> None:
        started = {"value": False}

        def slow_scan(lookback_days=365):
            started["value"] = True
            time.sleep(0.2)
            return 3

        self.engine.files.scan_browsers = slow_scan
        # The real completion path shows a modal QMessageBox, which has
        # nothing to dismiss it in a headless test and would hang forever
        # waiting for a click that never comes — stand in for it.
        original_info = pages.QMessageBox.information
        pages.QMessageBox.information = staticmethod(lambda *a, **k: None)
        try:
            self.page._rescan()
            self.assertFalse(self.page.rescan_button.isEnabled())
            self.assertTrue(pump(lambda: self.page.rescan_button.isEnabled()))
        finally:
            pages.QMessageBox.information = original_info
        self.assertTrue(started["value"])

    def test_the_display_cap_is_named_in_the_card_hint(self) -> None:
        # It used to say nothing about the cap, which read as "everything"
        # even though it never was.
        from PySide6.QtWidgets import QLabel
        hints = [w.text() for w in self.page.findChildren(QLabel)
                if w.objectName() == "CardHint"]
        self.assertTrue(any(str(pages.FILES_DISPLAY_LIMIT) in h for h in hints))

    def test_a_full_page_says_there_may_be_more(self) -> None:
        rows = [{"path": f"C:/D/{i}.zip", "name": f"{i}.zip", "folder": "C:/D",
                "size": 1, "ts": time.time(), "source": None, "app": None}
               for i in range(pages.FILES_DISPLAY_LIMIT)]
        self.page._apply_results(self.page._request_id, rows)
        self.assertIn("+", self.page.summary.text())

    def test_a_partial_page_does_not_claim_there_is_more(self) -> None:
        rows = [{"path": "C:/D/a.zip", "name": "a.zip", "folder": "C:/D",
                "size": 1, "ts": time.time(), "source": None, "app": None}]
        self.page._apply_results(self.page._request_id, rows)
        self.assertNotIn("+", self.page.summary.text())


if __name__ == "__main__":
    unittest.main()
