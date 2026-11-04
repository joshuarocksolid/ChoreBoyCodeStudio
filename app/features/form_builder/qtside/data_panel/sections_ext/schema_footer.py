"""Column-cache footer. Refresh reads SQLite here and PostgreSQL in the helper."""

from __future__ import annotations

import datetime
import weakref
from typing import Any, Dict, Optional

from app.features.form_builder.engine.data.connections import Connection, load_connections
from app.features.form_builder.engine.data.schema import is_stale, schema_for
from app.features.form_builder.engine.data.schema_cache import (
    cancel_schema_work,
    footer_text,
    install_schema_reader,
    refresh,
)
from app.features.form_builder.engine.data.source import has_data_source, read_data
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection
from app.features.form_builder.qtside.schema_prompt import ask_connection_secret, install_secret_marshal
from app.qt.QtCore import QEvent, QThread, QTimer, Qt
from app.qt.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from app.qt.qt_compat import enum_value

FORCE_FOOTER: "weakref.WeakSet[Any]" = weakref.WeakSet()


class _Worker(QThread):
    def __init__(self, fn: Any, parent: QWidget) -> None:
        super().__init__(parent)
        self._fn = fn
        self.payload: object = None

    def run(self) -> None:  # noqa: D102
        try:
            self.payload = self._fn()
        except Exception as exc:
            self.payload = exc


class _Footer(QWidget):
    def __init__(self, host: Any) -> None:
        super().__init__(host)
        self.setObjectName("formBuilder.data.schemaFooter")
        self._host = host
        self._generation = 0
        self._busy = False
        self._filtered = False
        self._worker: Optional[_Worker] = None
        self._worker_generation = 0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self._sentence = QLabel(self)
        self._sentence.setObjectName("formBuilder.data.schemaSentence")
        self._sentence.setWordWrap(True)
        self._sentence.setMinimumWidth(0)
        layout.addWidget(self._sentence)
        row = QHBoxLayout()
        layout.addLayout(row)
        self._row = row
        self._stale = QLabel("(may be out of date)", self)
        self._stale.setObjectName("formBuilder.data.stale")
        self._stale.setWordWrap(True)
        row.addWidget(self._stale, 0)
        row.addStretch(1)
        self._refresh = QPushButton("Refresh", self)
        self._refresh.setObjectName("formBuilder.data.schemaRefresh")
        self._refresh.clicked.connect(self._on_refresh)
        row.addWidget(self._refresh, 0)
        root = _project_root(host)
        if root:
            install_schema_reader(root)
        self._show_idle()

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802
        press = getattr(getattr(QEvent, "Type", QEvent), "KeyPress", None)
        if (
            self._busy
            and press is not None
            and event.type() == press  # type: ignore[attr-defined]
            and enum_value(event.key()) == enum_value(Qt.Key.Key_Escape)  # type: ignore[attr-defined]
        ):
            self._cancel()
            return True
        return super().eventFilter(watched, event)  # type: ignore[arg-type]

    def _on_refresh(self) -> None:
        root = _project_root(self._host)
        if root:
            install_schema_reader(root)
        connection = self._connection(root)
        self._generation += 1
        generation = self._generation
        self._busy = True
        self._set_sentence(footer_text(None, busy=True), wrap=False)
        self._stale.hide()
        self._install_filter()
        install_secret_marshal()
        document = _document(self._host)
        source = _source(document)
        sql = str(getattr(source, "sql", "") or "")
        asked: Dict[str, str] = {}

        def ask(item: Connection) -> str:
            if "secret" in asked:
                return str(asked["secret"])
            secret = ask_connection_secret(root, item)
            asked["secret"] = secret
            return secret

        def run() -> object:
            if connection is None or not root:
                return None
            outcome = refresh(root, connection, ask)
            _remember_list_sql(root, connection, document, sql, ask)
            return outcome

        worker = _Worker(run, self)
        self._worker = worker
        self._worker_generation = generation
        worker.start()
        QTimer.singleShot(20, self._poll)

    def _poll(self) -> None:
        worker = self._worker
        if worker is None:
            return
        if not worker.isFinished():
            QTimer.singleShot(20, self._poll)
            return
        payload = worker.payload
        generation = self._worker_generation
        worker.wait()
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
        if generation != self._generation:
            return
        self._busy = False
        self._drop_filter()
        self._apply(payload)

    def _apply(self, payload: object) -> None:
        connection = self._connection(_project_root(self._host))
        if payload is None or isinstance(payload, Exception):
            self._show_failure(connection, "Can't connect.")
            return
        cancelled = bool(getattr(payload, "cancelled", False))
        if cancelled or getattr(payload, "kind", "") == "cancelled":
            self._show_idle()
            return
        if not getattr(payload, "ok", False):
            self._show_failure(
                connection,
                str(getattr(payload, "reason", "") or ""),
                getattr(payload, "schema", None),
            )
            return
        self._show_idle()
        signal = getattr(self._host, "schema_changed", None)
        emit = getattr(signal, "emit", None)
        if callable(emit) and connection is not None:
            emit(connection.name)

    def _cancel(self) -> None:
        if not self._busy:
            return
        self._generation += 1
        cancel_schema_work()
        self._busy = False
        self._drop_filter()
        self._show_idle()

    def _show_idle(self) -> None:
        schema = self._cached()
        self._set_sentence(footer_text(schema), wrap=False)
        stale = schema is not None and bool(schema.read_at) and is_stale(schema, datetime.datetime.now())
        self._stale.setVisible(stale)

    def _show_failure(self, connection: Optional[Connection], reason: str, schema: object = None) -> None:
        if schema is None:
            schema = self._cached()
        title = connection.title if connection is not None else ""
        self._set_sentence(footer_text(schema, failed=True, title=title, reason=reason), wrap=True)
        self._stale.hide()

    def _set_sentence(self, text: str, wrap: bool) -> None:
        # The sentence always wraps to the footer's width. Refresh sits on the
        # line below, so a 184 px Data tab still shows the whole read time.
        del wrap
        self._sentence.setText(text)

    def _cached(self) -> object:
        doc = _document(self._host)
        source = _source(doc)
        if doc is None or source is None:
            return None
        return schema_for(doc, source.connection)

    def _connection(self, root: str) -> Optional[Connection]:
        source = _source(_document(self._host))
        if source is None or not root:
            return None
        loaded, _diagnostic = load_connections(root)
        if loaded is None:
            return None
        name = source.connection
        for item in loaded.connections:
            if item.name == name:
                return item
        return None

    def _install_filter(self) -> None:
        application = QApplication.instance()
        if application is not None and not self._filtered:
            application.installEventFilter(self)
            self._filtered = True

    def _drop_filter(self) -> None:
        application = QApplication.instance()
        if application is not None and self._filtered:
            application.removeEventFilter(self)
            self._filtered = False


