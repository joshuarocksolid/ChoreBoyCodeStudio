"""Connect, bind-by-name, Show SQL and Python hooks."""

from __future__ import annotations

from typing import Any, List, Optional

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import RecordSource, singular
from app.features.form_builder.qtside.data_panel.chrome import apply_chrome
from app.features.form_builder.qtside.theme.chrome import FormChrome, chrome_from_values
from app.features.form_builder.qtside.theme.items import polish_item_view
from app.features.form_builder.qtside.theme.metrics import CONTROL, ORDER_SEGMENT, S1, S2, TABLE_LIST
from app.features.form_builder.qtside.theme.dialog_body import parts_from
from app.features.form_builder.qtside.theme.segmented import SegmentedControl
from app.features.form_builder.qtside.data_panel.edits import (
    assign_hook,
    bind_named,
    connect_form,
    proposals,
)
from app.features.form_builder.qtside.data_panel.host import narrate, session_of, surface_of
from app.features.form_builder.qtside.data_panel.model import (
    HOOK_ROWS,
    connections_of,
    hook_method,
    order_of,
    record_source,
    record_word,
)
from app.features.form_builder.qtside.data_panel.sql_text import sql_text
from app.qt.QtCore import QEvent, QTimer, Qt
from app.qt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QApplication,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value, exec_qt

_ADD_CONNECTION = "add-connection"

_OPENS = (
    ("First", "first"),
    ("Last", "last"),
    ("A new record", "new"),
    ("Nothing", "none"),
)


def open_connect_sheet(host: Any, tokens: object = None) -> None:
    session = session_of(host)
    if session is None:
        return
    sheet = ConnectSheet(host, session, tokens or getattr(host, "_tokens", None))
    exec_qt(sheet)


def open_bind_sheet(host: Any, tokens: object = None) -> None:
    session = session_of(host)
    if session is None:
        return
    sheet = BindSheet(host, session, tokens or getattr(host, "_tokens", None))
    exec_qt(sheet)


def open_sql_sheet(host: Any, tokens: object = None) -> None:
    session = session_of(host)
    if session is None:
        return
    sheet = SqlDialog(host, session, tokens or getattr(host, "_tokens", None))
    exec_qt(sheet)


def open_hooks_sheet(host: Any, tokens: object = None) -> None:
    session = session_of(host)
    if session is None:
        return
    sheet = HooksDialog(host, session, tokens or getattr(host, "_tokens", None))
    exec_qt(sheet)


def _restore_focus(focus: object) -> None:
    """Filling the table list calls ``setFocus``. Put it back."""

    current = QApplication.focusWidget()
    if focus is None:
        if current is not None and _in_source_form(current):
            current.clearFocus()
        return
    try:
        visible = focus.isVisible()  # type: ignore[attr-defined]
    except RuntimeError:
        return
    if visible and current is not focus:
        focus.setFocus()  # type: ignore[attr-defined]


def _in_source_form(widget: QWidget) -> bool:
    current: Optional[QWidget] = widget
    seen = 0
    while current is not None and seen < 12:
        if current.objectName() == "formBuilder.data.sourceForm":
            return True
        current = current.parentWidget()
        seen += 1
    return False


