"""Render the tile and logo images a Microsoft Store package must ship.

The app already paints its own icon, so these are generated from that rather
than drawn separately — one source, and no chance of the Store tile drifting
away from the tray icon.

Tiles are not icons: Windows draws them on a coloured plate, and artwork that
fills the square edge to edge looks cramped beside everything else on the
Start menu. Each size below therefore carries the icon at a proportion of the
canvas, centred, on transparency.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: (file name, width, height, how much of the shorter side the icon fills).
#: The required set for a desktop package, plus the optional tiles — shipping
#: them costs a few KB and stops Windows upscaling the small one.
ASSETS: list[tuple[str, int, int, float]] = [
    ("StoreLogo.png", 50, 50, 1.0),
    ("Square44x44Logo.png", 44, 44, 1.0),
    ("Square44x44Logo.targetsize-24_altform-unplated.png", 24, 24, 1.0),
    ("Square44x44Logo.targetsize-256.png", 256, 256, 1.0),
    ("Square71x71Logo.png", 71, 71, 0.66),
    ("Square150x150Logo.png", 150, 150, 0.60),
    ("Square310x310Logo.png", 310, 310, 0.55),
    ("Wide310x150Logo.png", 310, 150, 0.60),
    ("SplashScreen.png", 620, 300, 0.55),
]


def write_assets(folder: Path) -> int:
    """Render every image into ``folder``. Returns how many were written."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from netvitals.ui.tray import app_pixmap

    # A QApplication must exist before any QPixmap; keep the reference so it
    # is not collected mid-render.
    app = QApplication.instance() or QApplication([])
    assert app is not None
    folder.mkdir(parents=True, exist_ok=True)

    written = 0
    for name, width, height, fill in ASSETS:
        canvas = QPixmap(width, height)
        canvas.fill(Qt.transparent)
        side = max(1, int(min(width, height) * fill))
        icon = app_pixmap(side)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.drawPixmap((width - side) // 2, (height - side) // 2, icon)
        painter.end()

        if canvas.save(str(folder / name), "PNG"):
            written += 1
    return written


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / "Assets"
    count = write_assets(target)
    print(f"Wrote {count} images to {target}")
    for name, width, height, _ in ASSETS:
        print(f"  {name:52} {width}x{height}")
    return 0 if count == len(ASSETS) else 1


if __name__ == "__main__":
    sys.exit(main())
