from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional

from .errors import PrintError

logger = logging.getLogger(__name__)


def print_report(
    page_images: List[str],
    title: str = "Print Report",
    printer: Optional[str] = None,
    copies: int = 1,
    collate: bool = False,
    duplex: bool = False,
    show_dialog: bool = True,
) -> bool:
    if not page_images:
        raise PrintError("No page images provided for printing")

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

    qt_printer = QtPrintSupport.QPrinter(QtPrintSupport.QPrinter.HighResolution)
    qt_printer.setDocName(title)
    qt_printer.setCopyCount(max(int(copies), 1))
    qt_printer.setCollateCopies(bool(collate))
    if duplex:
        qt_printer.setDuplex(QtPrintSupport.QPrinter.DuplexAuto)

    if printer:
        available = QtPrintSupport.QPrinterInfo.availablePrinters()
        matched = None
        for candidate in available:
            if candidate.printerName() == printer:
                matched = candidate
                break
        if matched is None:
            available_names = [item.printerName() for item in available]
            raise PrintError(
                "Printer '{}' not found. Available printers: {}".format(
                    printer, ", ".join(available_names)
                )
            )
        qt_printer.setPrinterName(printer)

    if show_dialog:
        dialog = QtPrintSupport.QPrintDialog(qt_printer)
        dialog.setWindowTitle(title)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            logger.info("Print dialog cancelled")
            return False

    painter = QtGui.QPainter(qt_printer)
    page_rect = qt_printer.pageRect()

    for index, pixmap in enumerate(pixmaps):
        if index > 0:
            qt_printer.newPage()
        scaled = pixmap.scaled(
            page_rect.size(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        x_pos = (page_rect.width() - scaled.width()) // 2
        y_pos = (page_rect.height() - scaled.height()) // 2
        painter.drawPixmap(x_pos, y_pos, scaled)

    painter.end()
    logger.info("Printed %d page(s)", len(pixmaps))
    return True