class SourceForm(QWidget):
    """Connection, table, key, order, opens at, record word. Shared by the sheet and the inspector."""

    def __init__(self, parent: QWidget, session: object) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.sourceForm")
        self._session = session
        self._word_edited = False
        self._loading = False
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(S2)
        layout.setVerticalSpacing(S1)
        layout.setColumnStretch(1, 1)
        self._connection = QComboBox(self)
        self._connection.setObjectName("formBuilder.data.connection")
        self._connection.setFixedHeight(CONTROL)
        self._filter = QLineEdit(self)
        self._filter.setPlaceholderText("Filter tables")
        self._filter.setObjectName("formBuilder.data.tableFilter")
        self._filter.setAccessibleName("Filter tables")
        self._filter.setFixedHeight(CONTROL)
        self._tables = QListWidget(self)
        self._tables.setObjectName("formBuilder.data.tables")
        self._tables.setAccessibleName("Tables")
        self._tables.setFixedHeight(TABLE_LIST)
        self._tables.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._keep = QCheckBox("Let people keep their version on a conflict", self)
        self._keep.setObjectName("formBuilder.data.allowOverwrite")
        self._keep.setAccessibleName("Let people keep their version on a conflict")
        self._key = QLabel(self)
        self._key.setObjectName("formBuilder.data.key")
        self._notice = QLabel(self)
        self._notice.setWordWrap(False)
        self._notice.setProperty("fbFaint", True)
        self._notice.setObjectName("formBuilder.data.keyNotice")
        self._orders = []
        order_box = QWidget(self)
        order_layout = QVBoxLayout(order_box)
        order_layout.setContentsMargins(0, 0, 0, 0)
        order_layout.setSpacing(S1)
        for index in range(3):
            row = QHBoxLayout()
            row.setSpacing(S2)
            order_layout.addLayout(row)
            column = QComboBox(order_box)
            column.setObjectName("formBuilder.data.orderColumn%d" % index)
            column.setAccessibleName("Order by, choice %d" % (index + 1))
            column.setFixedHeight(CONTROL)
            direction = SegmentedControl(order_box)
            direction.setObjectName("formBuilder.data.orderDirection%d" % index)
            direction.setAccessibleName("Order direction, choice %d" % (index + 1))
            direction.setFixedWidth(ORDER_SEGMENT)
            direction.set_items(
                ("\u2191", "\u2193"),
                tooltips=("Ascending", "Descending"),
                names=("Ascending", "Descending"),
            )
            row.addWidget(column, 1)
            row.addWidget(direction)
            self._orders.append((column, direction))
        self._opens = QComboBox(self)
        self._opens.setObjectName("formBuilder.data.opensAt")
        self._opens.setFixedHeight(CONTROL)
        for label, value in _OPENS:
            self._opens.addItem(label, value)
        self._word = QLineEdit(self)
        self._word.setObjectName("formBuilder.data.recordWord")
        self._word.setFixedHeight(CONTROL)
        row_index = 0
        for title, widget in (
            ("Connection", self._connection),
            ("Table", self._filter),
            ("", self._tables),
            ("Key", self._key),
            ("", self._notice),
            ("Order", order_box),
            ("Opens at", self._opens),
            ("Record word", self._word),
            ("", self._keep),
        ):
            if title:
                label = QLabel(title, self)
                label.setBuddy(widget)
                if not (widget.accessibleName() or "").strip():
                    widget.setAccessibleName(title)
                layout.addWidget(label, row_index, 0)
                layout.addWidget(widget, row_index, 1)
            else:
                layout.addWidget(widget, row_index, 0, 1, 2)
            row_index += 1
        self._chrome: Optional[FormChrome] = None
        self._add_connection: Optional[Any] = None
        self._kept_connection = 0
        self._connection.currentIndexChanged.connect(self._on_connection)
        self._filter.textChanged.connect(self._apply_filter)
        self._tables.currentItemChanged.connect(lambda _cur, _prev: self._on_table())
        self._word.textEdited.connect(self._on_word)
        self.reload()

    def set_session(self, session: object) -> None:
        self._session = session

    def apply_tokens(self, tokens: object) -> None:
        if tokens is None:
            return
        chrome = chrome_from_values(
            window=str(getattr(tokens, "window_bg", "") or ""),
            panel=str(getattr(tokens, "panel_bg", "") or ""),
            text=str(getattr(tokens, "text_primary", "") or ""),
            muted=str(getattr(tokens, "text_muted", "") or ""),
            faint=str(getattr(tokens, "gutter_text", "") or ""),
            border=str(getattr(tokens, "border", "") or ""),
            accent=str(getattr(tokens, "accent", "") or ""),
            row_hover=str(getattr(tokens, "tree_hover_bg", "") or ""),
            input_bg=str(getattr(tokens, "input_bg", "") or ""),
            error=str(getattr(tokens, "diag_error_color", "") or ""),
            focus_width=int(getattr(tokens, "focus_border_width", 1) or 1),
            selected=str(getattr(tokens, "tree_selected_bg", "") or ""),
            is_dark=bool(getattr(tokens, "is_dark", False)),
            is_high_contrast=bool(getattr(tokens, "is_high_contrast", False)),
        )
        self._chrome = chrome
        for _column, direction in self._orders:
            direction.apply_chrome(chrome)
        polish_item_view(self._tables, chrome)
        _paint_list_input(self._tables, chrome)

    def reload(self) -> None:
        focus = QApplication.focusWidget()
        self._loading = True
        self._connection.blockSignals(True)
        self._connection.clear()
        for item in connections_of(self._session, self):
            self._connection.addItem(item.title or item.name, item.name)
        if self._add_connection is not None:
            self._connection.addItem("Add a connection\u2026", _ADD_CONNECTION)
        self._connection.blockSignals(False)
        self._reload_tables()
        self._loading = False
        _restore_focus(focus)
        QTimer.singleShot(0, lambda: _restore_focus(focus))

    def load(self, source: Optional[RecordSource]) -> None:
        self._loading = True
        self.reload()
        if source is None:
            self._word_edited = False
            self._keep.setChecked(False)
            self._on_table()
            self._loading = False
            return
        index = self._connection.findData(source.connection)
        if index >= 0:
            self._connection.setCurrentIndex(index)
            self._reload_tables()
        self._select_table(source.table)
        self._fill_order(order_of(source))
        open_at = source.open_at or "first"
        found = self._opens.findData(open_at)
        if found >= 0:
            self._opens.setCurrentIndex(found)
        self._word.setText(record_word(source))
        self._word_edited = source.record_word not in (None, "")
        self._keep.setChecked(bool(source.allow_overwrite or source.conflicts == "overwrite"))
        self._loading = False

    def source(self) -> Optional[RecordSource]:
        item = self._tables.currentItem()
        if item is None or not _item_enabled(item):
            return None
        connection = self._connection.currentData()
        if connection == _ADD_CONNECTION:
            return None
        table = item.data(int(enum_value(Qt.ItemDataRole.UserRole)))
        key = item.data(int(enum_value(Qt.ItemDataRole.UserRole)) + 1)
        if not connection or not table or not key:
            return None
        order = self._order_value(str(key))
        open_at = self._opens.currentData()
        word = self._word.text().strip()
        default_word = singular(str(table))
        return RecordSource(
            str(connection),
            str(table),
            str(key),
            record_word=None if not word or word == default_word else word,
            order=None if order == ((str(key), "asc"),) else order,
            open_at=None if open_at in (None, "", "first") else str(open_at),
            allow_overwrite=self._keep.isChecked(),
        )

    def offer_add_connection(self, callback: Any) -> None:
        self._add_connection = callback

    def _on_connection(self, index: int) -> None:
        if self._connection.itemData(index) == _ADD_CONNECTION:
            self._connection.blockSignals(True)
            keep = self._kept_connection
            if keep < 0 or keep >= self._connection.count() or self._connection.itemData(keep) == _ADD_CONNECTION:
                keep = 0
            self._connection.setCurrentIndex(keep)
            self._connection.blockSignals(False)
            callback = self._add_connection
            if callable(callback):
                callback()
            return
        self._kept_connection = index
        self._reload_tables()

    def _reload_tables(self) -> None:
        chosen = self._tables.currentItem()
        previous = ""
        if chosen is not None:
            previous = str(chosen.data(int(enum_value(Qt.ItemDataRole.UserRole))) or "")
        self._tables.clear()
        name = self._connection.currentData()
        cached = schema_for(self._session.document, str(name or ""))
        tables = tuple(getattr(cached, "tables", ()) or ())
        role = int(enum_value(Qt.ItemDataRole.UserRole))
        enabled_flag = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        for table in tables:
            item = QListWidgetItem(table.name)
            item.setData(role, table.name)
            item.setData(role + 1, table.key or "")
            if not table.key:
                sentence = "%s has no single key column. Record forms need one." % table.name
                item.setText("%s — %s" % (table.name, sentence))
                item.setToolTip(sentence)
                item.setFlags(Qt.ItemFlag.NoItemFlags)
            else:
                item.setFlags(enabled_flag)
            self._tables.addItem(item)
        self._apply_filter(self._filter.text())
        if previous:
            self._select_table(previous)
        else:
            for row in range(self._tables.count()):
                candidate = self._tables.item(row)
                if candidate is not None and _item_enabled(candidate) and not candidate.isHidden():
                    self._tables.setCurrentRow(row)
                    break
        self._on_table()

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self._tables.count()):
            item = self._tables.item(row)
            visible = not needle or needle in item.text().lower()
            item.setHidden(not visible)

    def _select_table(self, name: str) -> None:
        role = int(enum_value(Qt.ItemDataRole.UserRole))
        focus = QApplication.focusWidget()
        for row in range(self._tables.count()):
            item = self._tables.item(row)
            if item.data(role) == name and _item_enabled(item):
                self._tables.setCurrentItem(item)
                _restore_focus(focus)
                return

    def _on_table(self) -> None:
        item = self._tables.currentItem()
        role = int(enum_value(Qt.ItemDataRole.UserRole))
        if item is None or not _item_enabled(item):
            self._key.setText("")
            self._notice.setText("")
            self._fill_columns(())
            return
        table = str(item.data(role) or "")
        key = str(item.data(role + 1) or "")
        self._key.setText(key)
        if not key:
            self._notice.setText("%s has no single key column. Record forms need one." % table)
        else:
            self._notice.setText("")
        self._fill_columns(_column_names(self._session, self._connection.currentData(), table), key)
        if not self._word_edited:
            self._word.setText(singular(table))

    def _on_word(self) -> None:
        if not self._loading:
            self._word_edited = True

    def _fill_columns(self, names: tuple, key: str = "") -> None:
        for index, (column, _direction) in enumerate(self._orders):
            column.blockSignals(True)
            column.clear()
            column.addItem("(none)", "")
            for name in names:
                column.addItem(name, name)
            if index == 0 and key:
                found = column.findData(key)
                if found >= 0:
                    column.setCurrentIndex(found)
            column.blockSignals(False)

    def _fill_order(self, pairs: tuple) -> None:
        names = _column_names(self._session, self._connection.currentData(), _current_table(self._tables))
        key = pairs[0][0] if pairs else ""
        self._fill_columns(names, key)
        for index, (column, direction) in enumerate(self._orders):
            if index < len(pairs):
                name, way = pairs[index]
                found = column.findData(name)
                if found >= 0:
                    column.setCurrentIndex(found)
                direction.set_current_index(1 if way == "desc" else 0)
            elif index:
                column.setCurrentIndex(0)

    def _order_value(self, key: str) -> tuple:
        pairs = []
        for column, direction in self._orders:
            name = column.currentData()
            if not name:
                continue
            pairs.append((str(name), "desc" if direction.current_index() == 1 else "asc"))
            if len(pairs) == 3:
                break
        if not pairs and key:
            return ((key, "asc"),)
        return tuple(pairs)


