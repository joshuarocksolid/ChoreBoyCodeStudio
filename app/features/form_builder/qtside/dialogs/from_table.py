"""Build a bound form from a named connection.

The preview is still the column layout via QUiLoader. Create writes each file
through the Data-tab editors, one undo step per file.
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from typing import Callable, Dict, List, Optional, Tuple

from app.qt.QtCore import QBuffer, QEvent, QIODevice, QLocale, QSize, QTimer, Qt, Signal
from app.qt.QtGui import QBrush, QColor, QFont, QIcon, QPalette
from app.qt.QtUiTools import QUiLoader
from app.qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value

from app.features.form_builder.engine.data.connections import Connection, load_connections
from app.features.form_builder.engine.data.schema import Column, Schema, Table
from app.features.form_builder.engine.data.schema_cache import (
    footer_text,
    install_schema_reader,
    refresh,
    store_schema,
)
from app.features.form_builder.engine.data.schema_sqlite import read_sqlite_file
from app.features.form_builder.engine.project.from_table_plan import (
    ColumnChoice,
    TableRequest,
    button_sentence,
    child_tables,
    choice_for,
    default_lines,
    include_column,
    linking_columns,
    plan_forms,
)
from app.features.form_builder.engine.project.names import class_name_for_stem
from app.features.form_builder.engine.project.table_form import (
    BuiltTableForm,
    TableColumn,
    build_table_form_ui,
    four_digit_year_format,
)
from app.features.form_builder.qtside.icons.glyphs import paint_glyph
from app.features.form_builder.qtside.schema_prompt import ask_connection_secret
from app.features.form_builder.qtside.theme.chrome import FormChrome, apply_page_shadow, control_qss, edge_on
from app.features.form_builder.qtside.theme.items import polish_item_view
from app.features.form_builder.qtside.theme.metrics import (
    CONTROL,
    ICON,
    LABEL_MIN,
    MAPPING_ROW,
    PREVIEW_INSET,
    PRIMARY_BUTTON,
    R_CARD,
    S2,
    S4,
    TYPE_BODY,
    TYPE_FINE,
)
from app.features.form_builder.qtside.theme.runtime import host_form, pin_runtime_look
from app.features.form_builder.qtside.theme.dialog_body import parts_from
from app.features.form_builder.qtside.theme.section_header import SectionHeader

_INCLUDE_REASON = "Include at least one column"
_CHOOSE_CONNECTION = "Choose a connection"
_HEADERS = ("Include", "Column", "Type", "Shows as", "Label")
_SHOWS_AS_WORDS = (
    ("QLineEdit", "Text"),
    ("QPlainTextEdit", "Long text"),
    ("QSpinBox", "Whole number"),
    ("QDoubleSpinBox", "Decimal"),
    ("QCheckBox", "Checkbox"),
    ("QDateEdit", "Date"),
    ("QDateTimeEdit", "Date and time"),
    ("QComboBox", "Choice list"),
)
_MAKES = (
    ("record", "Record form"),
    ("list", "List screen"),
    ("both", "List screen and record form"),
)
_CLASS_GLYPH = {
    "QLineEdit": "line_edit",
    "QPlainTextEdit": "plain_text_edit",
    "QSpinBox": "spin_box",
    "QDoubleSpinBox": "double_spin_box",
    "QCheckBox": "check_box",
    "QDateEdit": "date_edit",
    "QDateTimeEdit": "date_time_edit",
    "QComboBox": "combo_box",
}
_TABLE_COLUMN = 180
_PREVIEW_COLUMN = 320
_INCLUDE_WIDTH = 64
_DISABLED_OPACITY = 0.5
_WIDGET_MAX = 16777215
_BAR_NAMES = ("recordBar", "listButtons", "lineButtons")


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
        add_connection: Optional[Callable[[], None]] = None,
        shell_chrome: Optional[tuple] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.fromTable")
        self.setWindowTitle("Build a form from a table")
        self.resize(1100, 680)
        self._project_root = os.path.abspath(project_root)
        self._stem = stem
        self._chrome = chrome
        self._date_format = four_digit_year_format(date_format)
        self._name_reason = name_reason
        self._add_connection = add_connection
        self._shell_chrome = shell_chrome
        self._database = ""
        self._connection_name = ""
        self._connections: Dict[str, Connection] = {}
        self._schema: Optional[Schema] = None
        self._mappings: Dict[str, List[TableColumn]] = {}
        self._loading = False
        self._disabled = ""
        self._footer = ""
        self._read_reason = ""
        self._current_table = ""
        self._line_memory: Dict[Tuple[str, str], Tuple[bool, str, str]] = {}
        self._schema_tokens: Dict[str, Tuple[object, ...]] = {}
        self._preview_widget: Optional[QWidget] = None
        self._preview_view: Optional[QGraphicsView] = None
        self._fitting_preview = False
        self._main_kind = "missing"
        self._replaces = ""
        self._build()
        self._apply_chrome()
        self._load_saved_connections()
        self._read_main_state()
        self._sync_button()

    def set_database(self, path: str, connection: str = "") -> None:
        """Point the dialog at a SQLite file under a real connection name."""

        self._database = os.path.abspath(path)
        self._show_path(self._database)
        self._connection_name = connection or str(self._connection.currentData() or "")
        if not self._connection_name:
            self._schema = None
            self._read_reason = _CHOOSE_CONNECTION
            self._tables.clear()
            self._mappings.clear()
            self._mapping.setRowCount(0)
            self._show_preview_message(_CHOOSE_CONNECTION)
            self._sync_button()
            return
        try:
            schema = read_sqlite_file(self._database, self._connection_name, read_at=_now())
        except sqlite3.Error as exc:
            self._schema = None
            self._read_reason = "Could not read that database: %s" % exc
            self._tables.clear()
            self._mappings.clear()
            self._mapping.setRowCount(0)
            self._show_preview_message("Could not read that database: %s" % exc)
            self._sync_button()
            return
        store_schema(self._project_root, schema)
        install_schema_reader(self._project_root)
        self._read_reason = ""
        self._footer = ""
        self._use_schema(schema)

    def schema(self) -> Optional[Schema]:
        return self._schema

    def request(self) -> Optional[TableRequest]:
        if self._disabled:
            return None
        return self._draft()

    def _draft(self) -> Optional[TableRequest]:
        table = self._tables.currentItem()
        if table is None or self._schema is None or not self._connection_name:
            return None
        lines = ""
        link = ""
        if str(self._make.currentData() or "record") != "list" and self._lines.isChecked():
            lines = str(self._lines_table.currentData() or "")
            link = str(self._lines_link.currentData() or "")
        return TableRequest(
            self._connection_name,
            table.text(),
            self._choices(),
            str(self._make.currentData() or "record"),
            lines,
            self._stem,
            self._date_format,
            lines_link=link,
        )

    def set_included(self, column: str, included: bool) -> None:
        row = self._row_for(column)
        item = self._mapping.item(row, 0)
        if item is None:
            return
        item.setCheckState(Qt.Checked if included else Qt.Unchecked)

    def set_label(self, column: str, label: str) -> None:
        row = self._row_for(column)
        editor = self._mapping.cellWidget(row, 4)
        if isinstance(editor, QLineEdit):
            editor.setText(label)
            return
        item = self._mapping.item(row, 4)
        if item is not None:
            item.setText(label)

    def included_count(self) -> int:
        return sum(1 for column in self._current_columns() if column.include)

    def disabled_reason(self) -> str:
        return self._disabled

    def create_button(self) -> QPushButton:
        return self._create

    def database_label(self) -> str:
        return self._path_text

    def database_tooltip(self) -> str:
        return self._path_tip

    def built_form(self) -> BuiltTableForm:
        return build_table_form_ui(
            class_name_for_stem(self._stem),
            self._current_columns(),
            date_format=self._date_format,
        )

    def _build(self) -> None:
        self._path_text = ""
        self._path_tip = ""
        self._headers: List[SectionHeader] = []
        build, add_button, _stretch, primary, secondary = self._shell_chrome or parts_from(self)
        chrome = build(
            self,
            title="Build a form from a table",
            object_name="formBuilder.fromTable",
            body_margins=True,
        )
        self._chrome_parts = chrome
        root = chrome.body.layout()
        assert isinstance(root, QVBoxLayout)
        root.setSpacing(S4)

        options = QGridLayout()
        options.setHorizontalSpacing(S2)
        options.setVerticalSpacing(S2)
        options.setColumnMinimumWidth(0, LABEL_MIN)
        options.setColumnStretch(1, 1)
        root.addLayout(options)

        self._connection = QComboBox(self)
        self._connection.setObjectName("formBuilder.fromTable.connection")
        self._connection.setAccessibleName("Connection")
        self._connection.setFixedHeight(CONTROL)
        self._connection.currentIndexChanged.connect(self._on_connection)
        database = _field_label("Connection", self._connection, self)
        database.setObjectName("formBuilder.fromTable.databaseLabel")
        options.addWidget(database, 0, 0)
        options.addWidget(self._connection, 0, 1)
        add = QPushButton("Add connection…", self)
        add.setObjectName("formBuilder.fromTable.addConnection")
        add.setAccessibleName("Add connection")
        add.setFixedHeight(CONTROL)
        add.clicked.connect(self._on_add_connection)
        options.addWidget(add, 0, 2)

        self._make = QComboBox(self)
        self._make.setObjectName("formBuilder.fromTable.make")
        self._make.setAccessibleName("Make")
        self._make.setFixedHeight(CONTROL)
        for key, label in _MAKES:
            self._make.addItem(label, key)
        self._make.currentIndexChanged.connect(lambda _index: self._on_make())
        make_label = _field_label("Make", self._make, self)
        make_label.setObjectName("formBuilder.fromTable.makeLabel")
        options.addWidget(make_label, 1, 0)
        options.addWidget(self._make, 1, 1)
        lines = QHBoxLayout()
        lines.setSpacing(S2)
        self._lines = QCheckBox("Include lines from", self)
        self._lines.setObjectName("formBuilder.fromTable.lines")
        self._lines.setAccessibleName("Include lines from")
        self._lines.toggled.connect(lambda _checked: self._on_lines_toggled())
        lines.addWidget(self._lines)
        self._lines_table = QComboBox(self)
        self._lines_table.setObjectName("formBuilder.fromTable.linesTable")
        self._lines_table.setAccessibleName("Line item table")
        self._lines_table.setFixedHeight(CONTROL)
        self._lines_table.currentIndexChanged.connect(lambda _index: self._on_lines_table())
        lines.addWidget(self._lines_table, 1)
        self._link_label = QLabel("Lines linked by", self)
        self._link_label.setObjectName("formBuilder.fromTable.linkLabel")
        lines.addWidget(self._link_label)
        self._lines_link = QComboBox(self)
        self._lines_link.setObjectName("formBuilder.fromTable.linesLink")
        self._lines_link.setAccessibleName("Lines linked by")
        self._lines_link.setFixedHeight(CONTROL)
        self._link_label.setBuddy(self._lines_link)
        self._lines_link.currentIndexChanged.connect(lambda _index: self._sync_button())
        lines.addWidget(self._lines_link, 1)
        options.addLayout(lines, 1, 2)

        body = QHBoxLayout()
        body.setSpacing(S4)
        root.addLayout(body, 1)

        tables_col = QWidget(self)
        tables_col.setFixedWidth(_TABLE_COLUMN)
        tables_layout = QVBoxLayout(tables_col)
        tables_layout.setContentsMargins(0, 0, 0, 0)
        tables_layout.setSpacing(S2)
        tables_layout.addWidget(self._section("TABLE", "formBuilder.fromTable.tablesHeader"))
        self._tables = QListWidget(tables_col)
        self._tables.setObjectName("formBuilder.fromTable.tables")
        self._tables.setAccessibleName("Tables")
        self._tables.setIconSize(QSize(ICON, ICON))
        self._tables.currentTextChanged.connect(self._on_table)
        tables_layout.addWidget(self._tables, 1)
        body.addWidget(tables_col)

        columns_col = QWidget(self)
        columns_layout = QVBoxLayout(columns_col)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        columns_layout.setSpacing(S2)
        columns_layout.addWidget(self._section("COLUMNS", "formBuilder.fromTable.columnsHeader"))
        self._mapping = QTableWidget(0, len(_HEADERS), columns_col)
        self._mapping.setObjectName("formBuilder.fromTable.mapping")
        self._mapping.setAccessibleName("Columns")
        self._mapping.setHorizontalHeaderLabels(list(_HEADERS))
        self._mapping.setTabKeyNavigation(False)
        self._mapping.verticalHeader().setVisible(False)
        self._mapping.verticalHeader().setDefaultSectionSize(MAPPING_ROW)
        self._mapping.setShowGrid(False)
        self._mapping.itemChanged.connect(self._on_item_changed)
        self._mapping.installEventFilter(self)
        self._mapping.viewport().installEventFilter(self)
        self._fitting_columns = False
        columns_layout.addWidget(self._mapping, 1)
        body.addWidget(columns_col, 1)

        preview_host = QWidget(self)
        preview_host.setObjectName("formBuilder.fromTable.preview")
        preview_host.setFixedWidth(_PREVIEW_COLUMN)
        preview_layout = QVBoxLayout(preview_host)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(S2)
        preview_layout.addWidget(self._section("PREVIEW", "formBuilder.fromTable.previewHeader"))
        self._page = QFrame(preview_host)
        self._page.setObjectName("formBuilder.fromTable.page")
        self._preview = QVBoxLayout(self._page)
        self._preview.setContentsMargins(PREVIEW_INSET, PREVIEW_INSET, PREVIEW_INSET, PREVIEW_INSET)
        self._preview.setSpacing(0)
        preview_layout.addWidget(self._page, 1)
        body.addWidget(preview_host)

        start_box = QWidget(chrome.footer)
        start_layout = QVBoxLayout(start_box)
        start_layout.setContentsMargins(0, 0, 0, 0)
        start_layout.setSpacing(0)
        self._start = QCheckBox("Open this screen when the app starts", start_box)
        self._start.setObjectName("formBuilder.fromTable.start")
        self._start.setAccessibleName("Open this screen when the app starts")
        self._start_user = False
        self._start.toggled.connect(self._on_start_toggled)
        self._start_note = QLabel("", start_box)
        self._start_note.setObjectName("formBuilder.fromTable.startNote")
        self._start_note.setWordWrap(True)
        self._start_note.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        start_layout.addWidget(self._start)
        start_layout.addWidget(self._start_note)
        self._reason = QLabel("", start_box)
        self._reason.setObjectName("formBuilder.fromTable.reason")
        self._reason.setWordWrap(True)
        self._reason.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        start_layout.addWidget(self._reason)
        chrome.footer_layout.addWidget(start_box, 1)
        self._cancel = add_button(chrome, "Cancel", role=secondary)
        self._cancel.setObjectName("formBuilder.fromTable.cancel")
        self._cancel.setAccessibleName("Cancel")
        self._cancel.setFixedHeight(PRIMARY_BUTTON)
        self._cancel.clicked.connect(self.reject)
        self._create = add_button(chrome, "Create", role=primary, default=True)
        self._create.setObjectName("formBuilder.fromTable.create")
        self._create.setAccessibleName("Create the form")
        self._create.setFixedHeight(PRIMARY_BUTTON)
        self._create.clicked.connect(self.create_requested.emit)
        self._chain_tabs()
        self._fit_columns()

    def _section(self, title: str, object_name: str) -> SectionHeader:
        header = SectionHeader(self, title, object_name=object_name, accessible_name=title)
        header.set_pad(0)
        header.setFocusPolicy(Qt.NoFocus)
        self._headers.append(header)
        return header

    def showEvent(self, event: object) -> None:  # type: ignore[override]
        super().showEvent(event)  # type: ignore[arg-type]
        QTimer.singleShot(0, self._fit_columns)
        QTimer.singleShot(0, self._fit_preview)

    def _apply_chrome(self) -> None:
        chrome = self._chrome
        focus = max(1, int(getattr(chrome, "focus_width", 1) or 1))
        self.setStyleSheet(
            "QDialog#formBuilder\\.fromTable { background: %s; color: %s; }"
            "QLabel#formBuilder\\.fromTable\\.databaseLabel,"
            "QLabel#formBuilder\\.fromTable\\.makeLabel,"
            "QLabel#formBuilder\\.fromTable\\.linkLabel { color: %s; background: transparent; }"
            "QLabel { color: %s; background: transparent; }"
            "QCheckBox { color: %s; background: transparent; }"
            "QLabel#formBuilder\\.fromTable\\.reason,"
            "QLabel#formBuilder\\.fromTable\\.startNote { color: %s; background: transparent; }"
            "QWidget#formBuilder\\.fromTable\\.preview { background: %s; }"
            "QFrame#formBuilder\\.fromTable\\.page { background: %s; border: 1px solid %s; border-radius: %dpx; }"
            "QPushButton#formBuilder\\.fromTable\\.cancel {"
            " background: %s; color: %s; border: 1px solid %s; border-radius: %dpx; padding: 0 12px; }"
            "QPushButton#formBuilder\\.fromTable\\.create {"
            " background: %s; color: %s; border: none; border-radius: %dpx; padding: 0 12px;"
            " font-weight: 600; min-height: %dpx; max-height: %dpx; }"
            "QPushButton#formBuilder\\.fromTable\\.create:disabled {"
            " background: %s; color: %s; border: none; border-radius: %dpx;"
            " min-height: %dpx; max-height: %dpx; }"
            "QPushButton#formBuilder\\.fromTable\\.addConnection {"
            " background: %s; color: %s; border: 1px solid %s; border-radius: %dpx; padding: 0 12px; }"
            "QComboBox#formBuilder\\.fromTable\\.connection,"
            "QComboBox#formBuilder\\.fromTable\\.make,"
            "QComboBox#formBuilder\\.fromTable\\.linesTable,"
            "QComboBox#formBuilder\\.fromTable\\.linesLink,"
            "QComboBox#formBuilder\\.fromTable\\.showsAs,"
            "QLineEdit#formBuilder\\.fromTable\\.labelEdit {"
            " background: %s; color: %s; border: 1px solid %s; border-radius: 4px; padding: 0 8px; }"
            "QLabel#shell\\.dialogChrome\\.title { color: %s; background: transparent;"
            " font-size: 17px; font-weight: 700; }"
            "QWidget#shell\\.dialogChrome\\.header { background: %s; color: %s;"
            " border-bottom: 1px solid %s; }"
            "QWidget#shell\\.dialogChrome\\.footer { background: %s; color: %s;"
            " border-top: 1px solid %s; }"
            "QWidget#shell\\.dialogChrome\\.body { background: %s; color: %s; }"
            "QPushButton#formBuilder\\.fromTable\\.addConnection:focus,"
            "QPushButton#formBuilder\\.fromTable\\.cancel:focus,"
            "QPushButton#formBuilder\\.fromTable\\.create:focus,"
            "QCheckBox#formBuilder\\.fromTable\\.lines:focus,"
            "QCheckBox#formBuilder\\.fromTable\\.start:focus"
            " { border: %dpx solid %s; }"
            "QHeaderView::section { background: %s; color: %s; border: none;"
            " border-bottom: 1px solid %s; padding: 0 4px; font-size: %dpx; font-weight: 600; }"
            % (
                chrome.window,
                chrome.text,
                chrome.text,
                chrome.text,
                chrome.text,
                chrome.text,
                chrome.window,
                chrome.panel,
                chrome.border,
                R_CARD,
                chrome.input,
                chrome.text,
                chrome.border,
                R_CARD,
                chrome.accent,
                chrome.on_accent,
                R_CARD,
                PRIMARY_BUTTON,
                PRIMARY_BUTTON,
                chrome.accent,
                chrome.on_accent,
                R_CARD,
                PRIMARY_BUTTON,
                PRIMARY_BUTTON,
                chrome.input,
                chrome.text,
                chrome.border,
                R_CARD,
                chrome.input,
                chrome.text,
                edge_on(chrome, chrome.input or chrome.panel),
                chrome.text,
                chrome.panel,
                chrome.text,
                chrome.border,
                chrome.panel,
                chrome.text,
                chrome.border,
                chrome.window,
                chrome.text,
                focus,
                chrome.accent,
                chrome.input,
                chrome.text,
                chrome.border,
                TYPE_FINE,
            )
            + _indicator_qss("QCheckBox#formBuilder\\.fromTable\\.lines", chrome)
            + _indicator_qss("QCheckBox#formBuilder\\.fromTable\\.start", chrome)
            + _indicator_qss("QTableWidget#formBuilder\\.fromTable\\.mapping", chrome)
        )
        for header in self._headers:
            header.apply_chrome(chrome)
        self._paint_dialog_ink()
        self._paint_field_view(self._tables)
        self._paint_field_view(self._mapping)
        self._mapping.setStyleSheet(
            self._mapping.styleSheet()
            + _indicator_qss("QTableWidget#formBuilder\\.fromTable\\.mapping", chrome)
        )
        apply_page_shadow(self._page, is_dark=chrome.is_dark, is_high_contrast=chrome.is_high_contrast)
        view = self._preview_view
        form = self._preview_widget
        if view is not None and form is not None:
            self._paint_preview(form, view)

    def _on_add_connection(self) -> None:
        if self._add_connection is None:
            return
        previous = str(self._connection.currentData() or "")
        before = set(self._connections)
        self._add_connection()
        self._load_saved_connections(previous, before)

    def _load_saved_connections(self, prefer: str = "", before: Optional[set] = None) -> None:
        loaded, _error = load_connections(self._project_root)
        known = set(self._connections) if before is None else set(before)
        self._connections = {}
        self._connection.blockSignals(True)
        self._connection.clear()
        fresh = ""
        if loaded is not None:
            for item in loaded.connections:
                self._connections[item.name] = item
                self._connection.addItem(item.title or item.name, item.name)
                # `before` is the set from the last load. A name that was not
                # in that set is the connection just added. The first open
                # passes no `before`, so the first saved connection stays put.
                if before is not None and item.name not in known:
                    fresh = item.name
        target = fresh or (prefer if prefer in self._connections else "")
        if not target and self._connection.count():
            target = str(self._connection.itemData(0) or "")
        index = self._connection.findData(target) if target else -1
        if index >= 0:
            self._connection.setCurrentIndex(index)
        self._connection.blockSignals(False)
        if index >= 0:
            self._on_connection()

    def _on_connection(self) -> None:
        self._read_main_state()
        name = str(self._connection.currentData() or "")
        connection = self._connections.get(name) if hasattr(self, "_connections") else None
        if connection is None:
            return
        outcome = refresh(
            self._project_root,
            connection,
            lambda item: ask_connection_secret(self._project_root, item),
        )
        if not outcome.ok or outcome.schema is None:
            self._connection_name = name
            if outcome.schema is not None:
                self._read_reason = ""
                self._footer = footer_text(
                    outcome.schema,
                    failed=True,
                    title=connection.title or name,
                    reason=outcome.reason or "",
                )
                self._use_schema(outcome.schema)
                return
            self._schema = None
            self._footer = ""
            self._read_reason = outcome.reason or "The columns could not be read."
            self._tables.clear()
            self._mappings.clear()
            self._mapping.setRowCount(0)
            self._show_preview_message(self._read_reason)
            self._sync_button()
            return
        self._read_reason = ""
        self._footer = ""
        self._connection_name = name
        if connection.engine == "sqlite" and connection.file:
            self._database = os.path.abspath(os.path.join(self._project_root, connection.file))
            self._show_path(self._database)
        else:
            self._database = name
            self._remember_path("", connection.title or name)
        self._use_schema(outcome.schema)

    def _use_schema(self, schema: Schema) -> None:
        token = tuple(
            (table.name, tuple((column.name, column.type, column.nullable) for column in table.columns))
            for table in schema.tables
        )
        previous = self._schema_tokens.get(self._connection_name)
        if previous is not None and previous != token:
            self._line_memory = {
                key: value for key, value in self._line_memory.items() if key[0] != self._connection_name
            }
        self._schema_tokens[self._connection_name] = token
        self._schema = schema
        install_schema_reader(self._project_root)
        self._current_table = ""
        self._tables.clear()
        self._mappings.clear()
        self._release_mapping_editors()
        self._mapping.setRowCount(0)
        if not schema.tables:
            self._show_preview_message("This database has no tables.")
            self._sync_button()
            return
        ink = self._chrome.glyph or self._chrome.text
        icon = QIcon(paint_glyph("table_widget", ink, ICON, 1.0))
        for table in schema.tables:
            item = QListWidgetItem(icon, table.name)
            self._tables.addItem(item)
            self._mappings[table.name] = [_mapping_row(table, column, schema.engine) for column in table.columns]
        self._tables.setCurrentRow(0)

    def _show_path(self, path: str) -> None:
        relative = os.path.relpath(path, self._project_root).replace(os.sep, "/")
        if relative.startswith(".."):
            shown = path
        else:
            shown = relative
        self._remember_path(shown, os.path.abspath(path))

    def _remember_path(self, shown: str, tip: str) -> None:
        self._path_text = shown
        self._path_tip = tip
        self._connection.setToolTip(tip)

    def _on_table(self, name: str) -> None:
        if not name:
            return
        if self._current_table and self._current_table != name:
            self._line_memory[self._memory_key(self._current_table)] = (
                self._lines.isChecked(),
                str(self._lines_table.currentData() or ""),
                str(self._lines_link.currentData() or ""),
            )
        self._current_table = name
        columns = self._mappings.get(name)
        if columns is None:
            return
        self._fill_mapping(columns)
        self._fill_lines(name)

    def _memory_key(self, table_name: str) -> Tuple[str, str]:
        return (self._connection_name, table_name)

    def _release_mapping_editors(self) -> None:
        table = self._mapping
        for row in range(table.rowCount()):
            for column in range(table.columnCount()):
                if table.cellWidget(row, column) is not None:
                    table.removeCellWidget(row, column)
        for child in list(table.findChildren(QComboBox)) + list(table.findChildren(QLineEdit)):
            child.hide()
            child.setParent(None)
            child.deleteLater()

    def _fill_mapping(self, columns: List[TableColumn]) -> None:
        self._release_mapping_editors()
        self._loading = True
        self._mapping.setRowCount(len(columns))
        for row, column in enumerate(columns):
            include = QTableWidgetItem()
            include.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            include.setCheckState(Qt.Checked if column.include else Qt.Unchecked)
            self._mapping.setItem(row, 0, include)
            name_item = QTableWidgetItem(column.name)
            name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            name_font = QFont(name_item.font())
            name_font.setPixelSize(TYPE_BODY)
            name_item.setFont(name_font)
            name_item.setForeground(QBrush(QColor(self._chrome.text)))
            self._mapping.setItem(row, 1, name_item)
            type_item = QTableWidgetItem((column.sql_type or "untyped").upper())
            type_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            type_font = QFont(type_item.font())
            type_font.setPixelSize(TYPE_FINE)
            type_item.setFont(type_font)
            type_item.setForeground(QBrush(QColor(self._chrome.faint)))
            self._mapping.setItem(row, 2, type_item)
            combo = self._shows_as_combo(column.widget_class())
            combo.setObjectName("formBuilder.fromTable.showsAs")
            combo.currentIndexChanged.connect(
                lambda _index, row_index=row, box=combo: self._on_shows_as_changed(row_index, box)
            )
            self._mapping.setCellWidget(row, 3, combo)
            label = QLineEdit(column.field_label(), self._mapping)
            label.setObjectName("formBuilder.fromTable.labelEdit")
            label.setFixedHeight(CONTROL)
            label.setAccessibleName("Label for %s" % column.name)
            label.editingFinished.connect(lambda row_index=row, box=label: self._on_label_edited(row_index, box))
            self._mapping.setCellWidget(row, 4, label)
        self._loading = False
        self._fit_columns()
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
        else:
            return
        self._refresh_preview()
        self._sync_button()

    def _on_label_edited(self, row: int, box: QLineEdit) -> None:
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
            shows_as=current.shows_as,
            label=box.text(),
        )
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

    def _shows_as_combo(self, widget_class: str) -> QComboBox:
        combo = QComboBox()
        combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        combo.setFixedHeight(CONTROL)
        combo.setIconSize(QSize(ICON, ICON))
        ink = self._chrome.glyph or self._chrome.text
        chosen = 0
        for index, (qt_name, word) in enumerate(_SHOWS_AS_WORDS):
            glyph = _CLASS_GLYPH.get(qt_name, "widget")
            combo.addItem(QIcon(paint_glyph(glyph, ink, ICON, 1.0)), word, qt_name)
            combo.setItemData(index, qt_name, Qt.ToolTipRole)
            if qt_name == widget_class:
                chosen = index
        combo.blockSignals(True)
        combo.setCurrentIndex(chosen)
        combo.setToolTip(widget_class)
        combo.blockSignals(False)
        combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return combo

    def _on_shows_as_changed(self, row: int, box: QComboBox) -> None:
        chosen = box.currentData()
        box.setToolTip("" if chosen is None else str(chosen))
        if chosen is None:
            return
        self._set_shows_as(row, str(chosen))

    def wants_start_screen(self) -> bool:
        offer = getattr(self, "_start_offer", None)
        return bool(offer is not None and offer.enabled and self._start.isChecked())

    def start_module(self) -> str:
        offer = getattr(self, "_start_offer", None)
        return "" if offer is None else offer.module

    def start_class(self) -> str:
        offer = getattr(self, "_start_offer", None)
        return "" if offer is None else offer.class_name

    def start_sentence(self) -> str:
        return self._start_note.text()

    def _on_start_toggled(self, _checked: bool) -> None:
        if self._start.isEnabled():
            self._start_user = True

    def _read_main_state(self) -> None:
        from app.features.form_builder.engine.project.start_screen import launched_class, main_kind

        template = _template_main_bytes(self._project_root)
        self._main_kind = main_kind(self._project_root, template)
        self._replaces = launched_class(template)

    def _sync_start(self) -> None:
        from app.features.form_builder.engine.project.start_screen import present

        made = present(
            self._main_kind,
            self._replaces,
            self._stem,
            str(self._make.currentData() or "record"),
        )
        self._start_offer = made
        self._start.blockSignals(True)
        self._start.setEnabled(made.enabled)
        self._start.setText(made.label)
        if made.enabled:
            if not self._start_user:
                self._start.setChecked(made.checked)
            self._start_note.setText("")
        else:
            self._start.setChecked(False)
            self._start_note.setText(made.sentence)
        self._start.blockSignals(False)
        self._start.setToolTip(self._start_note.text())
        self._start_note.setVisible(False)

    def _chain_tabs(self) -> None:
        """Tables, the grid, then Make and the buttons. Tab must leave the grid."""

        order = (
            self._connection,
            self._tables,
            self._mapping,
            self._make,
            self._lines,
            self._lines_table,
            self._lines_link,
            self._start,
            self._cancel,
            self._create,
        )
        for earlier, later in zip(order, order[1:]):
            QWidget.setTabOrder(earlier, later)

    def _open_shows_as(self, event: object) -> bool:
        key = enum_value(getattr(event, "key")())
        mods = enum_value(getattr(event, "modifiers")())
        alt_down = key == enum_value(Qt.Key_Down) and bool(mods & enum_value(Qt.AltModifier))
        if key not in (enum_value(Qt.Key_F2), enum_value(Qt.Key_Space)) and not alt_down:
            return False
        if self._mapping.currentColumn() != 3:
            return False
        box = self._mapping.cellWidget(self._mapping.currentRow(), 3)
        if not isinstance(box, QComboBox):
            return False
        box.setFocus()
        box.showPopup()
        return True

    def eventFilter(self, watched: object, event: object) -> bool:  # type: ignore[override]
        if watched is self._mapping and enum_value(getattr(event, "type")()) == enum_value(QEvent.KeyPress):
            if self._open_shows_as(event):
                return True
        viewport = self._mapping.viewport()
        if watched is viewport and enum_value(getattr(event, "type")()) == enum_value(QEvent.Resize):
            self._fit_columns()
        view = getattr(self, "_preview_view", None)
        if view is not None and watched is view.viewport():
            if enum_value(getattr(event, "type")()) == enum_value(QEvent.Resize):
                self._fit_preview()
        return bool(super().eventFilter(watched, event))  # type: ignore[arg-type]

    def _fit_columns(self) -> None:
        """Keep the Label column inside the viewport on both Qt bindings."""
        if self._fitting_columns:
            return
        self._fitting_columns = True
        try:
            for _attempt in range(3):
                before = self._mapping.viewport().width()
                self._fit_columns_now()
                if self._mapping.viewport().width() == before:
                    break
        finally:
            self._fitting_columns = False

    def _fit_columns_now(self) -> None:
        table = self._mapping
        header = table.horizontalHeader()
        if table.columnCount() < 5:
            return
        viewport = table.viewport().width()
        if viewport < 80:
            return
        resize = getattr(QHeaderView, "ResizeMode", QHeaderView)
        contents = getattr(resize, "ResizeToContents")
        fixed = getattr(resize, "Fixed")
        stretch = getattr(resize, "Stretch")
        measured = []
        for column in range(5):
            header.setSectionResizeMode(column, contents)
            table.resizeColumnToContents(column)
            measured.append(max(16, header.sectionSize(column)))
        for row in range(table.rowCount()):
            editor = table.cellWidget(row, 3)
            if editor is not None:
                measured[3] = max(measured[3], editor.sizeHint().width())
        _include, column, type_width, shows = measured[:4]
        include = _INCLUDE_WIDTH
        column = max(48, column)
        spare = viewport - include - type_width - shows - column
        if spare < 64:
            column = max(48, viewport - include - type_width - shows - 64)
        header.setStretchLastSection(False)
        for index, width in ((0, include), (1, column), (2, type_width), (3, shows)):
            header.setSectionResizeMode(index, fixed)
            header.resizeSection(index, width)
        header.setSectionResizeMode(4, stretch)
        table.updateGeometries()
        for row in range(table.rowCount()):
            editor = table.cellWidget(row, 3)
            if editor is None:
                continue
            rect = table.visualRect(table.model().index(row, 3))
            editor.setFixedWidth(max(rect.width(), 1))

    def _fade_create(self, enabled: bool) -> None:
        if enabled:
            self._create.setGraphicsEffect(None)
            return
        effect = self._create.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(self._create)
            self._create.setGraphicsEffect(effect)
        effect.setOpacity(_DISABLED_OPACITY)

    def _sync_button(self) -> None:
        self._sync_start()
        count = self.included_count()
        table = self._tables.currentItem()
        name = table.text() if table is not None else ""
        make = str(self._make.currentData() or "record")
        lines = bool(make != "list" and self._lines.isChecked() and self._lines_table.currentData())
        draft = self._draft()
        planned = plan_forms(draft, self._schema) if draft is not None and self._schema is not None else None
        sentence = planned.button_text if planned is not None else button_sentence(name, count, make, lines)
        self._create.setText(sentence)
        self._create.setAccessibleName(sentence)
        reason = self._name_reason()
        if not reason and self._schema is None:
            reason = self._read_reason or _CHOOSE_CONNECTION
        elif not reason and planned is not None and planned.disabled_reason:
            reason = planned.disabled_reason
        elif not reason and count == 0 and self._schema is not None:
            reason = _INCLUDE_REASON
        self._disabled = reason or ""
        self._create.setEnabled(not self._disabled)
        shown = self._disabled or self._footer
        if shown == _CHOOSE_CONNECTION:
            shown = ""
        self._reason.setText(shown)
        self._reason.setVisible(bool(shown))
        self._create.setToolTip(self._disabled or "")
        self._fade_create(not self._disabled)

    def _on_make(self) -> None:
        self._sync_lines_and_button()
        self._refresh_preview()

    def _on_lines_toggled(self) -> None:
        self._sync_button()
        if not self._loading:
            self._refresh_preview()

    def _sync_lines_and_button(self) -> None:
        make = str(self._make.currentData() or "record")
        show = make != "list" and self._lines_table.count() > 0
        self._lines.setVisible(show)
        self._lines_table.setVisible(show)
        if not show:
            self._link_label.setVisible(False)
            self._lines_link.setVisible(False)
        self._sync_button()

    def _on_lines_table(self) -> None:
        self._fill_link()
        self._sync_button()

    def _fill_lines(self, table_name: str) -> None:
        self._lines_table.blockSignals(True)
        self._lines_table.clear()
        children = child_tables(self._schema, table_name) if self._schema is not None else ()
        for child in children:
            self._lines_table.addItem(child.name, child.name)
        remembered = self._line_memory.get(self._memory_key(table_name))
        chosen = remembered[1] if remembered else ""
        if not chosen and self._schema is not None:
            for child in children:
                if default_lines(self._schema, table_name, child):
                    chosen = child.name
                    break
        index = self._lines_table.findData(chosen) if chosen else 0
        if index < 0:
            index = 0
        if self._lines_table.count():
            self._lines_table.setCurrentIndex(index)
        self._lines_table.blockSignals(False)
        has_child = self._lines_table.count() > 0
        self._lines.setText("Include lines from" if has_child else "Include lines")
        self._lines.setAccessibleName(self._lines.text())
        self._lines.blockSignals(True)
        if remembered is not None:
            self._lines.setChecked(remembered[0])
        else:
            checked = False
            if chosen and self._schema is not None:
                checked = any(default_lines(self._schema, table_name, child) for child in children)
            self._lines.setChecked(checked)
        self._lines.blockSignals(False)
        self._fill_link(remembered[2] if remembered else "")
        self._sync_lines_and_button()
        self._refresh_preview()

    def _fill_link(self, prefer: str = "") -> None:
        child_name = str(self._lines_table.currentData() or "")
        child = None
        if self._schema is not None:
            for table in self._schema.tables:
                if table.name == child_name:
                    child = table
                    break
        links = linking_columns(child, self._current_table) if child is not None else ()
        self._lines_link.blockSignals(True)
        self._lines_link.clear()
        for column in links:
            self._lines_link.addItem(column.name, column.name)
        if len(links) > 1:
            self._lines_link.insertItem(0, "(choose)", "")
        target = prefer if any(column.name == prefer for column in links) else ""
        if not target and len(links) == 1:
            target = links[0].name
        found = self._lines_link.findData(target)
        self._lines_link.setCurrentIndex(found if found >= 0 else 0)
        self._lines_link.blockSignals(False)
        show = len(links) > 1 and str(self._make.currentData() or "record") != "list"
        self._link_label.setVisible(show)
        self._lines_link.setVisible(show)

    def _choices(self) -> Tuple[ColumnChoice, ...]:
        chosen = []
        for column in self._current_columns():
            if column.include:
                chosen.append(ColumnChoice(column.name, column.widget_class(), column.field_label()))
        return tuple(chosen)

    def _refresh_preview(self) -> None:
        if not self._current_columns():
            self._show_preview_message(self._disabled or "Include at least one column.")
            return
        draft = self._draft()
        text = ""
        if draft is not None and self._schema is not None:
            from app.features.form_builder.qtside.dialogs.table_apply import render_plans

            made = render_plans(draft, self._schema, self._project_root)
            planned = plan_forms(draft, self._schema)
            kinds = {form.stem: form.kind for form in planned.forms}
            record = ""
            for stem, body in made:
                if draft.make == "list" or kinds.get(stem) == "record":
                    record = body
                    break
            text = record
        if not text:
            self._show_preview_message(self._disabled or "The preview could not be built.")
            return
        buffer = QBuffer()
        buffer.setData(text.encode("utf-8"))
        buffer.open(QIODevice.ReadOnly)
        loader = QUiLoader()
        clear = getattr(loader, "clearPluginPaths", None)
        if callable(clear):
            clear()
        widget = loader.load(buffer)
        error = loader.errorString()
        if widget is None:
            self._show_preview_message(error or "The preview could not be built.")
            return
        # A proxy in its own scene: the app style sheet cannot reach it (UX-ISO-001).
        view = host_form(widget)
        self._paint_preview(widget, view)
        view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        view.viewport().setFocusPolicy(Qt.FocusPolicy.NoFocus)
        view.setMinimumWidth(0)
        view.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for child in widget.findChildren(QWidget):
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        view.viewport().installEventFilter(self)
        self._preview_view = view
        self._swap_preview(view, widget)
        self._fit_preview()
        QTimer.singleShot(0, self._fit_preview)

    def _fit_preview(self) -> None:
        if self._fitting_preview:
            return
        view = self._preview_view
        form = self._preview_widget
        if view is None or form is None:
            return
        proxy = form.graphicsProxyWidget()
        if proxy is None:
            return
        self._fitting_preview = True
        try:
            view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            width = self._preview_width(view)
            self._place_form(form, proxy, view, width)
            extent = view.verticalScrollBar().sizeHint().width()
            if extent <= 0:
                extent = 16
            if form.height() > view.viewport().height() and width - extent >= 48:
                self._place_form(form, proxy, view, width - extent)
        finally:
            self._fitting_preview = False

    def _show_preview_message(self, text: str) -> None:
        # "Choose a connection" lives on the disabled Create button.
        if text == _CHOOSE_CONNECTION:
            self._preview_view = None
            self._swap_preview(QWidget(self), None)
            return
        label = QLabel(text, self)
        label.setWordWrap(True)
        label.setObjectName("formBuilder.fromTable.previewMessage")
        self._preview_view = None
        self._swap_preview(label, None)

    def _swap_preview(self, shown: QWidget, form: Optional[QWidget]) -> None:
        while self._preview.count():
            item = self._preview.takeAt(0)
            old = item.widget()
            if old is not None:
                # setParent(None) would turn the old preview into a real window
                # and steal the keyboard from the dialog.
                old.hide()
                old.deleteLater()
        self._preview_widget = form
        self._preview.addWidget(shown)


    def _paint_preview(self, widget: QWidget, view: QGraphicsView) -> None:
        """The page card is chrome. The form itself stays the runtime Fusion look."""
        pin_runtime_look(widget)
        view.setBackgroundBrush(QColor(self._chrome.panel))
        scene = view.scene()
        if scene is not None:
            scene.setBackgroundBrush(QColor(self._chrome.panel))

    def _paint_dialog_ink(self) -> None:
        self._paint_ink(self)
        for label in self.findChildren(QLabel):
            name = label.objectName()
            if name.startswith("formBuilder.fromTable.") or name.startswith("shell.dialogChrome."):
                self._paint_ink(label)
        for box in self.findChildren(QCheckBox):
            if box.objectName().startswith("formBuilder.fromTable."):
                self._paint_ink(box)

    def _paint_ink(self, widget: QWidget) -> None:
        palette = widget.palette()
        role = getattr(QPalette, "ColorRole", QPalette)
        ink = QColor(self._chrome.text)
        palette.setColor(getattr(role, "WindowText"), ink)
        palette.setColor(getattr(role, "Text"), ink)
        palette.setColor(getattr(role, "ButtonText"), ink)
        widget.setPalette(palette)

    def _paint_field_view(self, view: QWidget) -> None:
        chrome = self._chrome
        polish_item_view(view, chrome)
        name = view.objectName().replace(".", "\\.")
        kind = view.metaObject().className()
        fill = chrome.input or chrome.panel
        ink = chrome.text
        view.setStyleSheet(
            view.styleSheet()
            + "%s#%s { background: %s; color: %s; }" % (kind, name, fill, ink)
            + "%s#%s::item { color: %s; }" % (kind, name, ink)
        )
        viewport = view.viewport()
        viewport.setStyleSheet("background: %s; color: %s;" % (fill, ink))
        palette = view.palette()
        role = getattr(QPalette, "ColorRole", QPalette)
        qfill = QColor(fill)
        qink = QColor(ink)
        palette.setColor(getattr(role, "Base"), qfill)
        palette.setColor(getattr(role, "Window"), qfill)
        palette.setColor(getattr(role, "Text"), qink)
        palette.setColor(getattr(role, "WindowText"), qink)
        view.setPalette(palette)
        viewport.setAutoFillBackground(True)
        viewport.setPalette(palette)

    def _preview_width(self, view: QGraphicsView) -> int:
        frame = self._page.frameWidth() * 2
        page = self._page.width()
        if page < 48:
            page = _PREVIEW_COLUMN
        cap = max(48, page - frame - (PREVIEW_INSET * 2))
        live = view.width()
        if 48 <= live <= cap:
            return live
        return cap

    def _place_form(self, form: QWidget, proxy: QWidget, view: QGraphicsView, width: int) -> None:
        inner = _layout_inner(form, width)
        for name in _BAR_NAMES:
            _reflow_bar(form, name, inner)
        _fit_tables(form)
        form.setMinimumWidth(0)
        form.setFixedWidth(width)
        layout = form.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        height = form.sizeHint().height()
        if form.hasHeightForWidth():
            height = max(height, form.heightForWidth(width))
        height = max(int(height), form.minimumSizeHint().height(), 1)
        form.setFixedHeight(height)
        proxy.setMinimumWidth(0)  # type: ignore[attr-defined]
        proxy.setMinimumHeight(0)  # type: ignore[attr-defined]
        proxy.resize(width, height)  # type: ignore[attr-defined]
        view.resetTransform()
        view.setSceneRect(0, 0, width, height)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)


def _layout_inner(form: QWidget, width: int) -> int:
    layout = form.layout()
    if layout is None:
        return width
    margins = layout.contentsMargins()
    return max(48, width - margins.left() - margins.right())


def _fit_tables(form: QWidget) -> None:
    resize = getattr(QHeaderView, "ResizeMode", QHeaderView)
    stretch = getattr(resize, "Stretch")
    off = Qt.ScrollBarAlwaysOff
    for view in form.findChildren(QTableView):
        view.setMinimumWidth(0)
        view.setHorizontalScrollBarPolicy(off)
        header = view.horizontalHeader()
        count = header.count()
        if count:
            for index in range(count):
                header.setSectionResizeMode(index, stretch)
        header.setStretchLastSection(True)


def _reflow_bar(form: QWidget, name: str, width: int) -> None:
    host_name = "formBuilder.fromTable.bar." + name
    host = form.findChild(QWidget, host_name)
    bar = form.findChild(QHBoxLayout, name)
    if host is None:
        if bar is None or not _bar_overflows(bar, width):
            return
        widgets = _take_bar(bar)
        if not widgets:
            return
        host = QWidget(form)
        host.setObjectName(host_name)
        host.setMinimumWidth(0)
        host.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(S2)
        bar.addWidget(host)
    else:
        widgets = _take_host(host)
        laid = host.layout()
        if not isinstance(laid, QVBoxLayout):
            return
        column = laid
    if not widgets:
        return
    host.setMaximumWidth(max(width, 1))
    _pack(column, widgets, width)


def _bar_overflows(bar: QHBoxLayout, width: int) -> bool:
    total = 0
    spaces = 0
    for index in range(bar.count()):
        item = bar.itemAt(index)
        if item is None:
            continue
        total += item.sizeHint().width()
        spaces += 1
    if spaces > 1:
        total += max(bar.spacing(), 0) * (spaces - 1)
    return total > width


def _take_bar(bar: QHBoxLayout) -> List[QWidget]:
    widgets = []
    while bar.count():
        item = bar.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            widgets.append(widget)
    return widgets


def _take_host(host: QWidget) -> List[QWidget]:
    widgets: List[QWidget] = []
    column = host.layout()
    if column is None:
        return widgets
    rows = []
    while column.count():
        item = column.takeAt(0)
        if item is None:
            continue
        row = item.layout()
        if row is not None:
            rows.append(row)
    for row in rows:
        while row.count():
            child = row.takeAt(0)
            if child is None:
                continue
            widget = child.widget()
            if widget is not None:
                widgets.append(widget)
        row.deleteLater()
    return widgets


def _pack(column: QVBoxLayout, widgets: List[QWidget], width: int) -> None:
    row = None
    used = 0
    gap = S2
    for widget in widgets:
        hint = _control_width(widget, width)
        if row is not None and used + gap + hint > width:
            row.addStretch(1)
            row = None
            used = 0
        if row is None:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(gap)
            column.addLayout(row)
        elif used:
            used += gap
        row.addWidget(widget)
        used += hint
    if row is not None:
        row.addStretch(1)


def _control_width(widget: QWidget, limit: int) -> int:
    if isinstance(widget, (QLabel, QPushButton)):
        full = widget.property("cbcsFullText")
        if not isinstance(full, str) or not full:
            full = widget.text()
            widget.setProperty("cbcsFullText", full)
        widget.setText(full)
        widget.setMaximumWidth(_WIDGET_MAX)
        hint = max(widget.sizeHint().width(), 1)
        if hint <= limit:
            return hint
        shown = widget.fontMetrics().elidedText(
            full,
            Qt.TextElideMode.ElideRight,  # type: ignore[attr-defined]
            max(8, limit - 8),
        )
        widget.setText(shown)
        widget.setToolTip(full)
        widget.setMaximumWidth(limit)
        return limit
    hint = max(widget.sizeHint().width(), 1)
    if hint > limit:
        widget.setMaximumWidth(limit)
        return limit
    return hint


def _tick_url(chrome: FormChrome) -> str:
    rules = control_qss(chrome)
    mark = "image: url("
    start = rules.find(mark)
    if start < 0:
        return "none"
    start += len(mark)
    end = rules.find(")", start)
    return rules[start:end] if end > start else "none"


def _indicator_qss(selector: str, chrome: FormChrome) -> str:
    edge = edge_on(chrome, chrome.panel)
    image = _tick_url(chrome)
    fill = chrome.input or chrome.panel
    return (
        "%s::indicator { width: 14px; height: 14px; border: 1px solid %s;"
        " border-radius: 3px; background: %s; image: none; }"
        "%s::indicator:checked { border: 1px solid %s; background: %s; image: url(%s); }"
        "%s::indicator:disabled { border: 1px solid %s; background: %s; image: none; }"
        "%s::indicator:checked:disabled { border: 1px solid %s; background: %s; image: url(%s); }"
        % (
            selector, edge, fill,
            selector, chrome.accent, chrome.accent, image,
            selector, edge, fill,
            selector, chrome.accent, chrome.accent, image,
        )
    )


def _field_label(text: str, buddy: QWidget, parent: QWidget) -> QLabel:
    label = QLabel(text, parent)
    label.setBuddy(buddy)
    label.setMinimumWidth(LABEL_MIN)
    return label


def _template_main_bytes(project_root: str) -> Optional[bytes]:
    """``templates/<id>/main.py`` for the project, read from the application root."""

    from app.bootstrap.paths import resolve_app_root
    from app.features.form_builder.engine.project.start_screen import project_template_id

    template_id = project_template_id(project_root)
    if not template_id:
        return None
    path = resolve_app_root() / "templates" / template_id / "main.py"
    if not path.is_file():
        return None
    return path.read_bytes()


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _mapping_row(table: Table, column: Column, engine: str) -> TableColumn:
    choice = choice_for(column, engine)
    return TableColumn(
        column.name,
        column.type,
        include=include_column(column, table.key or "", engine),
        shows_as=choice.shows_as,
        label=choice.label,
    )

