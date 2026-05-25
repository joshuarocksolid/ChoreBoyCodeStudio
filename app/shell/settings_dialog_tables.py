"""Table column sizing helpers for SettingsDialog."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide2.QtGui import QFontMetrics
from PySide2.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QWidget

if TYPE_CHECKING:
    from app.shell.settings_dialog import SettingsDialog

SETTINGS_TABLE_COLUMN_PAD = 16


def settings_table_widget_preferred_width(widget: QWidget) -> int:
    return max(
        widget.sizeHint().width(),
        widget.minimumSizeHint().width(),
        widget.minimumWidth(),
    )


def settings_table_item_text_width(table: QTableWidget, item: QTableWidgetItem) -> int:
    font = item.font()
    if font.pixelSize() < 0 and font.pointSize() < 0:
        font = table.font()
    fm = QFontMetrics(font)
    return fm.boundingRect(item.text()).width()


def settings_table_column_width(dialog: "SettingsDialog", table: QTableWidget, col: int) -> int:
    header = table.horizontalHeader()
    header_hint = header.sectionSizeFromContents(col).width()
    max_w = 0
    for row in range(table.rowCount()):
        cell = table.cellWidget(row, col)
        if cell is not None:
            max_w = max(max_w, settings_table_widget_preferred_width(cell))
            continue
        item = table.item(row, col)
        if item is not None:
            max_w = max(max_w, settings_table_item_text_width(table, item))
    return max(max_w, header_hint) + SETTINGS_TABLE_COLUMN_PAD


def finalize_keybindings_columns(dialog: "SettingsDialog") -> None:
    table = dialog._shortcut_table
    header = table.horizontalHeader()
    for col in (1, 2, 3):
        width = settings_table_column_width(dialog, table, col)
        header.setSectionResizeMode(col, QHeaderView.Fixed)
        table.setColumnWidth(col, max(width, 64))
    header.setSectionResizeMode(0, QHeaderView.Stretch)


def finalize_linter_columns(dialog: "SettingsDialog") -> None:
    table = dialog._linter_table
    header = table.horizontalHeader()
    for col in (0, 2, 3, 4):
        width = settings_table_column_width(dialog, table, col)
        header.setSectionResizeMode(col, QHeaderView.Fixed)
        table.setColumnWidth(col, max(width, 48))
    header.setSectionResizeMode(1, QHeaderView.Stretch)


def finalize_syntax_columns(dialog: "SettingsDialog") -> None:
    table = dialog._syntax_color_table
    header = table.horizontalHeader()
    for col in (1, 2, 3):
        width = settings_table_column_width(dialog, table, col)
        header.setSectionResizeMode(col, QHeaderView.Fixed)
        table.setColumnWidth(col, max(width, 56))
    header.setSectionResizeMode(0, QHeaderView.Stretch)
