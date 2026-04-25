"""Top-level main-window layout helpers."""

from __future__ import annotations

from typing import Any

from PySide2.QtCore import QSize, Qt
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QSplitter, QToolButton, QVBoxLayout, QWidget

from app.core import constants
from app.shell.layout_persistence import DEFAULT_TOP_SPLITTER_SIZES, DEFAULT_VERTICAL_SPLITTER_SIZES


def configure_window_frame(window: Any) -> None:
    """Apply static frame metadata owned by the shell composition root."""
    window.setObjectName("shell.mainWindow")
    window.setWindowTitle(f"ChoreBoy Code Studio v{constants.APP_VERSION}")
    window.resize(1280, 820)
    window.setMinimumSize(960, 640)


def build_layout_shell(window: Any) -> None:
    """Build the top-level splitter structure and delegate panel construction."""
    central = QWidget(window)
    central.setObjectName("shell.centralWidget")
    layout = QVBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)

    vertical_splitter = QSplitter(Qt.Vertical, central)
    vertical_splitter.setObjectName("shell.verticalSplitter")
    window._vertical_splitter = vertical_splitter

    top_splitter = QSplitter(Qt.Horizontal, vertical_splitter)
    top_splitter.setObjectName("shell.topSplitter")
    window._top_splitter = top_splitter
    top_splitter.addWidget(window._build_left_panel())
    top_splitter.addWidget(window._build_center_panel())
    top_splitter.setStretchFactor(0, 1)
    top_splitter.setStretchFactor(1, 3)

    vertical_splitter.addWidget(top_splitter)
    vertical_splitter.addWidget(window._build_bottom_panel())
    vertical_splitter.setStretchFactor(0, 4)
    vertical_splitter.setStretchFactor(1, 2)
    top_splitter.setSizes(list(DEFAULT_TOP_SPLITTER_SIZES))
    vertical_splitter.setSizes(list(DEFAULT_VERTICAL_SPLITTER_SIZES))

    layout.addWidget(vertical_splitter)
    window.setCentralWidget(central)


def make_explorer_button(parent: QWidget, tooltip: str, icon: QIcon) -> QToolButton:
    """Create the small toolbar buttons used in the Explorer header."""
    btn = QToolButton(parent)
    btn.setObjectName("shell.explorerAction")
    btn.setToolTip(tooltip)
    btn.setIcon(icon)
    btn.setFixedSize(QSize(24, 24))
    btn.setAutoRaise(True)
    return btn
