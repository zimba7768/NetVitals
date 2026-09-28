"""Live connections, and the grouping that makes them readable.

Unlike the per-application byte counts, this needs no elevation, so it is one
of the few things that works identically in the Microsoft Store build. The
grouping matters as much as the data: a browser holds dozens of connections to
the same host, and listing each one separately buries everything else.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from netvitals.collectors import connections as conn_module   # noqa: E402
from netvitals.collectors.connections import ConnectionCollector  # noqa: E402
from netvitals.collectors.net_system import DIRECT, VPN       # noqa: E402


class Addr:
    def __init__(self, ip: str, port: int) -> None:
        self.ip, self.port = ip, port


class Kind:
    def __init__(self, name: str) -> None:
        self.name = name


class Conn:
    def __init__(self, pid, laddr, raddr, status="ESTABLISHED",
                 stream=True) -> None:
        self.pid = pid
        self.laddr = laddr
        self.raddr = raddr
        self.status = status
        self.type = Kind("SOCK_STREAM" if stream else "SOCK_DGRAM")


class FakeProcess:
    def __init__(self, pid) -> None:
        self.pid = pid

    def name(self) -> str:
        if self.pid == 999:
            raise PermissionError("access denied")
        return {101: "chrome.exe", 102: "steam.exe"}.get(self.pid, "other.exe")


class FakePsutil:
    def __init__(self, conns, tunnel_ip: str = "10.14.0.2") -> None:
        self.conns = conns
        self.tunnel_ip = tunnel_ip

    def net_connections(self, kind="inet"):
        return self.conns

    def net_if_addrs(self):
        class Entry:
            def __init__(self, address): self.address = address
        return {"Ethernet": [Entry("192.168.1.5")],
                "SurfsharkWireGuard": [Entry(self.tunnel_ip)]}

    def Process(self, pid):
        return FakeProcess(pid)


def collector(conns) -> ConnectionCollector:
    conn_module.psutil = FakePsutil(conns)
    return ConnectionCollector()


class SnapshotTests(unittest.TestCase):
    def tearDown(self) -> None:
        import psutil
        conn_module.psutil = psutil

    def test_listening_sockets_are_left_out(self) -> None:
        # A listening socket is not a conversation, and the page is about
        # conversations.
        c = collector([Conn(101, Addr("0.0.0.0", 443), None, "LISTEN")])
        self.assertEqual(c.snapshot(), [])

    def test_established_connections_are_included(self) -> None:
        c = collector([Conn(101, Addr("192.168.1.5", 50000),
                            Addr("93.184.216.34", 443))])
        rows = c.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["app"], "chrome.exe")
        self.assertEqual(rows[0]["remote_ip"], "93.184.216.34")

    def test_a_tunnelled_connection_is_labelled_as_such(self) -> None:
        # The same judgement the totals depend on, shown per connection.
        c = collector([Conn(101, Addr("10.14.0.2", 50000),
                            Addr("93.184.216.34", 443))])
        self.assertEqual(c.snapshot()[0]["link"], VPN)

    def test_a_direct_connection_is_not(self) -> None:
        c = collector([Conn(101, Addr("192.168.1.5", 50000),
                            Addr("93.184.216.34", 443))])
        self.assertEqual(c.snapshot()[0]["link"], DIRECT)

    def test_udp_is_distinguished_from_tcp(self) -> None:
        c = collector([Conn(101, Addr("192.168.1.5", 5353),
                            Addr("224.0.0.251", 5353), stream=False)])
        self.assertEqual(c.snapshot()[0]["protocol"], "UDP")

    def test_an_unreadable_process_still_produces_a_row(self) -> None:
        # Dropping it would understate the machine; the PID is what we know.
        c = collector([Conn(999, Addr("192.168.1.5", 50000),
                            Addr("93.184.216.34", 443))])
        rows = c.snapshot()
        self.assertEqual(len(rows), 1)
        self.assertIn("999", rows[0]["app"])

    def test_a_failing_connection_table_is_survivable(self) -> None:
        class Broken(FakePsutil):
            def net_connections(self, kind="inet"):
                raise PermissionError("denied")
        conn_module.psutil = Broken([])
        self.assertEqual(ConnectionCollector().snapshot(), [])

    def test_names_are_cached_rather_than_looked_up_per_connection(self) -> None:
        conns = [Conn(101, Addr("192.168.1.5", 50000 + i),
                      Addr("93.184.216.34", 443)) for i in range(20)]
        c = collector(conns)
        looked_up = []
        real = conn_module.psutil.Process
        conn_module.psutil.Process = lambda pid: (looked_up.append(pid)
                                                  or real(pid))
        c.snapshot()
        self.assertEqual(len(looked_up), 1, "one lookup per PID, not per socket")


class GroupingTests(unittest.TestCase):
    def rows(self, *specs) -> list[dict]:
        out = []
        for app, ip, port, count, link, status in specs:
            out += [{"app": app, "pid": 1, "protocol": "TCP", "local_port": 0,
                     "remote_ip": ip, "remote_port": port,
                     "status": status, "link": link}] * count
        return out

    def test_repeated_conversations_collapse_to_one_row(self) -> None:
        groups = ConnectionCollector().grouped(
            self.rows(("chrome.exe", "93.184.216.34", 443, 14, DIRECT,
                       "ESTABLISHED")))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 14)

    def test_different_hosts_stay_separate(self) -> None:
        groups = ConnectionCollector().grouped(self.rows(
            ("chrome.exe", "93.184.216.34", 443, 3, DIRECT, "ESTABLISHED"),
            ("chrome.exe", "93.184.216.99", 443, 2, DIRECT, "ESTABLISHED")))
        self.assertEqual(len(groups), 2)

    def test_the_same_host_on_both_routes_stays_separate(self) -> None:
        # Merging these would hide exactly what the VPN split exists to show.
        groups = ConnectionCollector().grouped(self.rows(
            ("chrome.exe", "93.184.216.34", 443, 2, DIRECT, "ESTABLISHED"),
            ("chrome.exe", "93.184.216.34", 443, 2, VPN, "ESTABLISHED")))
        self.assertEqual(len(groups), 2)
        self.assertEqual({g["link"] for g in groups}, {DIRECT, VPN})

    def test_the_busiest_destination_sorts_first(self) -> None:
        groups = ConnectionCollector().grouped(self.rows(
            ("steam.exe", "93.184.216.99", 27015, 2, DIRECT, "ESTABLISHED"),
            ("chrome.exe", "93.184.216.34", 443, 9, DIRECT, "ESTABLISHED")))
        self.assertEqual(groups[0]["app"], "chrome.exe")

    def test_the_dominant_state_wins(self) -> None:
        # One socket closing must not relabel an established conversation.
        groups = ConnectionCollector().grouped(self.rows(
            ("chrome.exe", "93.184.216.34", 443, 9, DIRECT, "ESTABLISHED"),
            ("chrome.exe", "93.184.216.34", 443, 1, DIRECT, "CLOSE_WAIT")))
        self.assertEqual(groups[0]["status"], "ESTABLISHED")
        self.assertEqual(groups[0]["count"], 10)


class SummaryTests(unittest.TestCase):
    def test_one_line_per_application_with_distinct_hosts(self) -> None:
        rows = [{"app": "chrome.exe", "remote_ip": "1.1.1.1", "link": DIRECT},
                {"app": "chrome.exe", "remote_ip": "1.1.1.1", "link": DIRECT},
                {"app": "chrome.exe", "remote_ip": "2.2.2.2", "link": VPN}]
        summary = ConnectionCollector().summary(rows)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary[0]["connections"], 3)
        self.assertEqual(summary[0]["hosts"], 2)
        self.assertEqual(summary[0]["tunnelled"], 1)


if __name__ == "__main__":
    unittest.main()