class ConnectSheet(QDialog):
    def __init__(self, host: QWidget, session: object, tokens: object = None) -> None:
        super().__init__(host)
        self._session = session
        build, add_button, add_stretch, primary, secondary = parts_from(host)
        dialog = build(
            self,
            title="Connect to a table",
            object_name="formBuilder.data.connectSheet",
        )
        self._form = SourceForm(dialog.body, session)
        self._form.offer_add_connection(self._open_connections)
        dialog.body.layout().addWidget(self._form)
        self._error = QLabel(dialog.body)
        self._error.setWordWrap(False)
        self._error.setProperty("fbProblem", "warning")
        dialog.body.layout().addWidget(self._error)
        add_stretch(dialog)
        cancel = add_button(dialog, "Cancel", role=secondary)
        cancel.clicked.connect(self.reject)
        self._ok = add_button(dialog, "Connect", role=primary, default=True)
        self._ok.setObjectName("formBuilder.data.connectOk")
        self._ok.setAccessibleName("Connect")
        self._ok.clicked.connect(self._commit)
        self._form.load(record_source(session.document))
        self._applied_tokens = tokens
        self._form.apply_tokens(tokens)
        self.resize(480, 560)
        if tokens is not None:
            apply_chrome(self, tokens)

    def changeEvent(self, event: QEvent) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == _STYLE_CHANGE and hasattr(self, "_applied_tokens"):
            self._follow_host()

    def _follow_host(self) -> None:
        tokens = _host_tokens(self)
        if tokens is None or tokens == self._applied_tokens:
            return
        self._applied_tokens = tokens
        self._form.apply_tokens(tokens)
        apply_chrome(self, tokens)

    def _open_connections(self) -> None:
        host = self.parent()
        signal = getattr(host, "add_connection_requested", None)
        emit = getattr(signal, "emit", None)
        if callable(emit):
            emit()
        self._form.reload()

    def _commit(self) -> None:
        source = self._form.source()
        if source is None:
            self._error.setText("Choose a table with one key column.")
            return
        try:
            connect_form(self._session, source)
        except CommandRejected as exc:
            self._error.setText(str(exc))
            return
        self.accept()


