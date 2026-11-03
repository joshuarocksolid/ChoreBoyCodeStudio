"""UX-DATA-002 on the form root. ``selected_class`` reports ``@form`` for that widget."""

from __future__ import annotations

from typing import Optional

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.qtside.data_panel.edits import connect_form
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.model import list_source, record_source
from app.features.form_builder.qtside.data_panel.sheets import SourceForm
from app.features.form_builder.qtside.inspector.data_ext import DataSection
from app.qt.QtWidgets import QPushButton, QVBoxLayout, QWidget


class _FormSource(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorData.formSource")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self._form: Optional[SourceForm] = None
        self._update = QPushButton("Connect", self)
        self._update.setObjectName("formBuilder.inspectorData.updateSource")
        self._update.clicked.connect(self._commit)
        layout.addWidget(self._update)

    def refresh(self) -> None:
        session = session_of(self)
        if session is None:
            return
        if list_source(session.document) is not None:
            self.hide()
            return
        self.show()
        if self._form is None:
            self._form = SourceForm(self, session)
            self.layout().insertWidget(0, self._form)  # type: ignore[union-attr]
        else:
            self._form.set_session(session)
        source = record_source(session.document)
        self._form.load(source)
        self._update.setText("Update" if source is not None else "Connect")

    def _commit(self) -> None:
        session = session_of(self)
        if session is None or self._form is None:
            return
        source = self._form.source()
        if source is None:
            narrate(self, "Choose a table with one key column.")
            return
        try:
            connect_form(session, source)
        except CommandRejected as exc:
            narrate(self, str(exc))
            return
        self.refresh()


def _create(parent: QWidget) -> QWidget:
    return _FormSource(parent)


def _applies(class_name: str) -> bool:
    return class_name == "@form"


def register(registry: object) -> None:
    getattr(registry, "add")(DataSection("form-source", 15, _create, _applies))
