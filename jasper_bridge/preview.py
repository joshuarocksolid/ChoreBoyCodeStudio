from __future__ import annotations

import logging
import os
import sys
from typing import List

from .errors import PrintError

logger = logging.getLogger(__name__)


def preview(page_images: List[str], title: str = "Report Preview") -> None:
    if not page_images:
        raise PrintError("No page images provided for preview")

    for image_path in page_images:
        if not os.path.exists(image_path):
            raise FileNotFoundError(os.path.abspath(image_path))

    from PySide2 import QtCore, QtGui, QtPrintSupport, QtWidgets

    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)

    pixmaps = []
    for image_path in page_images:
        pixmap = QtGui.QPixmap(image_path)
        if pixmap.isNull():
            raise PrintError("Failed to load page image: {}".format(image_path))
        pixmaps.append(pixmap)

    printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
    dialog = QtPrintSupport.QPrintPreviewDialog(printer)
    dialog.setWindowTitle(title)

    def paint_pages(target_printer):
        painter = QtGui.QPainter(target_printer)
        page_rect = target_printer.pageRect()

        for index, pixmap in enumerate(pixmaps):
            if index > 0:
                target_printer.newPage()
            scaled = pixmap.scaled(
                page_rect.size(),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
            x_pos = (page_rect.width() - scaled.width()) // 2
            y_pos = (page_rect.height() - scaled.height()) // 2
            painter.drawPixmap(x_pos, y_pos, scaled)

        painter.end()

    dialog.paintRequested.connect(paint_pages)
    logger.debug("Opening preview dialog with %d page(s)", len(pixmaps))
    dialog.exec_()
