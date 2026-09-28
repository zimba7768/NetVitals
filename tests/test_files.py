"""Browser-history merging, and the fix for the multi-minute UI freeze it
could cause on a large, already-logged file library.

Every one of these files is on record already; the only new information a
periodic browser-history scan has to offer is a source for a handful of rows
that do not have one yet. Re-verifying (``getsize``, ``isfile``) thousands of
already-logged paths from disk on every 60-second pass is pure waste even on
a fast local disk, and on a folder synced by OneDrive or similar — where a
single stat can block on the cloud rather than answer from a local index —
it is what turned "waste" into "the window says Not Responding for minutes."
The fix is to know what is already logged *before* touching the filesystem,
so only genuinely new paths ever reach a stat call.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netvitals.collectors import files as files_module
from netvitals.collectors.files import FileTracker
from netvitals.db import Database

class FakeSettings:
    """Just enough of Settings for FileTracker's own reads."""

    def __init__(self, **overrides) -> None:
        self._data = {"min_file_bytes": 0, "ignore_extensions": [], "paused": False}
        self._data.update(overrides)

    def get(self, key, default=None):
        return self._data.get(key, default)


class MergeRecordTests(unittest.TestCase):
    """The per-record fast path that skips the filesystem for known paths."""

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-files-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self.settings = FakeSettings()
        self.tracker = FileTracker(self.db, self.settings)
        self.stat_calls: list[str] = []
        self._real_getsize = os.path.getsize
        self._real_isfile = os.path.isfile

        def spy_getsize(path):
            self.stat_calls.append(("getsize", path))
            return self._real_getsize(path)

        def spy_isfile(path):
            self.stat_calls.append(("isfile", path))
            return self._real_isfile(path)

        files_module.os.path.getsize = spy_getsize
        files_module.os.path.isfile = spy_isfile

    def tearDown(self) -> None:
        files_module.os.path.getsize = self._real_getsize
        files_module.os.path.isfile = self._real_isfile
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_known_path_never_touches_the_filesystem(self) -> None:
        # Already in the file log — from the folder watcher, most likely —
        # so nothing on disk needs checking again.
        self.db.add_file("C:/Downloads/movie.mkv", "movie.mkv",
                         "C:/Downloads", 900, ts=time.time())
        rec = {"path": "C:/Downloads/movie.mkv", "size": 0, "ts": time.time(),
              "url": "https://example.com/movie.mkv"}
        result = self.tracker._merge_record(rec, "Chrome", {"C:/Downloads/movie.mkv"})
        self.assertEqual(result, 0)
        self.assertEqual(self.stat_calls, [])

    def test_a_known_path_still_gets_its_source_filled_in(self) -> None:
        self.db.add_file("C:/Downloads/movie.mkv", "movie.mkv",
                         "C:/Downloads", 900, ts=time.time())
        rec = {"path": "C:/Downloads/movie.mkv", "size": 0, "ts": time.time(),
              "url": "https://example.com/movie.mkv"}
        self.tracker._merge_record(rec, "Chrome", {"C:/Downloads/movie.mkv"})
        row = self.db.recent_files(limit=1)[0]
        self.assertEqual(row["source"], "example.com")

    def test_an_unknown_path_is_still_verified_on_disk(self) -> None:
        target = os.path.join(self.dir, "fresh.zip")
        with open(target, "wb") as fh:
            fh.write(b"x" * 128)
        rec = {"path": target, "size": 0, "ts": time.time(), "url": ""}
        result = self.tracker._merge_record(rec, "Chrome", set())
        self.assertEqual(result, 1)
        self.assertIn(("isfile", target), self.stat_calls)

    def test_an_unknown_missing_file_is_skipped_without_error(self) -> None:
        rec = {"path": os.path.join(self.dir, "ghost.zip"), "size": 0,
              "ts": time.time(), "url": ""}
        self.assertEqual(self.tracker._merge_record(rec, "Chrome", set()), 0)


