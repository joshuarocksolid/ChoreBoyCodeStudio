"""Content row that opens the item editor (UX-ITEM-001)."""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.inspector.api import (
    EditorHost,
    EditorKey,
    GroupId,
    Prop,
    Registrar,
    RowSpec,
    RowValue,
)
from app.features.form_builder.qtside.inspector.editors._popover import SummaryButton
from app.features.form_builder.qtside.items.editor import open_editor
from app.features.form_builder.qtside.items.model import load_draft, summary
from app.qt.QtCore import QRect
from app.qt.QtWidgets import QWidget

_CLASSES = ("QComboBox", "QListWidget", "QTreeWidget", "QTableWidget")


def register(registrar: Registrar) -> None:
    registrar.editor(EditorKey("items"), ItemsEditor)
    registrar.row(
        RowSpec(
            key="items",
            group=GroupId.CONTENT,
            label="Items",
            help="The rows this widget shows.",
            source=Prop("statusTip"),
            classes=_CLASSES,
            editor="items",
            after="toolTip",
        )
    )


class ItemsEditor:
    def __init__(self, spec: object, host: EditorHost, parent: QWidget) -> None:
        del spec
        self._host = host
        self._button = SummaryButton("Items", parent)
        self._button.setObjectName("formBuilder.itemsRow")
        self._button.clicked.connect(self._open)

    @property
    def widget(self) -> QWidget:
        return self._button

    def show(self, value: RowValue) -> None:
        del value
        owners = self._host.owner_ids()
        if len(owners) != 1:
            self._button.set_summary("No items")
            return
        draft = load_draft(self._host.document(), owners[0])
        self._button.set_summary("No items" if draft is None else summary(draft))

    def _open(self) -> None:
        owners = self._host.owner_ids()
        if len(owners) != 1:
            return
        session = _session_of(self._host)
        if session is None:
            return
        rect = self._button.rect()
        origin = self._button.mapToGlobal(rect.topLeft())
        anchor = QRect(origin, rect.size())
        open_editor(session, owners[0], self._button.window(), under=anchor)


def _session_of(host: object) -> object:
    session = getattr(host, "session", None)
    if session is not None:
        return session
    services = getattr(host, "_services", None)
    return getattr(services, "session", None)
