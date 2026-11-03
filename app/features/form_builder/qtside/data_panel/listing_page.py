"""The list form's Data settings. The left pane and the inspector share this page."""

from __future__ import annotations

from typing import Iterable, List, Optional, cast

from app.features.form_builder.engine.data.listing import VALUE_READ
from app.features.form_builder.engine.data.schema import schema_for
from app.features.form_builder.engine.data.source import ListFilter, ListSource
from app.features.form_builder.engine.data.sql import select_source_error
from app.features.form_builder.qtside.data_panel.host import project_root_of, session_of
from app.features.form_builder.qtside.data_panel.listing_edits import (
    clear_own_sql,
    connection_named,
    form_stems,
    set_columns,
    set_filters,
    set_limit,
    set_open,
    set_order,
    set_own_sql,
    set_search,
    set_search_field,
)
from app.features.form_builder.qtside.data_panel.model import connection_title, list_source
from app.features.form_builder.qtside.data_panel.sheets import open_sql_sheet
from app.qt.QtCore import Qt
from app.qt.QtGui import QFont
from app.qt.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value, exec_qt


class OwnSqlDialog(QDialog):
    """The person's SELECT. A bad statement stays on screen with the FB314 sentence."""

    def __init__(self, parent: QWidget, text: str, probe: Optional[object] = None) -> None:
        super().__init__(parent)
        self._probe = probe
        self.setObjectName("formBuilder.data.ownSqlDialog")
        self.setWindowTitle("Use my own SQL")
        layout = QVBoxLayout(self)
        title = QLabel("Your own SQL for this list", self)
        title.setObjectName("formBuilder.data.ownSqlTitle")
        layout.addWidget(title)
        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName("formBuilder.data.ownSqlEdit")
        font = self._edit.font()
        font.setFamily("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        self._edit.setFont(font)
        self._edit.setMinimumHeight(140)
        self._edit.setPlainText(text)
        layout.addWidget(self._edit)
        self._problem = QLabel(self)
        self._problem.setObjectName("formBuilder.data.listSqlProblem")
        self._problem.setWordWrap(True)
        layout.addWidget(self._problem)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        self._ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._edit.textChanged.connect(self._show_problem)
        self._show_problem()
        self.resize(520, 360)

    def sql(self) -> str:
        return self._edit.toPlainText().strip()

    def _show_problem(self) -> None:
        self._mark(select_source_error(self._edit.toPlainText()) or "")

    def _mark(self, problem: str) -> None:
        self._problem.setText(problem)
        self._problem.setProperty("fbProblem", "error" if problem else "")
        style = self._problem.style()
        style.unpolish(self._problem)
        style.polish(self._problem)
        if self._ok is not None:
            self._ok.setEnabled(not problem)

    def _accept(self) -> None:
        problem = select_source_error(self._edit.toPlainText())
        if problem:
            self._mark(problem)
            return
        if callable(self._probe):
            reason = self._probe(self.sql())
            if reason:
                self._mark(str(reason))
                return
        self.accept()


class ListingPage(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.data.listing")
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        self._sentence = QLabel(self)
        self._sentence.setObjectName("formBuilder.data.listSentence")
        self._sentence.setWordWrap(True)
        head.addWidget(self._sentence, 1)
        more = QPushButton("\u22ef", self)
        more.setObjectName("formBuilder.data.listMore")
        menu = QMenu(more)
        menu.addAction("Use my own SQL\u2026", self._own_sql)
        menu.addAction("Use the table", self._use_table)
        menu.addAction("Show SQL", self._show_sql)
        more.setMenu(menu)
        head.addWidget(more)
        layout.addLayout(head)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        layout.addLayout(form)
        layout.addStretch(1)
        column_row = QWidget(self)
        column_layout = QHBoxLayout(column_row)
        column_layout.setContentsMargins(0, 0, 0, 0)
        self._columns = QListWidget(column_row)
        self._columns.setObjectName("formBuilder.data.listColumns")
        self._columns.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._columns.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        column_layout.addWidget(self._columns, 1)
        nudge = QVBoxLayout()
        up = QPushButton("Up", column_row)
        up.setObjectName("formBuilder.data.listColumnUp")
        down = QPushButton("Down", column_row)
        down.setObjectName("formBuilder.data.listColumnDown")
        up.clicked.connect(lambda: self._move_column(-1))
        down.clicked.connect(lambda: self._move_column(1))
        nudge.addWidget(up)
        nudge.addWidget(down)
        nudge.addStretch(1)
        column_layout.addLayout(nudge)
        form.addRow("Columns shown", column_row)
        self._search = QListWidget(self)
        self._search.setObjectName("formBuilder.data.listSearch")
        self._search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form.addRow("Search in", self._search)
        self._search_box = QComboBox(self)
        self._search_box.setObjectName("formBuilder.data.listSearchBox")
        form.addRow("Search box", self._search_box)
        self._filters = QWidget(self)
        self._filters.setObjectName("formBuilder.data.listFilters")
        self._filter_layout = QVBoxLayout(self._filters)
        self._filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_layout.setSpacing(4)
        self._add_filter = QPushButton("+", self._filters)
        self._add_filter.setObjectName("formBuilder.data.listFilterAdd")
        self._add_filter.clicked.connect(self._add_blank_filter)
        self._filter_layout.addWidget(self._add_filter, 0, Qt.AlignmentFlag.AlignLeft)
        form.addRow("Filters", self._filters)
        order_row = QWidget(self)
        order_layout = QHBoxLayout(order_row)
        order_layout.setContentsMargins(0, 0, 0, 0)
        self._order_column = QComboBox(order_row)
        self._order_column.setObjectName("formBuilder.data.listOrder")
        self._order_direction = QComboBox(order_row)
        self._order_direction.setObjectName("formBuilder.data.listOrderDirection")
        self._order_direction.addItem("ascending", "asc")
        self._order_direction.addItem("descending", "desc")
        order_layout.addWidget(self._order_column, 1)
        order_layout.addWidget(self._order_direction)
        form.addRow("Order by", order_row)
        limit_row = QWidget(self)
        limit_layout = QHBoxLayout(limit_row)
        limit_layout.setContentsMargins(0, 0, 0, 0)
        self._limit = QSpinBox(limit_row)
        self._limit.setObjectName("formBuilder.data.listLimit")
        self._limit.setRange(1, 100000)
        limit_layout.addWidget(self._limit)
        limit_layout.addWidget(QLabel("records", limit_row))
        limit_layout.addStretch(1)
        form.addRow("At most", limit_row)
        open_row = QWidget(self)
        open_layout = QHBoxLayout(open_row)
        open_layout.setContentsMargins(0, 0, 0, 0)
        self._open_form = QComboBox(open_row)
        self._open_form.setObjectName("formBuilder.data.listOpenForm")
        self._open_key = QComboBox(open_row)
        self._open_key.setObjectName("formBuilder.data.listOpenKey")
        open_layout.addWidget(self._open_form, 1)
        open_layout.addWidget(QLabel("in a dialog, keyed by", open_row))
        open_layout.addWidget(self._open_key, 1)
        form.addRow("Opens", open_row)
        self._filter_fields: tuple = ()
        self._filter_columns: tuple = ()

        self._columns.model().rowsMoved.connect(self._columns_moved)
        self._columns.itemChanged.connect(self._columns_moved)
        self._search.itemChanged.connect(self._search_changed)
        self._search_box.activated.connect(self._search_box_changed)
        self._order_column.activated.connect(self._order_changed)
        self._order_direction.activated.connect(self._order_changed)
        self._limit.editingFinished.connect(self._limit_changed)
        self._open_form.activated.connect(self._open_changed)
        self._open_key.activated.connect(self._open_changed)

    def refresh(self) -> None:
        session = session_of(self)
        source = list_source(session.document) if session is not None else None
        if source is None:
            self.hide()
            return
        self.show()
        self._loading = True
        try:
            self._fill(session, source)
        finally:
            self._loading = False

    def _fill(self, session: object, source: ListSource) -> None:
        title = connection_title(session, source.connection, self)
        if source.sql.strip():
            self._sentence.setText("Your SQL in %s" % title)
        else:
            self._sentence.setText("List of %s in %s" % (source.table or "records", title))
        names = _column_names(session, source)
        shown = source.columns or names
        _fill_list(self._columns, names or shown, source.columns, check=True)
        search_names = _text_columns(session, source, shown)
        checked = source.search if source.search else search_names
        _fill_list(self._search, search_names, checked, check=True)
        _fit_list(self._columns)
        _fit_list(self._search)
        _fill_combo(self._search_box, _widgets(session, ("QLineEdit",)), source.search_field)
        self._filter_fields = ("",) + _widgets(session, tuple(VALUE_READ))
        self._filter_columns = ("",) + tuple(names)
        self._rebuild_filters(source)
        _fill_combo(self._order_column, ("",) + tuple(names), source.order[0][0] if source.order else "")
        direction = source.order[0][1] if source.order else "asc"
        index = self._order_direction.findData(direction)
        self._order_direction.setCurrentIndex(index if index >= 0 else 0)
        self._limit.setValue(source.limit if source.limit is not None else 500)
        stems = form_stems(project_root_of(self))
        current_form = source.open.form if source.open is not None else ""
        _fill_stems(self._open_form, stems, current_form)
        current_key = source.open.key if source.open is not None else ""
        _fill_combo(self._open_key, ("",) + tuple(names), current_key)

    def _source(self) -> Optional[ListSource]:
        session = session_of(self)
        if session is None:
            return None
        return list_source(session.document)

    def _move_column(self, delta: int) -> None:
        if self._loading:
            return
        row = self._columns.currentRow()
        if row < 0:
            return
        target = row + delta
        if target < 0 or target >= self._columns.count():
            return
        item = self._columns.takeItem(row)
        self._columns.insertItem(target, item)
        self._columns.setCurrentItem(item)
        self._columns_moved()

    def _columns_moved(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        names = []
        for index in range(self._columns.count()):
            item = self._columns.item(index)
            if enum_value(item.checkState()) == enum_value(Qt.Checked):
                names.append(item.text())
        if tuple(names) == source.columns:
            return
        set_columns(session, source, names)

    def _search_changed(self, _item: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        picked = []
        for index in range(self._search.count()):
            item = self._search.item(index)
            if enum_value(item.checkState()) == enum_value(Qt.Checked):
                picked.append(item.text())
        set_search(session, source, picked)

    def _search_box_changed(self, *_args: object) -> None:
        self._save_simple(set_search_field, self._search_box.currentText())

    def _add_blank_filter(self) -> None:
        self._append_filter("", "")

    def _rebuild_filters(self, source: ListSource) -> None:
        while self._filter_layout.count() > 1:
            item = self._filter_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        for entry in source.filters:
            self._append_filter(entry.field, entry.column)
        if not source.filters:
            self._append_filter("", "")

    def _append_filter(self, field: str, column: str) -> None:
        row = QWidget(self._filters)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        widget = QComboBox(row)
        widget.setObjectName("formBuilder.data.listFilterWidget")
        column_box = QComboBox(row)
        column_box.setObjectName("formBuilder.data.listFilterColumn")
        remove = QPushButton("\u00d7", row)
        remove.setObjectName("formBuilder.data.listFilterRemove")
        layout.addWidget(widget, 1)
        layout.addWidget(column_box, 1)
        layout.addWidget(remove)
        self._filter_layout.insertWidget(self._filter_layout.count() - 1, row)
        _fill_combo(widget, self._filter_fields, field)
        _fill_combo(column_box, self._filter_columns, column)
        widget.activated.connect(self._filters_changed)
        column_box.activated.connect(self._filters_changed)
        remove.clicked.connect(lambda: self._remove_filter(row))

    def _remove_filter(self, row: QWidget) -> None:
        if self._loading:
            return
        row.hide()
        row.deleteLater()
        self._filter_layout.removeWidget(row)
        self._filters_changed()

    def _filters_changed(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        filters = []
        for index in range(self._filter_layout.count() - 1):
            row = self._filter_layout.itemAt(index).widget()
            row_layout = None if row is None else row.layout()
            if row_layout is None or row_layout.count() < 2:
                continue
            field_box = row_layout.itemAt(0).widget()
            column_box = row_layout.itemAt(1).widget()
            field = field_box.currentText() if field_box is not None else ""
            column = column_box.currentText() if column_box is not None else ""
            if field and column:
                filters.append(ListFilter(field, column))
        if tuple((item.field, item.column) for item in filters) == tuple(
            (item.field, item.column) for item in source.filters
        ):
            return
        set_filters(session, source, filters)

    def _order_changed(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        direction = self._order_direction.currentData()
        set_order(
            session,
            source,
            self._order_column.currentText(),
            direction if isinstance(direction, str) and direction else "asc",
        )

    def _limit_changed(self) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None or source.limit == self._limit.value():
            return
        set_limit(session, source, self._limit.value())

    def _open_changed(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        form = self._open_form.currentData()
        set_open(session, source, form if isinstance(form, str) else "", self._open_key.currentText())

    def _save_simple(self, writer, value: str) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        writer(session, source, value)

    def _own_sql(self) -> None:
        session = session_of(self)
        source = self._source()
        if session is None or source is None:
            return
        dialog = OwnSqlDialog(self, source.sql, lambda sql: _probe_problem(session, source, sql, self))
        if exec_qt(dialog) != enum_value(QDialog.DialogCode.Accepted):
            return
        columns = _probe_columns(session, source, dialog.sql(), self)
        set_own_sql(session, source, dialog.sql(), columns)
        self.refresh()

    def _use_table(self) -> None:
        session = session_of(self)
        source = self._source()
        if session is None or source is None or not source.sql:
            return
        clear_own_sql(session, source)
        self.refresh()

    def _show_sql(self) -> None:
        open_sql_sheet(self)


def _fill_list(widget: QListWidget, names: tuple, selected: tuple, check: bool) -> None:
    widget.clear()
    ordered = list(selected) + [name for name in names if name not in selected]
    for name in ordered:
        item = QListWidgetItem(name, widget)
        if check:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in selected else Qt.Unchecked)


def _fill_stems(widget: QComboBox, stems: tuple, current: str) -> None:
    widget.clear()
    widget.addItem("", "")
    for stem in stems:
        widget.addItem("%s.ui" % stem, stem)
    if current and widget.findData(current) < 0:
        widget.addItem("%s.ui" % current, current)
    if current:
        index = widget.findData(current)
        if index >= 0:
            widget.setCurrentIndex(index)


def _fit_list(widget: QListWidget) -> None:
    count = widget.count()
    row_height = widget.sizeHintForRow(0) if count else 22
    if row_height < 1:
        row_height = 22
    height = min(max(count, 1) * row_height + widget.frameWidth() * 2 + 6, 160)
    widget.setFixedHeight(height)


def _text_columns(session: object, source: ListSource, shown: tuple) -> tuple:
    cached = schema_for(session.document, source.connection)
    types = {}
    if cached is not None and source.table:
        for table in cached.tables:
            if table.name == source.table:
                types = {column.name: column.type.lower() for column in table.columns}
    found = []
    for name in shown:
        kind = types.get(name, "")
        if not kind or any(token in kind for token in ("char", "text", "string", "name", "clob")):
            found.append(name)
    return tuple(found)


def _fill_combo(widget: QComboBox, names: tuple, current: str) -> None:
    widget.clear()
    for name in names:
        widget.addItem(name)
    if current and widget.findText(current) < 0:
        widget.addItem(current)
    if current:
        widget.setCurrentText(current)


def _column_names(session: object, source: ListSource) -> tuple:
    cached = schema_for(session.document, source.connection)
    if cached is not None and source.table:
        for table in cached.tables:
            if table.name == source.table:
                return tuple(column.name for column in table.columns)
    return tuple(source.columns)


def _widgets(session: object, classes: tuple) -> tuple:
    walk = getattr(session.document, "iter_widgets", None)
    if not callable(walk):
        return ()
    found: List[str] = []
    for node in cast(Iterable[object], walk()):
        if (getattr(node, "class_name", "") or "") not in classes:
            continue
        name = getattr(node, "object_name", "") or ""
        if name and name not in found:
            found.append(name)
    return tuple(found)


def _probe_outcome(session: object, source: ListSource, sql: str, host: QWidget):
    item = connection_named(session, source.connection, host)
    root = project_root_of(host)
    if item is None or not root:
        return None
    from app.features.form_builder.engine.data.schema_cache import probe_select

    from app.features.form_builder.qtside.schema_prompt import ask_connection_secret

    return probe_select(root, item, sql, lambda connection: ask_connection_secret(root, connection))


def _probe_problem(session: object, source: ListSource, sql: str, host: QWidget) -> str:
    outcome = _probe_outcome(session, source, sql, host)
    if outcome is None or outcome.ok or outcome.kind in ("no_driver", "cancelled"):
        return ""
    return outcome.reason or "Only a single SELECT can be a list's source."


def _probe_columns(session: object, source: ListSource, sql: str, host: QWidget) -> tuple:
    outcome = _probe_outcome(session, source, sql, host)
    if outcome is None or not outcome.ok:
        return source.columns
    return tuple(column.name for column in outcome.columns if column.name)

