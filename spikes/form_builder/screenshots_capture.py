"""Grab the states the owner should see. Offscreen, then read the PNGs back."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = Path(__file__).resolve().parent / "screenshots"


def grab(widget, name: str, settle: bool = True, overlay=None) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QPainter
    from PySide6.QtWidgets import QApplication

    if settle:
        QApplication.processEvents()
    widget.repaint()
    image = widget.grab().toImage()
    if overlay is not None:
        overlay.repaint()
        shot = overlay.grab().toImage()
        painter = QPainter(image)
        painter.drawImage(overlay.mapTo(widget, QPoint(0, 0)), shot)
        painter.end()
    path = OUT / name
    image.save(str(path))
    colors = set()
    for y in range(0, image.height(), 24):
        for x in range(0, image.width(), 24):
            colors.add(image.pixelColor(x, y).name())
    print(f"{name} {image.width()}x{image.height()} colors {len(colors)}")


def main() -> None:
    from PySide6.QtCore import QLine, QRect
    from PySide6.QtWidgets import QApplication

    from spikes.form_builder.screens import TableDialog
    from spikes.form_builder.templates import data_entry
    from spikes.form_builder.theme import apply_theme
    from spikes.form_builder.window import MainWindow

    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    apply_theme(app, "light")
    window = MainWindow("light")
    window.resize(1280, 800)
    window.show()
    grab(window, "start.png")

    window.load_document(data_entry(), None)
    window.canvas.primary.rebuild_index()
    window.canvas.set_selection([])
    grab(window, "workbench-light.png", overlay=window.canvas.primary.overlay)

    window.canvas.primary.rebuild_index()
    info = next(iter(window.canvas.primary.overlay.layout_info.values()), None)
    if info is not None:
        rect = info["rect"]
        window.canvas.primary.overlay.removeEventFilter(window.canvas.primary)
        window.canvas.primary.overlay.slot = {
            "line": QLine(rect.left() + 8, rect.center().y(), rect.right() - 8, rect.center().y()),
            "cell": QRect(rect.left() + 12, rect.center().y() - 10, max(rect.width() - 24, 1), 20),
        }
        window.canvas.primary.refresh_overlay()
    grab(window, "insertion.png", settle=False, overlay=window.canvas.primary.overlay)
    window.canvas.primary.overlay.installEventFilter(window.canvas.primary)

    window.canvas.primary.overlay.slot = None
    window.set_mode("tab")
    window.canvas.primary.rebuild_index()
    window.canvas._sync_tab_badges()
    window.canvas.primary.refresh_overlay()
    grab(window, "tab-order.png", overlay=window.canvas.primary.overlay)

    window.set_mode("widgets")
    window.canvas.primary.overlay.slot = None
    dialog = TableDialog(window)
    dialog.show()
    grab(dialog, "from-table.png")
    dialog.hide()

    window.set_theme("dark")
    window.canvas.primary.rebuild_index()
    grab(window, "workbench-dark.png", overlay=window.canvas.primary.overlay)


if __name__ == "__main__":
    main()
