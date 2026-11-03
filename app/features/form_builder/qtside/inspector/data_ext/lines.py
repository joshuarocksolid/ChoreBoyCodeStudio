"""UX-LINES-001. The selected table view's lines, with Edit…."""

from __future__ import annotations

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.engine.ui4.nodes import WidgetNode
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.lines_sheet import open_lines_sheet, summary
from app.features.form_builder.qtside.inspector.data_ext import DataSection
from app.qt.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class _Lines(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.inspectorData.lines")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        self._sentence = QLabel(self)
        self._sentence.setObjectName("formBuilder.inspectorData.linesText")
        self._sentence.setWordWrap(True)
        layout.addWidget(self._sentence)
        self._edit = QPushButton("Edit…", self)
        self._edit.setObjectName("formBuilder.inspectorData.linesEdit")
        self._edit.clicked.connect(self._on_edit)
        layout.addWidget(self._edit)
        self._add = QPushButton("Add lines…", self)
        self._add.setObjectName("formBuilder.inspectorData.linesAdd")
        self._add.clicked.connect(self._on_add)
        layout.addWidget(self._add)

    def refresh(self) -> None:
        session = session_of(self)
        document = session.document if session is not None else None
        text = summary(document) if document is not None else ""
        node = _selected(session)
        own = ""
        if node is not None and document is not None:
            from app.features.form_builder.qtside.data_panel.lines_sheet import lines_on

            for name, rows in lines_on(document):
                if name == node.object_name:
                    own = "Lines from %s → %s" % (rows.table, name)
        self._sentence.setText(own or text)
        self._edit.setVisible(bool(own))
        self._add.setVisible(not own)

    def _on_edit(self) -> None:
        session = session_of(self)
        node = _selected(session)
        if node is None or not node.object_name:
            return
        try:
            open_lines_sheet(self, edit_name=node.object_name)
        except CommandRejected as exc:
            narrate(self, str(exc))

    def _on_add(self) -> None:
        try:
            open_lines_sheet(self)
        except CommandRejected as exc:
            narrate(self, str(exc))


def _create(parent: QWidget) -> QWidget:
    return _Lines(parent)


def _applies(class_name: str) -> bool:
    return class_name == "QTableView"


def register(registry: object) -> None:
    getattr(registry, "add")(DataSection("lines", 40, _create, _applies))


def _selected(session: object):
    if session is None:
        return None
    selection = getattr(session, "selection", None)
    state = getattr(selection, "state", None)
    ids = getattr(state, "ids", ()) or ()
    if len(ids) != 1:
        return None
    document = session.document
    if not document.contains(ids[0]):
        return None
    node = document.node(ids[0])
    if isinstance(node, WidgetNode) and node.class_name == "QTableView":
        return node
    return None
