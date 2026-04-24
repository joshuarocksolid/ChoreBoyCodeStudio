#!/usr/bin/env python3
"""Generate PNG icons from SVG masters for desktop launchers.

Uses PySide2 QSvgRenderer (available in the FreeCAD/ChoreBoy runtime) so
no external image tools are needed.

Usage (run via AppRun so PySide2 is available):
    /opt/freecad/AppRun python3 scripts/generate_icon_pngs.py
"""

from __future__ import annotations

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide2.QtCore import QByteArray, QRectF  # noqa: E402
from PySide2.QtGui import QImage, QPainter  # noqa: E402
from PySide2.QtSvg import QSvgRenderer  # noqa: E402
from PySide2.QtWidgets import QApplication  # noqa: E402

SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICON_DIR = os.path.join(ROOT, "app", "ui", "icons")


def _render_svg(svg_path: str, prefix: str) -> str:
    """Render an SVG to multi-resolution PNGs and return the 256px path."""
    with open(svg_path, "r", encoding="utf-8") as fh:
        svg_data = fh.read()

    svg_bytes = QByteArray(bytes(svg_data, "utf-8"))
    renderer = QSvgRenderer(svg_bytes)

    if not renderer.isValid():
        print("ERROR: SVG failed to parse: %s" % svg_path, file=sys.stderr)
        raise SystemExit(1)

    for size in SIZES:
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(0x00000000)
        painter = QPainter(image)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()

        out_path = os.path.join(ICON_DIR, "%s_%d.png" % (prefix, size))
        image.save(out_path, "PNG")
        print("  wrote %s" % out_path)

    return os.path.join(ICON_DIR, "%s_256.png" % prefix)


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)  # noqa: F841
    os.makedirs(ICON_DIR, exist_ok=True)

    svg_source = os.path.join(ICON_DIR, "python-logo-only.svg")

    app_256 = _render_svg(svg_source, "app_icon")
    app_desktop = os.path.join(ICON_DIR, "Python_Icon.png")
    shutil.copy2(app_256, app_desktop)
    print("  wrote %s (copy of 256px)" % app_desktop)

    installer_256 = _render_svg(svg_source, "installer_icon")
    installer_desktop = os.path.join(ICON_DIR, "installer_icon.png")
    shutil.copy2(installer_256, installer_desktop)
    print("  wrote %s (copy of 256px)" % installer_desktop)

    print("Done -- PNGs generated for app and installer icons.")


if __name__ == "__main__":
    main()
