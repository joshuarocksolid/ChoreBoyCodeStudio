
from __future__ import annotations

from typing import Dict, List, Literal, Optional, Tuple

from app.features.form_builder.engine.commands.base import CommandOutcome
from app.features.form_builder.engine.commands.catalog import AddConnection, DeleteNodes, EditConnection
from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.nodes import ConnectionNode, WidgetNode
from app.features.form_builder.qtside.inspector._live import live_classes
from app.features.form_builder.qtside.inspector._services import Services
from app.features.form_builder.qtside.inspector.model import BehaviorView, ConnectionView, ManyBehavior, OneBehavior
from app.features.form_builder.qtside.realize import Realizer
from app.qt.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

class BehaviorPage(QWidget):

    def __init__(self, services: Services, realizer: Realizer, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.behaviorBody")
        self._services = services
        self._realizer = realizer
        self._rows: Dict[NodeId, _ConnectionRow] = {}
        self._pending_open: Optional[NodeId] = None
        self._add_signal = ""
        self._view: Optional[OneBehavior] = None
        self._draft: Optional[_Draft] = None
        self._draft_row: Optional[_DraftRow] = None
        self._message = QLabel(self)
        self._message.setWordWrap(True)
        self._add = QPushButton("+ Add connection", self)
        self._add.clicked.connect(self._add_clicked)
        self._list = QWidget(self)
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        layout.addWidget(self._message)
        layout.addWidget(self._list)
        layout.addWidget(self._add, 0)
        layout.addStretch(1)

    def apply_colors(self, panel: str, text: str) -> None:
        self.setStyleSheet(
            "QWidget#formBuilder\\.behaviorBody { background: %s; color: %s; }"
            "QLabel { color: %s; background: transparent; }"
            % (panel, text, text)
        )

    def paint(self, view: BehaviorView) -> None:
        if isinstance(view, ManyBehavior):
            self._clear_draft()
            self._view = None
            self._message.setText("Select one widget to see its connections.")
            self._message.show()
            self._list.hide()
            self._add.hide()
            return
        self._view = view
        self._add.show()
        signal = view.add_signal or self._first_signal(view.sender)
        self._add_signal = signal or ""
        self._add.setEnabled(bool(self._add_signal))
        if view.connections or self._draft is not None:
            self._message.hide()
            self._list.show()
        else:
            self._message.setText(view.empty)
            self._message.show()
            self._list.show()
        self._reconcile(view)
        if self._draft_row is not None:
            self._message.hide()
            self._list.show()
            self._list_layout.insertWidget(0, self._draft_row)
            self._draft_row.show()
        pending = self._pending_open
        self._pending_open = None
        if pending is not None:
            row = self._rows.get(pending)
            if row is not None:
                row.open_signal()

    def has_draft(self) -> bool:
        return self._draft is not None

    def discard_draft(self) -> bool:
        if self._draft is None and self._draft_row is None:
            return False
        view = self._view
        self._clear_draft()
        if view is not None and not view.connections:
            self._message.setText(view.empty)
            self._message.show()
        return True

    def note_focus(self, focus: object) -> None:
        if self._draft is None or focus is None:
            return
        widget = focus
        while isinstance(widget, QWidget):
            if widget is self:
                return
            parent = widget.parentWidget()
            widget = parent
        self.discard_draft()

    def _add_clicked(self) -> None:
        view = self._view
        if view is None or not self._add_signal:
            return
        if self._draft_row is not None:
            self._draft_row.open_signal()
            return
        receiver = self._services.session.document.root.object_name
        self._draft = _Draft(self._add_signal, receiver)
        row = _DraftRow(self, self._list)
        self._draft_row = row
        self._list_layout.insertWidget(0, row)
        self._list.show()
        self._message.hide()
        row.show()
        row.fill(
            self._choices(view.sender, "signals"),
            self._receiver_names(),
            self._slots_for(receiver),
            self._add_signal,
            receiver,
        )
        row.open_signal()

    def _draft_signal(self, text: str) -> None:
        draft = self._draft
        if draft is None or not text:
            return
        draft.signal = text

    def _draft_receiver(self, text: str) -> None:
        draft = self._draft
        row = self._draft_row
        if draft is None or row is None or not text:
            return
        draft.receiver = text
        row.set_slots(self._slots_for(text))

    def _commit_draft(self, slot: str) -> None:
        view = self._view
        draft = self._draft
        chosen = slot.strip()
        if view is None or draft is None or not chosen:
            return
        document = self._services.session.document
        connections = document.connections()
        index = len(connections)
        for position, connection in enumerate(connections):
            if isinstance(connection, ConnectionNode) and connection.sender == view.sender_name:
                index = position
                break
        signal = draft.signal or self._add_signal
        receiver = draft.receiver or document.root.object_name
        self._clear_draft()
        sender = view.sender
        result = self._services.execute(AddConnection(view.sender_name, signal, receiver, chosen, index))
        if not isinstance(result, CommandOutcome):
            return
        # AddConnection selects the new connection, which would swap the
        # inspector to it. Keep the sender and open the new row (UX-INSP-013).
        # Undo still restores the sender, the selection before the command.
        added = result.result
        if isinstance(added, int):
            self._pending_open = NodeId(added)
        self._services.session.selection.set((sender,), source=SelectionSource.INSPECTOR)

    def _clear_draft(self) -> None:
        self._draft = None
        row = self._draft_row
        self._draft_row = None
        if row is None:
            return
        self._list_layout.removeWidget(row)
        row.hide()
        row.setParent(None)
        row.deleteLater()

    def _slots_for(self, name: str) -> Tuple[str, ...]:
        document = self._services.session.document
        found = document.by_name(name)
        if not found:
            return ()
        node = document.node(found[0])
        if not isinstance(node, WidgetNode):
            return ()
        return self._choices(node.id, "slots")

    def _on_picked(
        self, connection: NodeId, field: Literal["signal", "receiver", "slot"], text: str
    ) -> None:
        if field == "signal":
            command = EditConnection(connection, signal=text)
        elif field == "receiver":
            command = EditConnection(connection, receiver=text)
        else:
            command = EditConnection(connection, slot=text)
        self._services.execute(command)

    def _on_delete(self, connection: NodeId) -> None:
        self._services.execute(DeleteNodes((connection,)))

    def _choices(self, node: NodeId, kind: Literal["signals", "slots"]) -> Tuple[str, ...]:
        document = self._services.session.document
        found = live_classes(self._realizer, document, (node,))
        live = found.get(node)
        if live is None:
            return ()
        return live.signals if kind == "signals" else live.slots

    def _first_signal(self, node: NodeId) -> str:
        choices = self._choices(node, "signals")
        return choices[0] if choices else ""

    def _reconcile(self, view: OneBehavior) -> None:
        wanted = {connection.id: connection for connection in view.connections}
        for node_id in [key for key in self._rows if key not in wanted]:
            row = self._rows.pop(node_id)
            self._list_layout.removeWidget(row)
            row.hide()
            row.deleteLater()
        for connection in view.connections:
            row = self._rows.get(connection.id)
            if row is None:
                row = _ConnectionRow(self, connection.id, self._list)
                self._rows[connection.id] = row
            row.show()
            row.paint(connection, self._signal_choices(view, connection), self._receiver_names(), self._slot_choices(connection))
            self._list_layout.addWidget(row)

    def _signal_choices(self, view: OneBehavior, connection: ConnectionView) -> Tuple[str, ...]:
        return _with_current(self._choices(view.sender, "signals"), connection.signal)

    def _slot_choices(self, connection: ConnectionView) -> Tuple[str, ...]:
        document = self._services.session.document
        found = document.by_name(connection.receiver)
        slots: Tuple[str, ...] = ()
        if found:
            node = document.node(found[0])
            if isinstance(node, WidgetNode):
                slots = self._choices(node.id, "slots")
        return _with_current(slots, connection.slot)

    def _receiver_names(self) -> Tuple[str, ...]:
        document = self._services.session.document
        names = [widget.object_name for widget in document.iter_widgets() if widget.object_name]
        return tuple(names)

class _ConnectionRow(QWidget):
    def __init__(self, page: BehaviorPage, node_id: NodeId, parent: QWidget) -> None:
        super().__init__(parent)
        self._page = page
        self._id = node_id
        self._words = QLabel(self)
        self._words.setWordWrap(True)
        self._signal = QComboBox(self)
        self._receiver = QComboBox(self)
        self._slot = QComboBox(self)
        self._signal.activated.connect(lambda _index: self._picked("signal", self._signal))
        self._receiver.activated.connect(lambda _index: self._picked("receiver", self._receiver))
        self._slot.activated.connect(lambda _index: self._picked("slot", self._slot))
        self._delete = QToolButton(self)
        self._delete.setText("Remove")
        self._delete.clicked.connect(lambda: page._on_delete(self._id))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._words)
        row = QHBoxLayout()
        row.addWidget(self._signal, 1)
        row.addWidget(self._receiver, 1)
        row.addWidget(self._slot, 1)
        row.addWidget(self._delete, 0)
        layout.addLayout(row)

    def paint(
        self,
        view: ConnectionView,
        signals: Tuple[str, ...],
        receivers: Tuple[str, ...],
        slots: Tuple[str, ...],
    ) -> None:
        self._words.setText(view.words)
        _fill(self._signal, signals, view.signal)
        _fill(self._receiver, receivers, view.receiver)
        _fill(self._slot, slots, view.slot)

    def open_signal(self) -> None:
        self._signal.setFocus()
        self._signal.showPopup()

    def _picked(self, field: Literal["signal", "receiver", "slot"], box: QComboBox) -> None:
        text = box.currentText()
        if text:
            self._page._on_picked(self._id, field, text)

