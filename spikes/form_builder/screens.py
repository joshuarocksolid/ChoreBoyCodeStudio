"""Start screen and the build-from-table dialog."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spikes.form_builder.mapping import list_tables, plan_table
from spikes.form_builder.model import blank_widget, make_layout
from spikes.form_builder.templates import (
    blank_main_window,
    data_entry,
    dialog_buttons,
    from_columns,
    list_detail,
    table_search,
)


class StartScreen(QWidget):
    opened = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("panel")
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 40)
        root.setSpacing(18)
        title = QLabel("Form builder")
        title.setObjectName("title")
        subtitle = QLabel("Start from a layout you can already see. Drop widgets into it.")
        subtitle.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(subtitle)
        grid = QGridLayout()
        grid.setSpacing(12)
        cards = (
            ("Data-entry form", "Labels, fields, and a button box.", data_entry),
            ("List + detail", "A list beside one record.", list_detail),
            ("Table with search", "A search field above a table.", table_search),
            ("Dialog with buttons", "One field and Ok / Cancel.", dialog_buttons),
            ("Blank widget", "An empty page with a vertical layout.", blank_page),
            ("Blank main window", "Menu, toolbar, and a central page.", blank_main_window),
        )
        for index, (heading, body, factory) in enumerate(cards):
            grid.addWidget(_card(heading, body, factory, self.opened), index // 3, index % 3)
        root.addLayout(grid)
        row = QHBoxLayout()
        open_button = QPushButton("Open .ui")
        table_button = QPushButton("Build layout from a table")
        table_button.setObjectName("primary")
        open_button.clicked.connect(lambda: self.opened.emit("open"))
        table_button.clicked.connect(lambda: self.opened.emit("table"))
        row.addWidget(open_button)
        row.addWidget(table_button)
        row.addStretch(1)
        root.addLayout(row)
        root.addStretch(1)


class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Build layout from a table")
        self.resize(640, 420)
        self.path = QLineEdit()
        sample = Path(__file__).resolve().parent / "samples" / "shop.sqlite"
        if sample.exists():
            self.path.setText(str(sample))
        browse = QPushButton("Choose database")
        browse.clicked.connect(self._browse)
        self.tables = QComboBox()
        self.tables.currentTextChanged.connect(self._preview)
        self.preview = QTableWidget(0, 4)
        self.preview.setHorizontalHeaderLabels(["Column", "Type", "Widget", "Required"])
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form = QFormLayout(self)
        row = QHBoxLayout()
        row.addWidget(self.path)
        row.addWidget(browse)
        form.addRow("Database", row)
        form.addRow("Table", self.tables)
        form.addRow(self.preview)
        form.addRow(buttons)
        if self.path.text():
            self._load_tables()

    def _browse(self):
        path, _selected = QFileDialog.getOpenFileName(self, "SQLite database", self.path.text(), "SQLite (*.sqlite *.db)")
        if path:
            self.path.setText(path)
            self._load_tables()

    def _load_tables(self):
        self.tables.clear()
        path = self.path.text()
        if not path or not Path(path).exists():
            return
        with sqlite3.connect(path) as connection:
            for name in list_tables(connection):
                self.tables.addItem(name)
        self._preview(self.tables.currentText())

    def _preview(self, table):
        self.preview.setRowCount(0)
        path = self.path.text()
        if not table or not path or not Path(path).exists():
            return
        with sqlite3.connect(path) as connection:
            plans = plan_table(connection, table)
        self.preview.setRowCount(len(plans))
        for row, plan in enumerate(plans):
            self.preview.setItem(row, 0, QTableWidgetItem(plan.name))
            self.preview.setItem(row, 1, QTableWidgetItem(plan.declared_type))
            self.preview.setItem(row, 2, QTableWidgetItem(plan.widget))
            self.preview.setItem(row, 3, QTableWidgetItem("yes" if plan.required_marker else ""))

    def document(self):
        table = self.tables.currentText()
        with sqlite3.connect(self.path.text()) as connection:
            return from_columns(table, plan_table(connection, table))


def blank_page():
    doc = blank_widget("QWidget", "Form")
    doc.root.body.append(make_layout(doc, "QVBoxLayout", "verticalLayout"))
    return doc


def _card(heading, body, factory, opened):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    name = QLabel(heading)
    name.setObjectName("section")
    detail = QLabel(body)
    detail.setWordWrap(True)
    button = QPushButton("Use this")
    button.clicked.connect(lambda: opened.emit(factory))
    layout.addWidget(name)
    layout.addWidget(detail)
    layout.addWidget(button)
    return frame
