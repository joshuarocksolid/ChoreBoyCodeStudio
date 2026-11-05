"""Settings › Connections (UX-CONN-001). Project scope."""

from __future__ import annotations

import os
from dataclasses import replace
from typing import Any, Dict, List, Optional

from app.qt.QtCore import QEvent, QThread, Qt, QTimer
from app.qt.QtWidgets import (
    QCheckBox,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from app.qt.qt_compat import enum_value, exec_qt
from app.shell.settings_pages import SCOPE_PROJECT, SettingsPage, SettingsRefusal, register_settings_page
from app.shell.style_sheet_sections_controls import shell_section_checkbox_indicators
from app.shell.theme_tokens import ShellThemeTokens, tokens_from_palette

from app.features.form_builder.engine.data.connections import (
    ILLEGAL_NAME_SENTENCE,
    NAME_RE,
    OUTSIDE_PROJECT_SENTENCE,
    Connection,
    ConnectionSet,
    code_name_from_title,
    load_connections,
    read_connections,
    write_connections,
)
from app.features.form_builder.engine.data.connections_module import (
    ensure_connection_setup,
    save_project_connections,
)
from app.features.form_builder.integration.connection_paths import (
    load_project_machine,
    project_slug,
    rename_project_entry,
)
from app.features.form_builder.engine.data.schema_cache import cancel_schema_work, install_schema_reader
from app.features.form_builder.engine.data.tester import connection_tester, probe_sqlite
from app.features.form_builder.qtside.schema_prompt import ask_connection_secret, install_secret_marshal
from app.features.form_builder.engine.project.closed_forms import (
    forms_using_connection,
    rename_connection,
    rewrite_forms,
)
from app.features.form_builder.engine.project.fs import ProjectOpError, inside_project, relative_posix

MACHINE_WARNING = "This password file can be read by other users of this computer."
POSTGRES_PLACEHOLDER = "Testing PostgreSQL arrives with the schema helper."
_UNDO = "Update connection name"


def open_sessions(project_root: str) -> Dict[str, object]:
    """Open form sessions in this process, keyed by absolute ``.ui`` path."""

    del project_root
    from app.qt.QtWidgets import QApplication
    from app.features.form_builder.integration.surface import FormSurface

    app = QApplication.instance()
    found: Dict[str, object] = {}
    if app is None:
        return found
    for widget in app.allWidgets():
        if isinstance(widget, FormSurface):
            session = widget.session
            found[os.path.abspath(session.path)] = session
    return found


def engine_line(connection: Connection) -> str:
    if connection.engine == "sqlite":
        return "SQLite · %s" % (connection.file or "")
    host = connection.host or ""
    if connection.port not in (None, 5432):
        host = "%s:%s" % (host, connection.port)
    return "PostgreSQL · %s@%s/%s" % (connection.user or "", host, connection.database or "")


def remove_sentence(name: str, stems: List[str]) -> str:
    if len(stems) == 1:
        return "%s is used by %s. Remove it from that form first." % (name, stems[0])
    if len(stems) == 2:
        return "%s is used by %s and %s. Remove it from those forms first." % (name, stems[0], stems[1])
    return "%s is used by %s and %s. Remove it from those forms first." % (
        name,
        ", ".join(stems[:-1]),
        stems[-1],
    )


def rename_sentence(count: int, name: str) -> str:
    if count == 1:
        return "1 form uses %s. Update it?" % name
    return "%d forms use %s. Update them?" % (count, name)


def build_rename_question(parent: Optional[QWidget], sentence: str) -> QDialog:
    dialog = QDialog(parent)
    dialog.setObjectName("formBuilder.connections.renameQuestion")
    dialog.setWindowTitle("Update connection name")
    layout = QVBoxLayout(dialog)
    label = QLabel(sentence, dialog)
    label.setWordWrap(True)
    label.setObjectName("formBuilder.connections.renameText")
    layout.addWidget(label)
    row = QHBoxLayout()
    layout.addLayout(row)
    row.addStretch(1)
    update = QPushButton("Update", dialog)
    update.setObjectName("formBuilder.connections.renameUpdate")
    update.setDefault(True)
    cancel = QPushButton("Cancel", dialog)
    cancel.setObjectName("formBuilder.connections.renameCancel")
    update.clicked.connect(dialog.accept)
    cancel.clicked.connect(dialog.reject)
    row.addWidget(update)
    row.addWidget(cancel)
    dialog.resize(440, 160)
    return dialog


class _Worker(QThread):
    """Runs one connection test. The result sits on the instance; the page polls it."""

    def __init__(self, fn: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._fn = fn
        self.payload: object = None

    def run(self) -> None:
        try:
            self.payload = self._fn()
        except Exception as exc:
            lines = str(exc).splitlines()
            self.payload = {"text": lines[0] if lines else "Can't connect."}
        self._ready = True


class _Row(QWidget):
    def __init__(self, title: str, engine: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(0)
        self.title_label = QLabel(title, self)
        self.engine_label = QLabel(engine, self)
        self.engine_label.setObjectName("formBuilder.connections.engine")
        layout.addWidget(self.title_label)
        layout.addWidget(self.engine_label)


class ConnectionsPage(QWidget):
    def __init__(self, parent: Optional[QWidget], project_root: str) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.connections.page")
        self._root = project_root
        self._items: List[Connection] = []
        self._touched: List[bool] = []
        self._top_unknown: tuple = ()
        self._index = -1
        self._pending = ""
        self._setup_name: Optional[str] = None
        self._loading = False
        self._testing = False
        self._generation = 0
        self._filtered = False
        self._tokens: object = None
        self._workers: Dict[int, _Worker] = {}

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 12, 16, 12)
        column.setSpacing(8)

        self._machine = QLabel(self)
        self._machine.setObjectName("formBuilder.connections.machineWarning")
        self._machine.setWordWrap(True)
        self._machine.hide()
        column.addWidget(self._machine)

        self._refusal = QLabel(self)
        self._refusal.setObjectName("formBuilder.connections.refusal")
        self._refusal.setWordWrap(True)
        self._refusal.hide()
        column.addWidget(self._refusal)

        self._empty = QLabel("No connections yet. Add one to bind forms to a database.", self)
        self._empty.setObjectName("formBuilder.connections.empty")
        self._empty.setWordWrap(True)
        column.addWidget(self._empty)

        empty_buttons = QHBoxLayout()
        column.addLayout(empty_buttons)
        self._add_sqlite = QPushButton("+ Add SQLite file", self)
        self._add_sqlite.setObjectName("formBuilder.connections.addSqlite")
        self._add_postgres = QPushButton("+ Add PostgreSQL", self)
        self._add_postgres.setObjectName("formBuilder.connections.addPostgres")
        self._add_sqlite.clicked.connect(lambda: self._add_connection("sqlite"))
        self._add_postgres.clicked.connect(lambda: self._add_connection("postgres"))
        empty_buttons.addWidget(self._add_sqlite)
        empty_buttons.addWidget(self._add_postgres)
        empty_buttons.addStretch(1)
        self._empty_buttons = (self._add_sqlite, self._add_postgres)

        body = QHBoxLayout()
        column.addLayout(body, 1)
        left = QVBoxLayout()
        body.addLayout(left, 1)
        self._list = QListWidget(self)
        self._list.setObjectName("formBuilder.connections.list")
        self._list.currentRowChanged.connect(self._on_row)
        left.addWidget(self._list, 1)
        actions = QHBoxLayout()
        left.addLayout(actions)
        self._add = QPushButton("+ Add", self)
        self._add.setObjectName("formBuilder.connections.add")
        menu = QMenu(self._add)
        menu.addAction("SQLite file", lambda: self._add_connection("sqlite"))
        menu.addAction("PostgreSQL", lambda: self._add_connection("postgres"))
        self._add.setMenu(menu)
        self._duplicate = QPushButton("Duplicate", self)
        self._duplicate.setObjectName("formBuilder.connections.duplicate")
        self._remove = QPushButton("Remove", self)
        self._remove.setObjectName("formBuilder.connections.remove")
        self._duplicate.clicked.connect(self._duplicate_current)
        self._remove.clicked.connect(self._remove_current)
        actions.addWidget(self._add)
        actions.addWidget(self._duplicate)
        actions.addWidget(self._remove)
        actions.addStretch(1)

        self._editor = QWidget(self)
        self._editor.setObjectName("formBuilder.connections.editor")
        form = QFormLayout(self._editor)
        form.setSpacing(8)
        self._form = form
        self._title = QLineEdit(self._editor)
        self._title.setObjectName("formBuilder.connections.title")
        self._code = QLineEdit(self._editor)
        self._code.setObjectName("formBuilder.connections.code")
        self._title.textEdited.connect(self._on_title)
        self._title.editingFinished.connect(self._on_code_finished)
        self._code.textEdited.connect(self._on_code_edited)
        self._code.editingFinished.connect(self._on_code_finished)
        form.addRow("Name", self._title)
        form.addRow("Code", self._code)

        file_row = QHBoxLayout()
        self._file_row = file_row
        form.addRow("File", file_row)
        self._file = QLineEdit(self._editor)
        self._file.setObjectName("formBuilder.connections.file")
        self._choose = QPushButton("Choose\u2026", self._editor)
        self._choose.setObjectName("formBuilder.connections.choose")
        self._choose.clicked.connect(self._choose_file)
        self._file.editingFinished.connect(self._on_field)
        file_row.addWidget(self._file, 1)
        file_row.addWidget(self._choose)

        self._host = QLineEdit(self._editor)
        self._host.setObjectName("formBuilder.connections.host")
        self._port = QSpinBox(self._editor)
        self._port.setObjectName("formBuilder.connections.port")
        self._port.setRange(1, 65535)
        self._port.setValue(5432)
        self._database = QLineEdit(self._editor)
        self._database.setObjectName("formBuilder.connections.database")
        self._user = QLineEdit(self._editor)
        self._user.setObjectName("formBuilder.connections.user")
        self._schema = QLineEdit(self._editor)
        self._schema.setObjectName("formBuilder.connections.schema")
        self._password = QComboBox(self._editor)
        self._password.setObjectName("formBuilder.connections.password")
        self._password.addItem("Ask when the app starts", "ask")
        self._password.addItem("Remember on this machine", "machine")
        self._password.addItem("No password", "none")
        for widget in (self._host, self._database, self._user, self._schema):
            widget.editingFinished.connect(self._on_field)
        self._port.editingFinished.connect(self._on_field)
        self._password.currentIndexChanged.connect(self._on_field)
        form.addRow("Host", self._host)
        form.addRow("Port", self._port)
        form.addRow("Database", self._database)
        form.addRow("User", self._user)
        form.addRow("Schema", self._schema)
        form.addRow("Password", self._password)
        self._postgres_fields = (
            self._host,
            self._port,
            self._database,
            self._user,
            self._schema,
            self._password,
        )

        # One label column width for both engines, so every field starts at the same x.
        label_width = max(
            self.fontMetrics().horizontalAdvance(text) for text in ("Name", "Code", "File", "Host", "Port", "Database", "User", "Schema", "Password", "Setup")
        )
        for field in (self._title, self._code, self._file_row, self._host, self._port, self._database, self._user, self._schema, self._password):
            label = form.labelForField(field)
            if label is not None:
                label.setMinimumWidth(label_width)

        setup_row = QHBoxLayout()
        form.addRow("Setup", setup_row)
        self._setup = QLabel("none", self._editor)
        self._setup.setObjectName("formBuilder.connections.setup")
        self._create_setup_button = QPushButton("Create setup function", self._editor)
        self._create_setup_button.setObjectName("formBuilder.connections.createSetup")
        self._create_setup_button.clicked.connect(self._create_setup)
        setup_row.addWidget(self._setup)
        setup_row.addWidget(self._create_setup_button)
        setup_row.addStretch(1)

        self._try_sql = QCheckBox("In Try, only show the SQL", self._editor)
        self._try_sql.setObjectName("formBuilder.connections.trySql")
        self._try_sql.toggled.connect(self._on_field)
        form.addRow("", self._try_sql)

        test_row = QHBoxLayout()
        form.addRow("", test_row)
        self._test_button = QPushButton("Test", self._editor)
        self._test_button.setObjectName("formBuilder.connections.test")
        self._test_button.clicked.connect(self._test)
        self._result = QLabel(self._editor)
        self._result.setObjectName("formBuilder.connections.result")
        self._result.setWordWrap(True)
        test_row.addWidget(self._test_button)
        test_row.addWidget(self._result, 1)
        body.addWidget(self._editor, 2)
        self._load()

    def showEvent(self, event: object) -> None:  # noqa: N802
        super().showEvent(event)  # type: ignore[arg-type]
        window = self.window()
        self.apply_theme(getattr(window, "_tokens", None) or tokens_from_palette(self.palette()))

    def hideEvent(self, event: object) -> None:  # noqa: N802
        self._drop_filter()
        super().hideEvent(event)  # type: ignore[arg-type]

    def _drop_filter(self) -> None:
        application = QApplication.instance()
        if application is not None and self._filtered:
            application.removeEventFilter(self)
            self._filtered = False

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        press = getattr(getattr(QEvent, "Type", QEvent), "KeyPress", None)
        if (
            self._testing
            and press is not None
            and event.type() == press  # type: ignore[attr-defined]
            and enum_value(event.key()) == enum_value(Qt.Key.Key_Escape)  # type: ignore[attr-defined]
        ):
            self._cancel_test()
            return True
        return super().eventFilter(watched, event)  # type: ignore[arg-type]

    def apply_theme(self, tokens: object) -> None:
        self._tokens = tokens
        sheet = _style(tokens)
        if isinstance(tokens, ShellThemeTokens):
            sheet += shell_section_checkbox_indicators(tokens)
        self.setStyleSheet(sheet)

    def commit(self, project_root: str) -> Optional[SettingsRefusal]:
        self._pull(commit_code=True)
        if self._pending:
            return SettingsRefusal(self._pending)
        if any(NAME_RE.match(item.name) is None for item in self._items):
            return SettingsRefusal(ILLEGAL_NAME_SENTENCE)
        value = ConnectionSet(tuple(self._items), self._top_unknown)
        text = write_connections(value)
        _parsed, diagnostic = read_connections(text, project_root=project_root)
        if diagnostic is not None:
            return SettingsRefusal(diagnostic.sentence)
        save_project_connections(project_root, value, slug=project_slug(project_root))
        self._refresh_project()
        return None

    def _load(self) -> None:
        loaded, diagnostic = load_connections(self._root)
        if diagnostic is not None or loaded is None:
            self._show_refusal(diagnostic.sentence if diagnostic is not None else "The connections file can't be read.")
            loaded = ConnectionSet()
        self._items = list(loaded.connections)
        self._touched = [True] * len(self._items)
        self._top_unknown = loaded.unknown
        self._index = 0 if self._items else -1
        machine = load_project_machine(self._root)
        if machine.shared:
            self._machine.setText(MACHINE_WARNING)
            self._machine.show()
        self._refresh_list()
        self._fill()

    def _refresh_list(self) -> None:
        self._loading = True
        try:
            self._list.clear()
            for connection in self._items:
                title = connection.title or connection.name
                # The row widget paints the title. Item text would draw it again.
                item = QListWidgetItem("")
                role = getattr(getattr(Qt, "ItemDataRole", Qt), "AccessibleTextRole", None)
                if role is not None:
                    item.setData(role, title)
                row = _Row(connection.title, engine_line(connection), self._list)
                row.setAccessibleName(title)
                item.setSizeHint(row.sizeHint())
                self._list.addItem(item)
                self._list.setItemWidget(item, row)
            if 0 <= self._index < self._list.count():
                self._list.setCurrentRow(self._index)
        finally:
            self._loading = False
        self._sync_mode()

    def _sync_mode(self) -> None:
        empty = not self._items
        self._empty.setVisible(empty)
        for button in self._empty_buttons:
            button.setVisible(empty)
        self._list.setVisible(not empty)
        self._add.setVisible(not empty)
        self._duplicate.setVisible(not empty)
        self._remove.setVisible(not empty)
        self._editor.setVisible(not empty)

    def _fill(self) -> None:
        if self._index < 0 or self._index >= len(self._items):
            self._sync_mode()
            return
        item = self._items[self._index]
        self._loading = True
        try:
            self._title.setText(item.title)
            self._code.setText(item.name)
            sqlite = item.engine == "sqlite"
            self._show_engine(sqlite)
            self._file.setText(item.file or "")
            self._host.setText(item.host or "")
            self._port.setValue(item.port or 5432)
            self._database.setText(item.database or "")
            self._user.setText(item.user or "")
            self._schema.setText(item.schema or "public")
            index = self._password.findData(item.password or "ask")
            self._password.setCurrentIndex(index if index >= 0 else 0)
            self._try_sql.setChecked(bool(item.try_show_sql_only))
            self._setup_name = item.setup
            self._show_setup(item.setup)
        finally:
            self._loading = False
        self._sync_mode()

    def _show_engine(self, sqlite: bool) -> None:
        self._row_visible(self._file_row, sqlite)
        for field in self._postgres_fields:
            self._row_visible(field, not sqlite)

    def _row_visible(self, field: object, visible: bool) -> None:
        label = self._form.labelForField(field)  # type: ignore[arg-type]
        if label is not None:
            label.setVisible(visible)
        if isinstance(field, QWidget):
            field.setVisible(visible)
        elif isinstance(field, QHBoxLayout):
            for index in range(field.count()):
                child = field.itemAt(index).widget()
                if child is not None:
                    child.setVisible(visible)
        setter = getattr(self._form, "setRowVisible", None)
        if setter is not None:
            setter(field, visible)

    def _pull(self, *, commit_code: bool) -> None:
        index = self._index
        if index < 0 or index >= len(self._items) or self._loading:
            return
        if commit_code:
            self._commit_code()
        item = self._items[index]
        title = self._title.text()
        show = self._try_sql.isChecked()
        setup = self._setup_name
        if item.engine == "sqlite":
            file_name = self._file.text().strip() or None
            self._items[index] = replace(
                item,
                title=title,
                file=file_name,
                setup=setup,
                try_show_sql_only=show,
            )
            return
        port = int(self._port.value())
        schema = self._schema.text().strip()
        self._items[index] = replace(
            item,
            title=title,
            host=self._host.text().strip() or None,
            port=None if port == 5432 else port,
            database=self._database.text().strip() or None,
            user=self._user.text().strip() or None,
            schema=None if schema in ("", "public") else schema,
            password=str(self._password.currentData() or "ask"),
            setup=setup,
            try_show_sql_only=show,
        )

    def _commit_code(self) -> None:
        index = self._index
        if index < 0 or index >= len(self._items):
            return
        new = self._code.text().strip()
        old = self._items[index].name
        if new == old:
            return
        if NAME_RE.match(new) is None:
            self._items[index] = replace(self._items[index], name=new)
            return
        paths = forms_using_connection(self._root, old) if self._root else ()
        if paths:
            dialog = build_rename_question(self, rename_sentence(len(paths), old))
            if self._tokens is not None:
                dialog.setStyleSheet(_dialog_style(self._tokens))
            accepted = enum_value(QDialog.DialogCode.Accepted)
            if enum_value(exec_qt(dialog)) != accepted:
                self._loading = True
                self._code.setText(old)
                self._loading = False
                return
            try:
                rewrite_forms(
                    self._root,
                    lambda doc, old_name=old, new_name=new: rename_connection(doc, old_name, new_name),
                    open_sessions=open_sessions(self._root),
                    undo_label=_UNDO,
                )
            except Exception as exc:
                self._loading = True
                self._code.setText(old)
                self._loading = False
                self._show_refusal(str(exc))
                return
        rename_project_entry(self._root, old, new)
        self._items[index] = replace(self._items[index], name=new)

    def _on_row(self, row: int) -> None:
        if self._loading or row < 0 or row == self._index:
            return
        previous = self._index
        self._pull(commit_code=True)
        self._update_row(previous)
        self._index = row
        self._fill()

    def _on_title(self, _text: str) -> None:
        if self._loading or self._index < 0:
            return
        if not self._touched[self._index]:
            self._loading = True
            self._code.setText(code_name_from_title(self._title.text()))
            self._loading = False
        self._pull(commit_code=False)
        self._update_row(self._index)

    def _on_code_edited(self, _text: str) -> None:
        if self._loading or self._index < 0:
            return
        self._touched[self._index] = True

    def _on_code_finished(self) -> None:
        if self._loading:
            return
        self._pull(commit_code=True)
        self._update_row(self._index)

    def _on_field(self, *_args: object) -> None:
        if self._loading:
            return
        self._pull(commit_code=False)
        self._update_row(self._index)

    def _update_row(self, index: int) -> None:
        if index < 0 or index >= self._list.count() or index >= len(self._items):
            return
        widget = self._list.itemWidget(self._list.item(index))
        if not isinstance(widget, _Row):
            return
        connection = self._items[index]
        widget.title_label.setText(connection.title)
        widget.engine_label.setText(engine_line(connection))

    def _add_connection(self, engine: str) -> None:
        if self._items:
            self._pull(commit_code=False)
        if engine == "sqlite":
            title = "SQLite"
            item = Connection(code_name_from_title(title), title, "sqlite")
        else:
            title = "PostgreSQL"
            item = Connection(code_name_from_title(title), title, "postgres", password="ask")
        taken = {existing.name for existing in self._items}
        name = item.name
        number = 2
        while name in taken:
            name = "%s_%d" % (item.name, number)
            number += 1
        if name != item.name:
            item = replace(item, name=name)
        self._items.append(item)
        self._touched.append(False)
        self._index = len(self._items) - 1
        self._refresh_list()
        self._fill()

    def _duplicate_current(self) -> None:
        self._pull(commit_code=False)
        if self._index < 0:
            return
        source = self._items[self._index]
        taken = {item.name for item in self._items}
        number = 2
        candidate = "%s_%d" % (source.name, number)
        while candidate in taken:
            number += 1
            candidate = "%s_%d" % (source.name, number)
        copy = replace(source, name=candidate, title="Copy of %s" % source.title)
        self._items.append(copy)
        self._touched.append(True)
        self._index = len(self._items) - 1
        self._refresh_list()
        self._fill()

    def _remove_current(self) -> None:
        self._pull(commit_code=False)
        if self._index < 0:
            return
        connection = self._items[self._index]
        paths = forms_using_connection(self._root, connection.name)
        if paths:
            stems = [os.path.splitext(os.path.basename(path))[0] for path in paths]
            sentence = remove_sentence(connection.name, stems)
            self._pending = sentence
            self._show_refusal(sentence)
            return
        del self._items[self._index]
        del self._touched[self._index]
        self._index = min(self._index, len(self._items) - 1)
        self._refresh_list()
        self._fill()

    def _choose_file(self) -> None:
        start = self._root or ""
        chosen = QFileDialog.getSaveFileName(
            self,
            "Choose a SQLite file",
            start,
            "SQLite (*.db *.sqlite *.sqlite3);;All files (*)",
        )
        selected = chosen[0] if isinstance(chosen, tuple) else chosen
        if not selected:
            return
        if not self._root or not inside_project(selected, self._root):
            self._show_refusal(OUTSIDE_PROJECT_SENTENCE)
            return
        try:
            relative = relative_posix(selected, self._root)
        except ProjectOpError:
            self._show_refusal(OUTSIDE_PROJECT_SENTENCE)
            return
        self._refusal.hide()
        self._file.setText(relative)
        self._pull(commit_code=False)
        self._update_row(self._index)

    def _create_setup(self) -> None:
        ensure_connection_setup(self._root)
        self._setup_name = "on_connect"
        if 0 <= self._index < len(self._items):
            self._items[self._index] = replace(self._items[self._index], setup="on_connect")
        self._show_setup("on_connect")
        self._refresh_project()

    def _refresh_project(self) -> None:
        owners = []
        widget: object = self
        while widget is not None:
            owners.append(widget)
            parent = getattr(widget, "parent", None)
            widget = parent() if callable(parent) else None
        top = self.window()
        if top is not None:
            owners.append(top)
        for owner in owners:
            tree = getattr(owner, "_project_tree_ui_workflow", None)
            refresh = getattr(tree, "refresh_project_tree_from_disk", None)
            if callable(refresh):
                refresh()
                return

    def _show_setup(self, setup: Optional[str]) -> None:
        if setup:
            self._setup.setText(setup)
            self._create_setup_button.hide()
            return
        self._setup.setText("none")
        self._create_setup_button.show()

    def _test(self) -> None:
        self._pull(commit_code=False)
        if self._index < 0:
            return
        connection = self._items[self._index]
        if connection.engine == "postgres" and connection_tester() is None:
            self._result.setText(POSTGRES_PLACEHOLDER)
            self._test_button.setText("Test")
            self._test_button.setEnabled(True)
            return
        if connection.engine == "postgres":
            install_secret_marshal()
        self._start(lambda connection=connection: self._run_test(connection))

    def _run_test(self, connection: Connection) -> dict:
        if connection.engine == "sqlite":
            return {"text": probe_sqlite(self._sqlite_path(connection))}
        tester = connection_tester()
        if tester is None:
            return {"text": POSTGRES_PLACEHOLDER}
        install_schema_reader(self._root)
        try:
            result = tester(connection, lambda: ask_connection_secret(self._root, connection))
        except Exception as exc:
            lines = str(exc).splitlines()
            return {"text": lines[0] if lines else "Can't connect."}
        return {"text": _format_probe(result)}

    def _sqlite_path(self, connection: Connection) -> str:
        relative = connection.file or ""
        if not relative or not self._root:
            return relative
        return os.path.abspath(os.path.join(self._root, *relative.split("/")))

    def _start(self, fn: Any) -> None:
        self._generation += 1
        generation = self._generation
        self._testing = True
        # Esc must reach us before the dialog does. Watch the application only while a test runs.
        application = QApplication.instance()
        if application is not None and not self._filtered:
            application.installEventFilter(self)
            self._filtered = True
        self._test_button.setText("Testing\u2026")
        self._test_button.setEnabled(False)
        self._result.setText("Testing\u2026")
        worker = _Worker(fn, self)
        worker._ready = False
        self._workers[generation] = worker
        worker.start()
        QTimer.singleShot(0, self._poll_tests)

    def _poll_tests(self) -> None:
        pending = False
        for generation, worker in list(self._workers.items()):
            if not getattr(worker, "_ready", False):
                pending = True
                continue
            worker.wait(3000)
            self._workers.pop(generation, None)
            worker.deleteLater()
            if generation != self._generation:
                continue
            self._show_test_result(worker.payload)
        if pending:
            QTimer.singleShot(20, self._poll_tests)

    def _show_test_result(self, payload: object) -> None:
        self._testing = False
        self._drop_filter()
        self._test_button.setText("Test")
        self._test_button.setEnabled(True)
        text = ""
        if isinstance(payload, dict):
            text = str(payload.get("text") or "")
        self._result.setText(text)

    def _cancel_test(self) -> None:
        if not self._testing:
            return
        cancel_schema_work()
        self._generation += 1
        self._testing = False
        self._drop_filter()
        self._test_button.setText("Test")
        self._test_button.setEnabled(True)
        self._result.setText("")

    def _show_refusal(self, sentence: str) -> None:
        self._refusal.setText(sentence)
        self._refusal.show()


def _format_probe(result: object) -> str:
    if not isinstance(result, dict):
        return str(result)
    if result.get("ok"):
        return "\u2713 Connected · %s · %s tables · %s" % (
            result.get("server", ""),
            result.get("tables", 0),
            result.get("driver", ""),
        )
    message = result.get("message") or ""
    if isinstance(message, str) and message:
        return message.splitlines()[0]
    return str(result.get("kind") or "")


def _style(tokens: object) -> str:
    width = int(getattr(tokens, "focus_border_width", 1) or 1)
    return (
        "QWidget#formBuilder\\.connections\\.page { background: %s; color: %s; }"
        "QLabel { color: %s; background: transparent; }"
        "QLabel#formBuilder\\.connections\\.engine, QLineEdit#formBuilder\\.connections\\.code { color: %s; }"
        "QLabel#formBuilder\\.connections\\.refusal, QLabel#formBuilder\\.connections\\.machineWarning { color: %s; }"
        "QLineEdit, QComboBox, QSpinBox, QListWidget { color: %s; background: %s; border: 1px solid %s; padding: 2px 4px; }"
        "QPushButton { color: %s; background: %s; border: 1px solid %s; padding: 4px 8px; }"
        "QCheckBox { color: %s; background: transparent; spacing: 6px; }"
        "QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QListWidget:focus, QPushButton:focus, QCheckBox:focus {"
        " border: %dpx solid %s; }"
        % (
            tokens.panel_bg,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.text_muted,  # type: ignore[attr-defined]
            tokens.diag_warning_color,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.input_bg,  # type: ignore[attr-defined]
            tokens.border,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.input_bg,  # type: ignore[attr-defined]
            tokens.border,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            width,
            tokens.accent,  # type: ignore[attr-defined]
        )
    )


def _dialog_style(tokens: object) -> str:
    width = int(getattr(tokens, "focus_border_width", 1) or 1)
    return (
        "QDialog { background: %s; color: %s; }"
        "QLabel { color: %s; }"
        "QPushButton { color: %s; background: %s; border: 1px solid %s; padding: 4px 10px; }"
        "QPushButton:focus { border: %dpx solid %s; }"
        % (
            tokens.panel_bg,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.text_primary,  # type: ignore[attr-defined]
            tokens.input_bg,  # type: ignore[attr-defined]
            tokens.border,  # type: ignore[attr-defined]
            width,
            tokens.accent,  # type: ignore[attr-defined]
        )
    )


def _no_project(parent: QWidget) -> QWidget:
    page = QWidget(parent)
    page.setObjectName("formBuilder.connections.page")
    layout = QVBoxLayout(page)
    label = QLabel("Open a project to manage its connections.", page)
    label.setWordWrap(True)
    layout.addWidget(label)
    layout.addStretch(1)
    return page


def build(parent: QWidget, payload: object, project_root: str) -> QWidget:
    del payload
    if not project_root:
        return _no_project(parent)
    return ConnectionsPage(parent, project_root)


def apply(widget: QWidget, project_root: str) -> Optional[SettingsRefusal]:
    if isinstance(widget, ConnectionsPage):
        return widget.commit(project_root)
    return None


def install() -> None:
    register_settings_page(
        SettingsPage(
            key="connections",
            title="Connections",
            build=build,
            apply=apply,
            scope=SCOPE_PROJECT,
        )
    )