class BindSheet(QDialog):
    def __init__(self, host: QWidget, session: object, tokens: object = None) -> None:
        super().__init__(host)
        self.setObjectName("formBuilder.data.bindSheet")
        self.setWindowTitle("Bind fields by name")
        self._session = session
        self._boxes: List[QCheckBox] = []
        layout = QVBoxLayout(self)
        self._rows = QVBoxLayout()
        layout.addLayout(self._rows)
        buttons = QHBoxLayout()
        layout.addLayout(buttons)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel", self)
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        self._ok = QPushButton("Bind 0", self)
        self._ok.setObjectName("formBuilder.data.bindOk")
        self._ok.clicked.connect(self.accept_bind)
        buttons.addWidget(self._ok)
        self.refresh()
        self.resize(420, 360)
        if tokens is not None:
            apply_chrome(self, tokens)

    def refresh(self) -> None:
        while self._rows.count():
            item = self._rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._boxes = []
        for object_name, column in proposals(self._session):
            box = QCheckBox("%s → %s" % (object_name, column), self)
            box.setChecked(True)
            box.setProperty("objectNameBinding", object_name)
            box.setProperty("column", column)
            box.toggled.connect(self._recount)
            self._rows.addWidget(box)
            self._boxes.append(box)
        if not self._boxes:
            empty = QLabel("No unbound fields match a column.", self)
            empty.setProperty("fbFaint", True)
            self._rows.addWidget(empty)
        self._recount()

    def preview_text(self) -> str:
        return "\n".join(box.text() for box in self._boxes)

    def _recount(self) -> None:
        count = sum(1 for box in self._boxes if box.isChecked())
        self._ok.setText("Bind %d" % count)
        self._ok.setEnabled(count > 0)

    def accept_bind(self) -> None:
        pairs = [
            (str(box.property("objectNameBinding")), str(box.property("column")))
            for box in self._boxes
            if box.isChecked()
        ]
        try:
            bind_named(self._session, pairs)
        except CommandRejected as exc:
            narrate(self, str(exc))
            return
        self.accept()


