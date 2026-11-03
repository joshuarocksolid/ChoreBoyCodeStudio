"""UX-DATA-003. ``{table} in {connection}`` with Change and the more menu."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from app.features.form_builder.qtside.data_panel.host import session_of
from app.features.form_builder.qtside.data_panel.model import connection_title, record_source
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.sourceLine")
    layout = QHBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    sentence = QLabel(body)
    sentence.setObjectName("formBuilder.data.sourceText")
    sentence.setWordWrap(True)
    layout.addWidget(sentence, 1)
    change = QPushButton("Change\u2026", body)
    change.setObjectName("formBuilder.data.change")
    change.clicked.connect(lambda: _change(host))
    layout.addWidget(change)
    more = QPushButton("\u22ef", body)
    more.setObjectName("formBuilder.data.more")
    more.setStyleSheet("QPushButton::menu-indicator { image: none; width: 0px; }")
    menu = QMenu(more)
    menu.addAction("Show SQL", lambda: _menu(host, "sql"))
    menu.addAction("Python hooks\u2026", lambda: _menu(host, "hooks"))
    menu.addAction("Eject to code\u2026", lambda: _menu(host, "eject"))
    menu.addAction("Disconnect\u2026", lambda: _menu(host, "disconnect"))
    more.setMenu(menu)
    layout.addWidget(more)

    def refresh() -> None:
        session = session_of(host)
        source = record_source(session.document) if session is not None else None
        if source is None:
            sentence.setText("")
            return
        title = connection_title(session, source.connection, host)
        sentence.setText("%s in %s" % (source.table, title))

    body.refresh = refresh  # type: ignore[attr-defined]
    refresh()
    return body


def _change(host: Any) -> None:
    from app.features.form_builder.qtside.data_panel.sheets import open_connect_sheet

    open_connect_sheet(host)


def _menu(host: Any, which: str) -> None:
    from app.features.form_builder.engine.commands.base import CommandRejected
    from app.features.form_builder.qtside.data_panel.edits import disconnect_form
    from app.features.form_builder.qtside.data_panel.host import narrate, session_of as owner_session
    from app.features.form_builder.qtside.data_panel.sheets import open_hooks_sheet, open_sql_sheet

    if which == "sql":
        open_sql_sheet(host)
        return
    if which == "hooks":
        open_hooks_sheet(host)
        return
    if which == "eject":
        from app.features.form_builder.qtside.data_panel.eject_dialog import open_eject_dialog

        open_eject_dialog(host)
        return
    session = owner_session(host)
    if session is None:
        return
    try:
        disconnect_form(session)
    except CommandRejected as exc:
        narrate(host, str(exc))


def _applies(doc: Any) -> bool:
    return record_source(doc) is not None


def register(registry: Any) -> None:
    registry.add(PanelSection("source", 20, _create, _applies))