def _fill(box: QComboBox, choices: Tuple[str, ...], current: str) -> None:
    items = _with_current(choices, current)
    box.blockSignals(True)
    box.clear()
    box.addItems(list(items))
    index = box.findText(current)
    if index >= 0:
        box.setCurrentIndex(index)
    box.blockSignals(False)

def _with_current(choices: Tuple[str, ...], current: str) -> Tuple[str, ...]:
    found: List[str] = list(choices)
    if current and current not in found:
        found.insert(0, current)
    return tuple(found)


class _Draft:
    def __init__(self, signal: str, receiver: str) -> None:
        self.signal = signal
        self.receiver = receiver


class _DraftRow(QWidget):

    def __init__(self, page: BehaviorPage, parent: QWidget) -> None:
        super().__init__(parent)
        self._page = page
        self.setObjectName("formBuilder.connectionDraft")
        self._signal = QComboBox(self)
        self._receiver = QComboBox(self)
        self._slot = QComboBox(self)
        self._signal.setObjectName("formBuilder.draftSignal")
        self._receiver.setObjectName("formBuilder.draftReceiver")
        self._slot.setObjectName("formBuilder.draftSlot")
        self._signal.activated.connect(lambda _index: page._draft_signal(self._signal.currentText()))
        self._receiver.activated.connect(lambda _index: page._draft_receiver(self._receiver.currentText()))
        self._slot.activated.connect(lambda _index: page._commit_draft(self._slot.currentText()))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        words = QLabel("New connection", self)
        layout.addWidget(words)
        row = QHBoxLayout()
        row.addWidget(self._signal, 1)
        row.addWidget(self._receiver, 1)
        row.addWidget(self._slot, 1)
        layout.addLayout(row)

    def fill(
        self,
        signals: Tuple[str, ...],
        receivers: Tuple[str, ...],
        slots: Tuple[str, ...],
        signal: str,
        receiver: str,
    ) -> None:
        _fill(self._signal, signals, signal)
        _fill(self._receiver, receivers, receiver)
        self.set_slots(slots)

    def set_slots(self, slots: Tuple[str, ...]) -> None:
        box = self._slot
        box.blockSignals(True)
        box.clear()
        box.addItems(list(slots))
        box.setCurrentIndex(-1)
        box.setPlaceholderText("Choose a slot")
        box.blockSignals(False)

    def open_signal(self) -> None:
        self._signal.setFocus()
        self._signal.showPopup()
