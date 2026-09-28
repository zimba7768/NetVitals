"""Render the images the Microsoft Store listing needs.

    QT_QPA_PLATFORM=offscreen python tools/make_store_images.py [outdir]

Screenshots are rendered **as the Store build**, with demo data. Showing the
desktop version's per-application table would advertise a feature the package
does not have, which is both misleading and a certification risk; and real
usage data is nobody's business but the user's.

Sizes come from the Store's requirements: screenshots at 1366x768 or larger
(1920x1080 here), and a 1:1 tile icon at 300x300.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
#: Render the packaged branch: this is what a Store customer installs.
os.environ["NETVITALS_PACKAGED"] = "1"

WIDTH, HEIGHT = 1920, 1080
TILE = 300

#: (nav index, file name, caption for the listing — 200 characters at most)
SHOTS = [
    (0, "01-dashboard.png",
     "Live throughput and totals for today, this week, month and year."),
    (1, "02-history.png",
     "Hourly, daily, weekly, monthly and yearly history, as charts and tables."),
    (6, "03-connections.png",
     "Which application is talking to which host, and whether it went through the tunnel."),
    (4, "04-vpn.png",
     "VPN traffic measured separately, so tunnelled and direct are never added together."),
    (5, "05-interfaces.png",
     "Every adapter, what it is counted as, and what it is carrying right now."),
]


def load_screenshot_module():
    """Reuse the demo-data seeding rather than inventing a second version."""
    path = ROOT / "tools" / "screenshot.py"
    spec = importlib.util.spec_from_file_location("netvitals_screenshot", path)
    module = importlib.util.module_from_spec(spec)
    argv, sys.argv = sys.argv, ["screenshot.py", str(Path(os.environ.get(
        "NETVITALS_SHOT_TMP", "/tmp/netvitals-store-scratch")))]
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv = argv
    return module


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "store"
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication

    from netvitals.config import Settings, data_dir, db_path
    from netvitals.db import SYSTEM, Database
    from netvitals.engine import Engine
    from netvitals.ui import theme
    from netvitals.ui.assets import ensure_assets
    from netvitals.ui.main_window import MainWindow
    from netvitals.ui.tray import app_pixmap

    shots = load_screenshot_module()

    for suffix in ("", "-wal", "-shm"):
        try:
            os.unlink(str(db_path()) + suffix)
        except OSError:
            pass

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(theme.build_stylesheet(ensure_assets(data_dir())))

    settings = Settings()
    settings.update({"watch_folders": [str(Path.home() / "Downloads")],
                     "units": "auto"})
    db = Database(db_path())
    shots.seed(db)
    # The Store build never collects per-application rows, so a listing must
    # not show any: it would advertise a feature the package does not have.
    db._conn.execute("DELETE FROM traffic WHERE app != ?", (SYSTEM,))
    db._conn.commit()
    db.rollup(since=0)

    engine = Engine(db, settings)
    engine.wan.address = "203.0.113.42"          # RFC 5737, never a real one
    engine.wan.source = "ipify.org"
    engine.wan.checked_at = 1.0

    import random
    import time
    random.seed(11)
    now = time.time()
    level = 900_000.0
    for i in range(120):
        level = max(40_000.0, level + random.uniform(-260_000, 300_000))
        burst = 2_400_000 if 70 < i < 96 else 0
        engine.live.append((now - (120 - i), level + burst,
                            level * random.uniform(0.06, 0.2),
                            level * 0.35, level * 0.04))

    # The adapters and connections cards read the *real* machine. For listing
    # images that would publish whatever this build machine happens to be
    # running, so both are stood in for. Addresses are RFC 5737 documentation
    # ranges, never real ones.
    engine.system.interface_details = lambda: [
        {"name": "Ethernet", "kind": "direct", "up": True,
         "ipv4": "192.168.1.24", "speed": 1000,
         "received": 512_000_000_000, "sent": 48_000_000_000,
         "down_rate": 1_180_000.0, "up_rate": 214_000.0},
        {"name": "SurfsharkWireGuard", "kind": "vpn", "up": True,
         "ipv4": "10.14.0.2", "speed": 0,
         "received": 210_000_000_000, "sent": 19_000_000_000,
         "down_rate": 940_000.0, "up_rate": 96_000.0},
        {"name": "Wi-Fi", "kind": "direct", "up": False, "ipv4": "",
         "speed": 0, "received": 0, "sent": 0,
         "down_rate": 0.0, "up_rate": 0.0},
        {"name": "Loopback Pseudo-Interface 1", "kind": "ignored", "up": True,
         "ipv4": "127.0.0.1", "speed": 0, "received": 4_200_000,
         "sent": 4_200_000, "down_rate": 0.0, "up_rate": 0.0},
    ]

    def demo_connections(**_kwargs):
        made = []
        for app, host, port, count, link in (
                ("chrome.exe", "203.0.113.17", 443, 14, "direct"),
                ("steam.exe", "203.0.113.64", 27015, 6, "direct"),
                ("Spotify.exe", "203.0.113.90", 443, 4, "vpn"),
                ("Discord.exe", "203.0.113.12", 443, 3, "vpn"),
                ("OneDrive.exe", "203.0.113.41", 443, 2, "direct")):
            for _ in range(count):
                made.append({"app": app, "pid": 0, "protocol": "TCP",
                             "local_port": 0, "remote_ip": host,
                             "remote_port": port, "status": "ESTABLISHED",
                             "link": link})
        return made

    engine.connections.snapshot = demo_connections

    window = MainWindow(db, engine, settings)
    window.resize(WIDTH, HEIGHT)
    window.show()
    QCoreApplication.processEvents()

    written = []
    for index, name, _caption in SHOTS:
        window.nav_group.button(index).setChecked(True)
        window.stack.setCurrentIndex(index)
        window.refresh_current()
        page = window.stack.currentWidget()
        if hasattr(page, "refresh_live"):
            page.refresh_live()
        for _ in range(8):
            QCoreApplication.processEvents()
        target = out / name
        window.grab().save(str(target))
        written.append(target)

    tile = app_pixmap(TILE * 2).scaled(
        TILE, TILE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    tile_path = out / "store-tile-300.png"
    tile.save(str(tile_path))
    written.append(tile_path)

    db.close()

    print(f"Wrote {len(written)} images to {out}\n")
    for index, name, caption in SHOTS:
        print(f"  {name:20} {WIDTH}x{HEIGHT}")
        print(f"  {'':20} caption: {caption}")
    print(f"  {'store-tile-300.png':20} {TILE}x{TILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