class SqlDialog(QDialog):
    def __init__(self, host: QWidget, session: object, tokens: object = None) -> None:
        super().__init__(host)
        self.setObjectName("formBuilder.data.sqlDialog")
        self.setWindowTitle("Show SQL")
        self._session = session
        layout = QVBoxLayout(self)
        self._view = QPlainTextEdit(self)
        self._view.setObjectName("formBuilder.data.sqlView")
        self._view.setReadOnly(True)
        layout.addWidget(self._view)
        row = QHBoxLayout()
        layout.addLayout(row)
        copy = QPushButton("Copy all", self)
        copy.setObjectName("formBuilder.data.sqlCopy")
        copy.clicked.connect(self._copy)
        row.addWidget(copy)
        row.addStretch(1)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        self.refresh()
        self.resize(640, 480)
        if tokens is not None:
            apply_chrome(self, tokens)

    def refresh(self) -> None:
        self._view.setPlainText(sql_text(self._session, self))

    def text(self) -> str:
        return self._view.toPlainText()

    def _copy(self) -> None:
        from app.qt.QtWidgets import QApplication

        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.text())


class HooksDialog(QDialog):
    def __init__(self, host: QWidget, session: object, tokens: object = None) -> None:
        super().__init__(host)
        self.setObjectName("formBuilder.data.hooks")
        self.setWindowTitle("Python hooks")
        self._session = session
        self._host = host
        layout = QVBoxLayout(self)
        self._body = QVBoxLayout()
        layout.addLayout(self._body)
        close = QPushButton("Close", self)
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.refresh()
        self.resize(460, 360)
        if tokens is not None:
            apply_chrome(self, tokens)

    def refresh(self) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        source = record_source(self._session.document)
        for field, label, method, _params in HOOK_ROWS:
            row_widget = QWidget(self)
            row = QHBoxLayout(row_widget)
            row.setContentsMargins(0, 0, 0, 0)
            title = QLabel(label, row_widget)
            row.addWidget(title, 1)
            current = hook_method(source, field) if source is not None else ""
            if current:
                link = QPushButton(current, row_widget)
                link.clicked.connect(lambda _checked=False, name=current: self._open(name))
                row.addWidget(link)
            else:
                none = QLabel("none", row_widget)
                none.setProperty("fbFaint", True)
                row.addWidget(none)
                create = QPushButton("Create", row_widget)
                create.clicked.connect(lambda _checked=False, key=field, name=method: self._create(key, name))
                row.addWidget(create)
            self._body.addWidget(row_widget)

    def _create(self, field: str, method: str) -> None:
        try:
            note = assign_hook(self._session, field, method, surface_of(self._host))
        except CommandRejected as exc:
            narrate(self, str(exc))
            return
        if note:
            narrate(self, note)
        self.refresh()

    def _open(self, method: str) -> None:
        surface = surface_of(self._host)
        if surface is None:
            return
        from app.features.form_builder.qtside.pickers import method_actions

        service = method_actions()
        go_to = getattr(service, "go_to", None)
        if not callable(go_to):
            return
        go_to(surface, method)


