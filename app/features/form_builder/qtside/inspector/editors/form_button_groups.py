"""The form's Button groups group (UX-MAIN-019): name, member count and "Only one can be on".

Selecting a row selects its buttons; Delete ungroups them; F2 renames the group.
Shown while the form is selected and the form has at least one button group.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.features.form_builder.engine.commands.catalog import Rename, SetProperty
from app.features.form_builder.engine.commands.catalog_ext.actions import UngroupButtons
from app.features.form_builder.engine.query import actions as q
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.document import UiDocument
from app.features.form_builder.engine.ui4.values import BoolValue
from app.features.form_builder.qtside.inspector.api import Registrar
from app.qt.QtCore import Qt
from app.qt.QtGui import QKeyEvent
from app.qt.QtWidgets import QCheckBox, QHBoxLayout, QInputDialog, QLabel, QPushButton, QVBoxLayout, QWidget

EXCLUSIVE_LABEL = "Only one can be on"


def register(registrar: Registrar) -> None:
    del registrar


def register_form_groups(registry: Any) -> None:
    registry.add("buttonGroups", "Button groups", _Body, order=140, applies=_has_groups)


def _has_groups(document: UiDocument) -> bool:
    return bool(q.button_groups(document))


class _Line(QWidget):
    def __init__(self, body: "_Body", name: str, group_id: int, members: Tuple[int, ...], exclusive: bool) -> None:
        super().__init__(body.widget)
        self._body = body
        self._name = name
        self._members = members
        self.setObjectName("formBuilder.buttonGroup.%s" % name)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        pick = QPushButton("%s · %d" % (name, len(members)), self)
        pick.setFlat(True)
        pick.setAccessibleName("Select the buttons of %s" % name)
        pick.clicked.connect(self.select_members)
        row.addWidget(pick, 1)
        box = QCheckBox(EXCLUSIVE_LABEL, self)
        box.setChecked(exclusive)
        box.toggled.connect(self._toggled)
        row.addWidget(box)
        self._group_id = group_id
        self._box = box

    def select_members(self) -> None:
        session = getattr(self._body.host, "session", None)
        if session is not None and self._members:
            from app.features.form_builder.engine.ids import NodeId

            session.selection.set(tuple(NodeId(m) for m in self._members), source=SelectionSource.PROGRAM)

    def _toggled(self, on: bool) -> None:
        from app.features.form_builder.engine.ids import NodeId

        value = None if on else BoolValue(False)
        self._body.host.run("Change button group %s" % self._name, [SetProperty(NodeId(self._group_id), "exclusive", value)])

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Delete:
            self._body.host.run("Ungroup buttons", [UngroupButtons(self._name)])
            return
        if event.key() == Qt.Key.Key_F2:
            from app.features.form_builder.engine.ids import NodeId

            new, ok = QInputDialog.getText(self, "Rename", "Object name", text=self._name)
            if ok and new and new != self._name:
                self._body.host.run("Rename %s" % self._name, [Rename(NodeId(self._group_id), new)])
            return
        super().keyPressEvent(event)


class _Body:
    def __init__(self, host: Any, parent: QWidget) -> None:
        self.host = host
        self.widget = QWidget(parent)
        self._layout = QVBoxLayout(self.widget)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._lines: List[_Line] = []

    def show(self, rows: Tuple[Any, ...]) -> None:
        del rows
        for line in self._lines:
            line.setParent(None)
            line.deleteLater()
        self._lines = []
        doc = self.host.document
        exclusive: Dict[str, bool] = {}
        for name, node_id, _members in q.button_groups(doc):
            entry = doc.node(node_id).prop("exclusive")
            exclusive[name] = not (entry is not None and isinstance(entry.value, BoolValue) and not entry.value.value)
        for name, node_id, members in q.button_groups(doc):
            line = _Line(self, name, int(node_id), tuple(int(m) for m in members), exclusive.get(name, True))
            self._layout.addWidget(line)
            self._lines.append(line)
        if not self._lines:
            self._layout.addWidget(QLabel("No button groups.", self.widget))
