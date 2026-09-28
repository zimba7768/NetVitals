"""The Interfaces page, and the per-adapter data behind it.

This page exists to make the direct/VPN split checkable. Every total in the
application depends on which adapter counts as what, and until now that
judgement was invisible: a misclassified adapter would show up only as figures
that looked subtly wrong, with nothing to inspect.
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

from netvitals.collectors import net_system                      # noqa: E402
from netvitals.collectors.net_system import (DIRECT, IGNORED, VPN,  # noqa: E402
                                             SystemNetCollector)
from netvitals.config import Settings                            # noqa: E402
from netvitals.db import Database                                # noqa: E402
from netvitals.engine import Engine                              # noqa: E402
from netvitals.ui import pages                                   # noqa: E402


class Counter:
    def __init__(self, recv: int, sent: int) -> None:
        self.bytes_recv, self.bytes_sent = recv, sent


class Stat:
    def __init__(self, isup: bool, speed: int = 0) -> None:
        self.isup, self.speed = isup, speed


class Addr:
    def __init__(self, address: str) -> None:
        import socket
        self.family, self.address = socket.AF_INET, address


class FakePsutil:
    def __init__(self, adapters: dict) -> None:
        self.adapters = adapters

    def net_io_counters(self, pernic: bool = False):
        return {n: Counter(*a["bytes"]) for n, a in self.adapters.items()}

    def net_if_stats(self):
        return {n: Stat(a["up"], a.get("speed", 0))
                for n, a in self.adapters.items()}

    def net_if_addrs(self):
        return {n: [Addr(a["ipv4"])] if a.get("ipv4") else []
                for n, a in self.adapters.items()}


ADAPTERS = {
    "Ethernet": {"up": True, "speed": 1000, "ipv4": "192.168.50.10",
                 "bytes": (5_000_000, 1_000_000)},
    "SurfsharkWireGuard": {"up": True, "speed": 0, "ipv4": "10.14.0.2",
                           "bytes": (3_000_000, 600_000)},
    "Loopback Pseudo-Interface 1": {"up": True, "ipv4": "127.0.0.1",
                                    "bytes": (10, 10)},
    "Wi-Fi 3": {"up": False, "ipv4": "169.254.202.70", "bytes": (0, 0)},
}


class InterfaceDetailTests(unittest.TestCase):
    def setUp(self) -> None:
        self._real = net_system.psutil
        net_system.psutil = FakePsutil(ADAPTERS)
        self.collector = SystemNetCollector()

    def tearDown(self) -> None:
        net_system.psutil = self._real

    def rows(self) -> dict:
        return {r["name"]: r for r in self.collector.interface_details()}

    def test_every_adapter_is_listed_including_ignored_and_down(self) -> None:
        # Hiding them would make the arithmetic impossible to check.
        self.assertEqual(set(self.rows()), set(ADAPTERS))

    def test_each_adapter_carries_its_classification(self) -> None:
        rows = self.rows()
        self.assertEqual(rows["Ethernet"]["kind"], DIRECT)
        self.assertEqual(rows["SurfsharkWireGuard"]["kind"], VPN)
        self.assertEqual(rows["Loopback Pseudo-Interface 1"]["kind"], IGNORED)

    def test_down_adapters_are_reported_as_down(self) -> None:
        self.assertFalse(self.rows()["Wi-Fi 3"]["up"])
        self.assertTrue(self.rows()["Ethernet"]["up"])

    def test_the_busiest_adapter_sorts_first(self) -> None:
        # A live adapter must not sit below a row of disconnected Wi-Fi.
        self.collector.sample()
        ADAPTERS["Ethernet"]["bytes"] = (9_000_000, 2_000_000)
        self.collector.sample()
        self.assertEqual(self.collector.interface_details()[0]["name"], "Ethernet")

    def test_rates_are_per_adapter_not_shared(self) -> None:
        self.collector.sample()
        ADAPTERS["Ethernet"]["bytes"] = (6_000_000, 1_000_000)
        self.collector.sample()
        rows = self.rows()
        self.assertGreater(rows["Ethernet"]["down_rate"], 0)
        self.assertEqual(rows["Wi-Fi 3"]["down_rate"], 0)

    def test_no_adapters_is_survivable(self) -> None:
        net_system.psutil = FakePsutil({})
        self.assertEqual(SystemNetCollector().interface_details(), [])


class InterfacesPageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="netvitals-if-")
        self.db = Database(os.path.join(self.dir, f"n_{time.time_ns()}.db"))
        self.settings = Settings()
        self.engine = Engine(self.db, self.settings)
        self.page = pages.InterfacesPage(self.db, self.engine, self.settings)

    def tearDown(self) -> None:
        self.db.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def show(self, rows: list[dict]) -> None:
        self.engine.system.interface_details = lambda: rows
        self.page.refresh()

    def row(self, name: str, kind: str = DIRECT, up: bool = True) -> dict:
        return {"name": name, "kind": kind, "up": up, "ipv4": "10.0.0.2",
                "speed": 1000, "received": 1, "sent": 1,
                "down_rate": 0.0, "up_rate": 0.0}

    def test_a_tunnel_is_explained_not_just_listed(self) -> None:
        self.show([self.row("Ethernet"), self.row("wg0", VPN)])
        self.assertIn("VPN tunnel", self.page.note.text())
        self.assertIn("never added to direct", self.page.note.text())

    def test_ignored_adapters_are_not_counted_in_the_summary(self) -> None:
        self.show([self.row("Ethernet"), self.row("lo", IGNORED)])
        self.assertIn("1 adapter counted", self.page.note.text())

    def test_the_summary_is_grammatical_in_both_cases(self) -> None:
        # A doubled full stop and a lowercase sentence start both shipped once.
        for rows in ([self.row("Ethernet")],
                     [self.row("Ethernet"), self.row("wg0", VPN)]):
            self.show(rows)
            text = self.page.note.text()
            self.assertNotIn("..", text)
            self.assertNotIn("(s)", text)

    def test_the_counters_are_labelled_as_windows_own(self) -> None:
        # They predate the install, so presenting them as our totals would
        # contradict every other figure in the application.
        self.show([self.row("Ethernet")])
        self.assertIn("lifetime counters", self.page.note.text())

    def test_no_adapters_says_so(self) -> None:
        self.show([])
        self.assertIn("No network adapters", self.page.note.text())

    def test_every_adapter_gets_a_row(self) -> None:
        self.show([self.row("Ethernet"), self.row("wg0", VPN),
                   self.row("lo", IGNORED), self.row("Wi-Fi", up=False)])
        self.assertEqual(self.page.table.rowCount(), 4)


if __name__ == "__main__":
    unittest.main()
