"""Reachability and latency, without the rights an ICMP ping needs.

A raw ICMP ping needs a raw socket, which on Windows means administrator
rights — exactly the elevation this application has spent its packaged build
avoiding. A TCP connect needs none: opening and immediately closing a socket
answers the same question ("is it there, and how long did it take to
answer?") using nothing but an ordinary, unprivileged connection attempt.

The targets are IP literals and one hostname, picked so a bad answer is
diagnostic rather than just "the internet is down":

* Two independent providers by address, so one being slow, blocked, or
  filtering — a captive portal, a VPN's kill switch, a route that only some
  addresses take — does not read as the whole internet being unreachable.
* One by hostname, so a DNS failure shows up as its own row rather than
  being indistinguishable from a routing problem.

Each probe opens a plain TCP connection and closes it immediately: nothing is
sent or read beyond the handshake itself. That is a deliberately small,
literal thing to be doing in an application about watching outbound traffic,
and it runs whether or not the desktop build's per-application tracking is
available — like the connection table, this needs no elevation and works
identically in the Microsoft Store build.
"""
from __future__ import annotations

import socket
import threading
import time

#: (label, host, port, why this one) — read top to bottom in the interface.
TARGETS: list[tuple[str, str, int, str]] = [
    ("Cloudflare (1.1.1.1)", "1.1.1.1", 443,
     "an IP address, so this needs no DNS lookup to reach — if this fails, "
     "nothing below it will succeed either"),
    ("Google (8.8.8.8)", "8.8.8.8", 443,
     "a second, independent address, so one provider being slow or blocked "
     "does not look like the whole internet being down"),
    ("GitHub (github.com)", "github.com", 443,
     "reached by name rather than address, so a DNS problem shows up here "
     "on its own instead of looking identical to a routing one"),
]

#: How often each target is re-checked.
INTERVAL = 20.0

#: A probe that has not answered by here counts as unreachable rather than
#: leaving the row stuck on "checking…" indefinitely.
TIMEOUT = 4.0


def probe_once(host: str, port: int, timeout: float = TIMEOUT) -> tuple[bool, float, str]:
    """Open and close a TCP connection. Returns (ok, latency_ms, error)."""
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except Exception as exc:
        return False, 0.0, describe(exc)
    return True, (time.monotonic() - started) * 1000.0, ""


def describe(exc: BaseException) -> str:
    """A short, specific reason rather than a bare exception class name."""
    name = type(exc).__name__
    if isinstance(exc, socket.timeout):
        return "timed out"
    if isinstance(exc, socket.gaierror):
        return "name did not resolve"
    text = (getattr(exc, "strerror", "") or "").strip()
    return f"{name}: {text}" if text else name


class ProbeCollector:
    """Runs the target list on a background thread and caches the results.

    A TCP connect can take the full timeout to fail, and there are several
    targets — running these from the interface thread on every refresh would
    freeze the window for seconds at a time. Instead a loop owns its own
    thread, one probe at a time, and the interface reads whatever the last
    pass found.
    """

    def __init__(self, targets: list[tuple[str, str, int, str]] | None = None,
                interval: float = INTERVAL) -> None:
        self.targets = targets if targets is not None else TARGETS
        self.interval = interval
        self._lock = threading.Lock()
        self._results: dict[str, dict] = {
            label: {"label": label, "host": host, "port": port, "note": note,
                    "ok": None, "latency_ms": 0.0, "error": "",
                    "checked_at": 0.0}
            for label, host, port, note in self.targets
        }
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ life
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="probes", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=TIMEOUT + 2)
            self._thread = None

    def refresh_now(self) -> None:
        """Run every target immediately rather than waiting for the next pass."""
        self._wake.set()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ----------------------------------------------------------------- read
    def snapshot(self) -> list[dict]:
        """The most recent result for every target, in the order configured."""
        with self._lock:
            return [dict(self._results[label]) for label, _h, _p, _n in self.targets]

    # ------------------------------------------------------------------ loop
    def _run_pass(self) -> None:
        for label, host, port, note in self.targets:
            if self._stop.is_set():
                return
            try:
                ok, latency_ms, error = probe_once(host, port)
            except Exception:
                # One target misbehaving must not cost the rest their turn —
                # leave its previous result in place and move on.
                continue
            with self._lock:
                self._results[label] = {
                    "label": label, "host": host, "port": port, "note": note,
                    "ok": ok, "latency_ms": latency_ms, "error": error,
                    "checked_at": time.time()}

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._run_pass()
            except Exception:
                pass                    # a single bad pass must not end the thread
            self._wake.wait(self.interval)
            self._wake.clear()
