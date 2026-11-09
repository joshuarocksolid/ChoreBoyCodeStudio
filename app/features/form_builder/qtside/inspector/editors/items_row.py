"""Content row that opens the item editor (UX-ITEM-001)."""

from __future__ import annotations

from typing import Optional, Tuple

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import NumberValue
from app.features.form_builder.qtside.inspector.api import (
    Choice,
    EditorHost,
    EditorKey,
    GroupId,
    Prop,
    Registrar,
    RowSpec,
    RowValue,
    Summary,
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
            source=Summary(),
            classes=_CLASSES,
            editor="items",
            after="toolTip",
        )
    )
    # UX-ITEM-003: the combo's "Starts on" is an inspector row over its item texts.
    registrar.row(
        RowSpec(
            key="comboStartsOn",
            group=GroupId.CONTENT,
            label="Starts on",
            help="The item shown when the form opens.",
            source=Prop("currentIndex"),
            classes=("QComboBox",),
            after="items",
            choices=_combo_start_choices,
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
        open_editor(session, owners[0], self._button.window(), under=anchor, chrome=self._host.chrome)


def _combo_start_choices(document: UiDocument, owners: Tuple[NodeId, ...]) -> Tuple[Choice, ...]:
    if len(owners) != 1:
        return ()
    draft = load_draft(document, owners[0])
    if draft is None:
        return ()
    return tuple(
        Choice(item.text_at(0) or "Item %d" % (index + 1), NumberValue(index))
        for index, item in enumerate(draft.items)
    )


def _session_of(host: object) -> object:
    session = getattr(host, "session", None)
    if session is not None:
        return session
    services = getattr(host, "_services", None)
    return getattr(services, "session", None)
