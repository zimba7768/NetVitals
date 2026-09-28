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
    (4, "03-vpn.png",
     "VPN traffic measured separately, so tunnelled and direct are never added together."),
    (3, "04-files.png",
     "Every file that arrives in your watched folders, with its size and source."),
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