def _paint_list_input(view: QListWidget, chrome: FormChrome) -> None:
    """The table list is a chrome field. Item-view polish fills it with the panel."""
    fill = chrome.input or chrome.panel
    if not fill or fill == chrome.panel:
        return
    sheet = view.styleSheet()
    needle = "background: %s;" % chrome.panel
    if needle not in sheet:
        return
    view.setStyleSheet(sheet.replace(needle, "background: %s;" % fill, 1))


def _host_tokens(widget: QWidget) -> object:
    """Shell tokens from the host that owns the theme, walking past a dialog window."""
    current: Optional[QWidget] = widget
    seen = 0
    while current is not None and seen < 8:
        workflow = getattr(current, "_shell_theme_workflow", None)
        resolve = getattr(workflow, "resolve_theme_tokens", None)
        if callable(resolve):
            return resolve()
        current = current.parentWidget()
        seen += 1
    return None


_STYLE_CHANGE = getattr(getattr(QEvent, "Type", QEvent), "StyleChange")


def _item_enabled(item: QListWidgetItem) -> bool:
    return bool(enum_value(item.flags()) & enum_value(Qt.ItemFlag.ItemIsEnabled))


def _current_table(tables: QListWidget) -> str:
    item = tables.currentItem()
    if item is None:
        return ""
    return str(item.data(int(enum_value(Qt.ItemDataRole.UserRole))) or "")


def _column_names(session: object, connection: object, table: str) -> tuple:
    if not connection or not table:
        return ()
    cached = schema_for(session.document, str(connection))
    if cached is None:
        return ()
    for item in cached.tables:
        if item.name == table:
            return tuple(column.name for column in item.columns)
    return ()