class ReadFirefoxTests(unittest.TestCase):
    """The Firefox reader is the one that used to stat every row while
    just *reading* history, before a record ever reached the merge step."""

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-ff-")
        self.dbfile = Path(self.dir) / "places.sqlite"
        conn = sqlite3.connect(self.dbfile)
        conn.executescript("""
            CREATE TABLE moz_places (id INTEGER PRIMARY KEY, url TEXT);
            CREATE TABLE moz_anno_attributes (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE moz_annos (
                place_id INTEGER, anno_attribute_id INTEGER,
                content TEXT, dateAdded INTEGER);
        """)
        conn.execute("INSERT INTO moz_places VALUES (1, 'https://example.com/a.zip')")
        conn.execute(
            "INSERT INTO moz_anno_attributes VALUES (1, 'downloads/destinationFileURI')")
        now_micro = int(time.time() * 1_000_000)
        conn.execute(
            "INSERT INTO moz_annos VALUES (1, 1, ?, ?)",
            ("file:///C:/Downloads/a.zip", now_micro))
        conn.commit()
        conn.close()

    def tearDown(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_known_path_is_not_stat_d(self) -> None:
        # Read what the function itself would normalise the path to, rather
        # than hard-coding a separator that only matches one platform.
        expected_path = os.path.normpath("C:/Downloads/a.zip")

        calls: list[str] = []
        real_getsize = os.path.getsize
        files_module.os.path.getsize = lambda p: (calls.append(p), real_getsize(p))[1]
        try:
            records = FileTracker._read_firefox(self.dbfile, 0.0, {expected_path})
        finally:
            files_module.os.path.getsize = real_getsize
        self.assertEqual(calls, [])
        self.assertEqual(records[0]["path"], expected_path)
        self.assertEqual(records[0]["size"], 0)

    def test_an_unknown_path_is_attempted_on_disk(self) -> None:
        # The fixture path does not exist here, so the stat fails — what
        # matters is that it is *attempted* rather than skipped, unlike the
        # known-path case above.
        calls: list[str] = []
        real_getsize = os.path.getsize
        files_module.os.path.getsize = lambda p: (calls.append(p), real_getsize(p))[1]
        try:
            records = FileTracker._read_firefox(self.dbfile, 0.0, set())
        finally:
            files_module.os.path.getsize = real_getsize
        self.assertEqual(len(records), 1)
        self.assertEqual(len(calls), 1)


class StartupTests(unittest.TestCase):
    """Folder-watch setup must never be able to block the caller of start().

    At application launch the caller is the interface thread, before the
    window is even shown — exactly where a stalled network or cloud-virtual
    drive turning a plain isdir() into a multi-second wait would be most
    damaging.
    """

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-startup-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self._real_isdir = os.path.isdir

    def tearDown(self) -> None:
        files_module.os.path.isdir = self._real_isdir
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_start_returns_immediately_even_when_a_folder_check_is_slow(self) -> None:
        slow_root = os.path.join(self.dir, "slow-drive")
        os.makedirs(slow_root, exist_ok=True)
        real_isdir = self._real_isdir

        def slow_isdir(path):
            if path == slow_root:
                time.sleep(0.3)
            return real_isdir(path)

        files_module.os.path.isdir = slow_isdir
        settings = FakeSettings(watch_folders=[slow_root])
        tracker = FileTracker(self.db, settings)
        try:
            before = time.monotonic()
            tracker.start()
            elapsed = time.monotonic() - before
            self.assertLess(elapsed, 0.1,
                            "start() waited on the folder check itself")
        finally:
            tracker.stop()

    def test_status_eventually_reports_what_start_found(self) -> None:
        root = os.path.join(self.dir, "watched")
        os.makedirs(root, exist_ok=True)
        settings = FakeSettings(watch_folders=[root])
        tracker = FileTracker(self.db, settings)
        tracker.start()
        try:
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and tracker.status == "starting…":
                time.sleep(0.01)
            self.assertNotEqual(tracker.status, "starting…")
        finally:
            tracker.stop()
        self.assertEqual(tracker.status, "stopped")


class ScanBrowsersTests(unittest.TestCase):
    """The pass as a whole: one known-paths lookup, not one per record."""

    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-scan-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self.settings = FakeSettings()
        self.tracker = FileTracker(self.db, self.settings)

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_known_paths_is_read_once_per_scan_not_per_record(self) -> None:
        calls = []
        real = self.db.known_paths

        def counting(*a, **k):
            calls.append(1)
            return real(*a, **k)

        self.db.known_paths = counting
        self.tracker.browser_profiles = lambda: []   # no real browsers here
        self.tracker.scan_browsers()
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
