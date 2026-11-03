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
        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName("formBuilder.data.ownSqlEdit")
        self._edit.setPlainText(text)
        layout.addWidget(self._edit)
        self._problem = QLabel(self)
        self._problem.setObjectName("formBuilder.data.listSqlProblem")
        self._problem.setWordWrap(True)
        layout.addWidget(self._problem)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._edit.textChanged.connect(self._show_problem)
        self._show_problem()
        self.resize(520, 320)

    def sql(self) -> str:
        return self._edit.toPlainText().strip()

    def _show_problem(self) -> None:
        self._problem.setText(select_source_error(self._edit.toPlainText()) or "")

    def _accept(self) -> None:
        problem = select_source_error(self._edit.toPlainText())
        if problem:
            self._problem.setText(problem)
            return
        if callable(self._probe):
            reason = self._probe(self.sql())
            if reason:
                self._problem.setText(str(reason))
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
        layout.addLayout(form)
        self._columns = QListWidget(self)
        self._columns.setObjectName("formBuilder.data.listColumns")
        self._columns.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._columns.setFixedHeight(96)
        form.addRow("Columns shown", self._columns)
        self._search = QListWidget(self)
        self._search.setObjectName("formBuilder.data.listSearch")
        self._search.setFixedHeight(96)
        form.addRow("Search in", self._search)
        self._search_box = QComboBox(self)
        self._search_box.setObjectName("formBuilder.data.listSearchBox")
        form.addRow("Search box", self._search_box)
        filter_row = QWidget(self)
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        self._filter_widget = QComboBox(filter_row)
        self._filter_widget.setObjectName("formBuilder.data.listFilterWidget")
        self._filter_column = QComboBox(filter_row)
        self._filter_column.setObjectName("formBuilder.data.listFilterColumn")
        filter_layout.addWidget(self._filter_widget)
        filter_layout.addWidget(self._filter_column)
        form.addRow("Filters", filter_row)
        order_row = QWidget(self)
        order_layout = QHBoxLayout(order_row)
        order_layout.setContentsMargins(0, 0, 0, 0)
        self._order_column = QComboBox(order_row)
        self._order_column.setObjectName("formBuilder.data.listOrder")
        self._order_direction = QComboBox(order_row)
        self._order_direction.setObjectName("formBuilder.data.listOrderDirection")
        self._order_direction.addItem("asc")
        self._order_direction.addItem("desc")
        order_layout.addWidget(self._order_column)
        order_layout.addWidget(self._order_direction)
        form.addRow("Order by", order_row)
        self._limit = QSpinBox(self)
        self._limit.setObjectName("formBuilder.data.listLimit")
        self._limit.setRange(1, 100000)
        self._limit.setSuffix(" records")
        form.addRow("At most", self._limit)
        open_row = QWidget(self)
        open_layout = QHBoxLayout(open_row)
        open_layout.setContentsMargins(0, 0, 0, 0)
        self._open_form = QComboBox(open_row)
        self._open_form.setObjectName("formBuilder.data.listOpenForm")
        self._open_key = QComboBox(open_row)
        self._open_key.setObjectName("formBuilder.data.listOpenKey")
        open_layout.addWidget(self._open_form)
        opens_in = QLabel("in a dialog", open_row)
        open_layout.addWidget(opens_in)
        open_layout.addWidget(self._open_key)
        form.addRow("Opens", open_row)

        self._columns.model().rowsMoved.connect(self._columns_moved)
        self._search.itemChanged.connect(self._search_changed)
        self._search_box.activated.connect(self._search_box_changed)
        self._filter_widget.activated.connect(self._filter_changed)
        self._filter_column.activated.connect(self._filter_changed)
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
        _fill_list(self._columns, source.columns, source.columns, check=False)
        _fill_list(self._search, source.columns or names, source.search, check=True)
        _fill_combo(self._search_box, _widgets(session, ("QLineEdit",)), source.search_field)
        _fill_combo(self._filter_widget, ("",) + _widgets(session, tuple(VALUE_READ)), _first_filter(source).field)
        _fill_combo(self._filter_column, ("",) + tuple(names), _first_filter(source).column)
        _fill_combo(self._order_column, ("",) + tuple(names), source.order[0][0] if source.order else "")
        direction = source.order[0][1] if source.order else "asc"
        self._order_direction.setCurrentText(direction if direction in ("asc", "desc") else "asc")
        self._limit.setValue(source.limit if source.limit is not None else 500)
        stems = form_stems(project_root_of(self))
        current_form = source.open.form if source.open is not None else ""
        _fill_combo(self._open_form, ("",) + stems, current_form)
        current_key = source.open.key if source.open is not None else ""
        _fill_combo(self._open_key, ("",) + tuple(names), current_key)

    def _source(self) -> Optional[ListSource]:
        session = session_of(self)
        if session is None:
            return None
        return list_source(session.document)

    def _columns_moved(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        names = [self._columns.item(index).text() for index in range(self._columns.count())]
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

    def _filter_changed(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        field = self._filter_widget.currentText()
        column = self._filter_column.currentText()
        filters = (ListFilter(field, column),) if field and column else ()
        set_filters(session, source, filters)

    def _order_changed(self, *_args: object) -> None:
        if self._loading:
            return
        source = self._source()
        session = session_of(self)
        if source is None or session is None:
            return
        set_order(session, source, self._order_column.currentText(), self._order_direction.currentText() or "asc")

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
        set_open(session, source, self._open_form.currentText(), self._open_key.currentText())

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


def _fill_combo(widget: QComboBox, names: tuple, current: str) -> None:
    widget.clear()
    for name in names:
        widget.addItem(name)
    if current and widget.findText(current) < 0:
        widget.addItem(current)
    if current:
        widget.setCurrentText(current)


def _first_filter(source: ListSource) -> ListFilter:
    if source.filters:
        return source.filters[0]
    return ListFilter("", "")


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

    return probe_select(root, item, sql, lambda _connection: "")


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