def _remember_list_sql(root: str, connection: Connection, document: object, sql: str, ask: Any) -> None:
    """Probe after the schema read. The result is what publish shows later."""

    if document is None or not sql.strip():
        return
    from app.features.form_builder.engine.data.checks.listing import remember_list_probe
    from app.features.form_builder.engine.data.schema_cache import probe_select

    remember_list_probe(document, sql, probe_select(root, connection, sql, ask))


def _create(host: Any) -> QWidget:
    return _Footer(host)


def _applies(doc: Any) -> bool:
    try:
        forced = doc in FORCE_FOOTER
    except TypeError:
        forced = False
    return forced or has_data_source(doc)


def _document(host: Any) -> object:
    for owner in (host, getattr(host, "_workbench", None)):
        if owner is None:
            continue
        document = getattr(getattr(owner, "session", None), "document", None)
        if document is not None:
            return document
    return None


def _project_root(host: Any) -> str:
    for owner in (host, getattr(host, "_workbench", None)):
        if owner is None:
            continue
        found = getattr(owner, "project_root", None)
        if isinstance(found, str) and found:
            return found
        window = getattr(owner, "window", None)
        if not callable(window):
            continue
        try:
            loaded = getattr(window(), "_loaded_project", None)
        except Exception:
            loaded = None
        path = getattr(loaded, "project_root", None)
        if path:
            return str(path)
    return ""


def _source(doc: object) -> Optional[object]:
    root = getattr(doc, "root", None)
    prop = getattr(root, "prop", None)
    if not callable(prop):
        return None
    entry = prop("cbcsData")
    if entry is None:
        return None
    value = getattr(entry, "value", None)
    text = getattr(value, "text", None)
    if not isinstance(text, str) or not text.strip():
        return None
    return read_data(text).value


def register(registry: Any) -> None:
    registry.add(PanelSection("schema_footer", 900, _create, _applies))
