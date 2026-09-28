"""Reachability checks, and the Probes page that shows them.

A raw ICMP ping needs administrator rights on Windows; a TCP connect needs
none. These tests stand in for the network with a fake ``probe_once`` so they
run the same way with or without an actual connection.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication

_app = QApplication.instance() or QApplication([])

from netvitals.collectors import probes as probes_module          # noqa: E402
from netvitals.collectors.probes import ProbeCollector, describe   # noqa: E402
from netvitals.config import Settings                              # noqa: E402
from netvitals.db import Database                                  # noqa: E402
from netvitals.engine import Engine                                # noqa: E402
from netvitals.ui import pages                                     # noqa: E402

TARGETS = [
    ("Alpha", "203.0.113.1", 443, "an address, no DNS needed"),
    ("Beta", "203.0.113.2", 443, "a second, independent address"),
    ("Gamma (example.test)", "example.test", 443, "reached by name"),
]


class DescribeTests(unittest.TestCase):
    def test_a_timeout_is_named_as_one(self) -> None:
        self.assertEqual(describe(socket.timeout()), "timed out")

    def test_a_dns_failure_is_named_as_one(self) -> None:
        self.assertEqual(describe(socket.gaierror()), "name did not resolve")

    def test_other_errors_keep_their_class_name(self) -> None:
        self.assertIn("ConnectionRefusedError", describe(ConnectionRefusedError()))


class ProbeCollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = ProbeCollector(targets=TARGETS)

    def test_every_target_starts_unchecked(self) -> None:
        rows = self.collector.snapshot()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r["ok"] is None for r in rows))

    def test_snapshot_preserves_configured_order(self) -> None:
        rows = self.collector.snapshot()
        self.assertEqual([r["label"] for r in rows], ["Alpha", "Beta", "Gamma (example.test)"])

    def test_a_successful_pass_records_latency_and_a_timestamp(self) -> None:
        self.collector._results = {}  # rebuilt by the pass, not needed here
        original = probes_module.probe_once
        probes_module.probe_once = lambda host, port, timeout=4.0: (True, 12.5, "")
        try:
            self.collector._run_pass()
        finally:
            probes_module.probe_once = original
        rows = self.collector.snapshot()
        self.assertTrue(all(r["ok"] for r in rows))
        self.assertEqual(rows[0]["latency_ms"], 12.5)
        self.assertGreater(rows[0]["checked_at"], 0)

    def test_a_failed_target_carries_its_reason(self) -> None:
        original = probes_module.probe_once
        probes_module.probe_once = lambda host, port, timeout=4.0: (False, 0.0, "timed out")
        try:
            self.collector._run_pass()
        finally:
            probes_module.probe_once = original
        rows = self.collector.snapshot()
        self.assertFalse(any(r["ok"] for r in rows))
        self.assertEqual(rows[0]["error"], "timed out")

    def test_one_bad_target_does_not_stop_the_rest(self) -> None:
        original = probes_module.probe_once

        def flaky(host, port, timeout=4.0):
            if host == "203.0.113.1":
                raise RuntimeError("boom")
            return True, 5.0, ""

        probes_module.probe_once = flaky
        try:
            self.collector._run_pass()
        finally:
            probes_module.probe_once = original
        rows = {r["label"]: r for r in self.collector.snapshot()}
        # The one that raised keeps its previous (unchecked) state rather than
        # taking the whole pass down with it.
        self.assertIsNone(rows["Alpha"]["ok"])
        self.assertTrue(rows["Beta"]["ok"])

    def test_start_and_stop_are_idempotent_and_join_cleanly(self) -> None:
        collector = ProbeCollector(targets=TARGETS, interval=0.05)
        collector.start()
        collector.start()          # a second start must not spawn a second thread
        self.assertTrue(collector.running)
        time.sleep(0.15)
        collector.stop()
        self.assertFalse(collector.running)
        collector.stop()           # stopping twice must not raise


class ProbesPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-probes-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self.settings = Settings()
        self.engine = Engine(self.db, self.settings)
        self.page = pages.ProbesPage(self.db, self.engine, self.settings)

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def row(self, label="Alpha", ok=True, latency_ms=20.0, error="",
           checked_at=None, note="an address") -> dict:
        return {"label": label, "host": "203.0.113.1", "port": 443, "note": note,
                "ok": ok, "latency_ms": latency_ms, "error": error,
                "checked_at": checked_at if checked_at is not None else time.time()}

    def show(self, rows: list[dict]) -> None:
        self.engine.probes.snapshot = lambda: rows
        self.page.refresh()

    def test_a_reachable_target_shows_its_latency(self) -> None:
        self.show([self.row(ok=True, latency_ms=33.0)])
        self.assertEqual(self.page.table.item(0, 1).text(), "Reachable")
        self.assertEqual(self.page.table.item(0, 2).text(), "33 ms")

    def test_an_unreachable_target_shows_its_reason_not_a_bare_no(self) -> None:
        self.show([self.row(ok=False, error="timed out")])
        self.assertEqual(self.page.table.item(0, 1).text(), "Timed out")

    def test_a_target_with_no_result_yet_reads_as_checking(self) -> None:
        self.show([self.row(ok=None, checked_at=0.0)])
        self.assertIn("Checking", self.page.table.item(0, 1).text())
        self.assertIn("first time", self.page.note.text())

    def test_the_summary_counts_reachable_targets(self) -> None:
        self.show([self.row("Alpha", ok=True), self.row("Beta", ok=False)])
        self.assertIn("1 of 2", self.page.note.text())

    def test_all_reachable_is_said_plainly(self) -> None:
        self.show([self.row("Alpha", ok=True), self.row("Beta", ok=True)])
        self.assertIn("All 2 targets reachable", self.page.note.text())

    def test_nothing_reachable_blames_the_network_not_one_service(self) -> None:
        self.show([self.row("Alpha", ok=False), self.row("Beta", ok=False)])
        self.assertIn("network itself", self.page.note.text())

    def test_no_targets_is_survivable(self) -> None:
        self.show([])
        self.assertIn("No probe targets", self.page.note.text())

    def test_every_target_gets_a_row(self) -> None:
        self.show([self.row("Alpha"), self.row("Beta"), self.row("Gamma")])
        self.assertEqual(self.page.table.rowCount(), 3)


if __name__ == "__main__":
    unittest.main()
