"""Build a form from a SQLite table. Preview uses QUiLoader on our own XML.

``qtside/realize`` is not on this base, so the preview is not the canvas
realizer. Nothing here loads or runs the user's code.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Callable, Dict, List, Optional

from app.qt.QtCore import QBuffer, QIODevice, QLocale, Qt, Signal
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.features.form_builder.engine.project.names import class_name_for_stem
from app.features.form_builder.engine.project.table_form import (
    SHOWS_AS_CHOICES,
    BuiltTableForm,
    TableColumn,
    build_table_form_ui,
    four_digit_year_format,
    sqlite_columns,
    sqlite_tables,
)
from app.features.form_builder.qtside.theme.chrome import FormChrome

_INCLUDE_REASON = "Include at least one column"
_HEADERS = ("Include", "Column", "Type", "Shows as", "Label")


def locale_date_format() -> str:
    """The project locale's short date, with a four-digit year."""
    short = QLocale().dateFormat(QLocale.ShortFormat)
    return four_digit_year_format(str(short))


class FromTableDialog(QDialog):
    """Table list, column mapping, and a live preview."""

    create_requested = Signal()

    def __init__(
        self,
        *,
        project_root: str,
        stem: str,
        chrome: FormChrome,
        date_format: str,
        name_reason: Callable[[], Optional[str]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.fromTable")
        self.setWindowTitle("Build a form from a table")
        self.resize(960, 560)
        self._project_root = os.path.abspath(project_root)
        self._stem = stem
        self._chrome = chrome
        self._date_format = four_digit_year_format(date_format)
        self._name_reason = name_reason
        self._database = ""
        self._mappings: Dict[str, List[TableColumn]] = {}
        self._loading = False
        self._preview_widget: Optional[QWidget] = None
        self._build()
        self._apply_chrome()
        self._sync_button()

    def set_database(self, path: str) -> None:
        self._database = os.path.abspath(path)
        self._show_path(self._database)
        self._tables.clear()
        self._mappings.clear()
        self._mapping.setRowCount(0)
        try:
            names = sqlite_tables(self._database)
        except sqlite3.Error as exc:
            self._show_preview_message("Could not read that database: %s" % exc)
            self._sync_button()
            return
        if not names:
            self._show_preview_message("This database has no tables.")
            self._sync_button()
            return
        for name in names:
            self._tables.addItem(name)
        self._tables.setCurrentRow(0)

    def set_included(self, column: str, included: bool) -> None:
        row = self._row_for(column)
        item = self._mapping.item(row, 0)
        if item is None:
            return
        item.setCheckState(Qt.Checked if included else Qt.Unchecked)

    def set_label(self, column: str, label: str) -> None:
        row = self._row_for(column)
        item = self._mapping.item(row, 4)
        if item is not None:
            item.setText(label)

    def included_count(self) -> int:
        return sum(1 for column in self._current_columns() if column.include)

    def disabled_reason(self) -> str:
        return self._reason.text()

    def create_button(self) -> QPushButton:
        return self._create

    def database_label(self) -> str:
        return self._path.text()

    def database_tooltip(self) -> str:
        return self._path.toolTip()

    def built_form(self) -> BuiltTableForm:
        return build_table_form_ui(
            class_name_for_stem(self._stem),
            self._current_columns(),
            date_format=self._date_format,
        )

    def _build(self) -> None:
        root = QVBoxLayout(self)
        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Database", self))
        self._path = QLabel("Choose a SQLite file", self)
        self._path.setObjectName("formBuilder.fromTable.path")
        path_row.addWidget(self._path, 1)
        browse = QPushButton("Browse…", self)
        browse.setObjectName("formBuilder.fromTable.browse")
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        root.addLayout(path_row)

        body = QHBoxLayout()
        root.addLayout(body, 1)
        self._tables = QListWidget(self)
        self._tables.setObjectName("formBuilder.fromTable.tables")
        self._tables.currentTextChanged.connect(self._on_table)
        body.addWidget(self._tables, 1)

        self._mapping = QTableWidget(0, len(_HEADERS), self)
        self._mapping.setObjectName("formBuilder.fromTable.mapping")
        self._mapping.setHorizontalHeaderLabels(list(_HEADERS))
        self._mapping.itemChanged.connect(self._on_item_changed)
        body.addWidget(self._mapping, 3)

        self._preview = QVBoxLayout()
        preview_host = QWidget(self)
        preview_host.setObjectName("formBuilder.fromTable.preview")
        preview_host.setLayout(self._preview)
        body.addWidget(preview_host, 2)

        footer = QHBoxLayout()
        self._reason = QLabel("", self)
        self._reason.setObjectName("formBuilder.fromTable.reason")
        footer.addWidget(self._reason, 1)
        self._create = QPushButton(self)
        self._create.setObjectName("formBuilder.fromTable.create")
        self._create.clicked.connect(self.create_requested.emit)
        footer.addWidget(self._create)
        root.addLayout(footer)

    def _apply_chrome(self) -> None:
        chrome = self._chrome
        self.setStyleSheet(
            "QDialog#formBuilder\\.fromTable { background: %s; color: %s; }"
            "QLabel { color: %s; }"
            "QListWidget, QTableWidget { background: %s; color: %s; border: 1px solid %s; }"
            % (chrome.window, chrome.text, chrome.text, chrome.panel, chrome.text, chrome.border)
        )
        self._reason.setStyleSheet("color: %s;" % chrome.muted)
        self._path.setStyleSheet("color: %s;" % chrome.muted)

    def _browse(self) -> None:
        chosen, _selected = QFileDialog.getOpenFileName(
            self,
            "Choose a SQLite database",
            self._project_root,
            "SQLite (*.sqlite *.sqlite3 *.db);;All files (*)",
        )
        if chosen:
            self.set_database(chosen)

    def _show_path(self, path: str) -> None:
        relative = os.path.relpath(path, self._project_root).replace(os.sep, "/")
        if relative.startswith(".."):
            shown = path
        else:
            shown = relative
        self._path.setText(shown)
        self._path.setToolTip(os.path.abspath(path))

    def _on_table(self, name: str) -> None:
        if not name or not self._database:
            return
        if name not in self._mappings:
            try:
                raw = sqlite_columns(self._database, name)
            except sqlite3.Error as exc:
                self._show_preview_message("Could not read %s: %s" % (name, exc))
                return
            self._mappings[name] = [
                TableColumn(column_name, declared) for column_name, declared in raw
            ]
        self._fill_mapping(self._mappings[name])

    def _fill_mapping(self, columns: List[TableColumn]) -> None:
        self._loading = True
        self._mapping.setRowCount(len(columns))
        for row, column in enumerate(columns):
            include = QTableWidgetItem()
            include.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            include.setCheckState(Qt.Checked if column.include else Qt.Unchecked)
            self._mapping.setItem(row, 0, include)
            name_item = QTableWidgetItem(column.name)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self._mapping.setItem(row, 1, name_item)
            type_item = QTableWidgetItem(column.sql_type or "untyped")
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            self._mapping.setItem(row, 2, type_item)
            combo = QComboBox(self._mapping)
            for choice in SHOWS_AS_CHOICES:
                combo.addItem(choice)
            combo.setCurrentText(column.widget_class())
            combo.currentTextChanged.connect(lambda text, index=row: self._set_shows_as(index, text))
            self._mapping.setCellWidget(row, 3, combo)
            label = QTableWidgetItem(column.field_label())
            label.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self._mapping.setItem(row, 4, label)
        self._loading = False
        self._refresh_preview()
        self._sync_button()

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._loading:
            return
        table = self._tables.currentItem()
        if table is None:
            return
        columns = self._mappings.get(table.text())
        if not columns or item.row() >= len(columns):
            return
        current = columns[item.row()]
        if item.column() == 0:
            columns[item.row()] = TableColumn(
                current.name,
                current.sql_type,
                include=item.checkState() == Qt.Checked,
                shows_as=current.shows_as,
                label=current.label,
            )
        elif item.column() == 4:
            columns[item.row()] = TableColumn(
                current.name,
                current.sql_type,
                include=current.include,
                shows_as=current.shows_as,
                label=item.text(),
            )
        else:
            return
        self._refresh_preview()
        self._sync_button()

    def _set_shows_as(self, row: int, widget_class: str) -> None:
        if self._loading:
            return
        table = self._tables.currentItem()
        if table is None:
            return
        columns = self._mappings.get(table.text())
        if not columns or row >= len(columns):
            return
        current = columns[row]
        columns[row] = TableColumn(
            current.name,
            current.sql_type,
            include=current.include,
            shows_as=widget_class,
            label=current.label,
        )
        self._refresh_preview()

    def _current_columns(self) -> List[TableColumn]:
        table = self._tables.currentItem()
        if table is None:
            return []
        return list(self._mappings.get(table.text(), ()))

    def _row_for(self, column: str) -> int:
        for row in range(self._mapping.rowCount()):
            item = self._mapping.item(row, 1)
            if item is not None and item.text() == column:
                return row
        raise KeyError(column)

    def _sync_button(self) -> None:
        count = self.included_count()
        self._create.setText("Create form with %d fields" % count)
        reason = self._name_reason()
        if not reason and count == 0:
            reason = _INCLUDE_REASON
        self._create.setEnabled(not reason)
        self._reason.setText(reason or "")
        self._reason.setVisible(bool(reason))
        self._create.setToolTip(reason or "")

    def _refresh_preview(self) -> None:
        if not self._current_columns():
            self._show_preview_message("Include at least one column.")
            return
        built = self.built_form()
        buffer = QBuffer()
        buffer.setData(built.text.encode("utf-8"))
        buffer.open(QIODevice.ReadOnly)
        loader = QUiLoader()
        widget = loader.load(buffer)
        error = loader.errorString()
        if widget is None:
            self._show_preview_message(error or "The preview could not be built.")
            return
        self._swap_preview(widget)

    def _show_preview_message(self, text: str) -> None:
        label = QLabel(text, self)
        label.setWordWrap(True)
        self._swap_preview(label)

    def _swap_preview(self, widget: QWidget) -> None:
        while self._preview.count():
            item = self._preview.takeAt(0)
            old = item.widget()
            if old is not None:
                old.setParent(None)
                old.deleteLater()
        self._preview_widget = widget
        self._preview.addWidget(widget)
