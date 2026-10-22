#!/usr/bin/env python
"""Keep a Qt event loop alive without covering the desktop."""

from __future__ import annotations

import sys

from PySide2 import QtCore, QtWidgets


def main():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    for widget in app.topLevelWidgets():
        widget.hide()
    QtCore.QTimer.singleShot(800000, app.quit)
    app.exec_()


if __name__ == "__main__":
    main()
