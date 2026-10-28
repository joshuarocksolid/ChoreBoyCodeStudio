"""Saved pieces under the Insert list (UX-CLIP-006). The list stays hidden while empty."""

from __future__ import annotations

from typing import Optional, Protocol, Sequence

from app.qt.QtCore import QEvent, QMimeData, QPoint, Qt
from app.qt.QtGui import QDrag, QKeyEvent
from app.qt.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from app.features.form_builder.engine.ids import NodeId
from app.features.form_builder.qtside.canvas.core.palette import MIME_DESIGNER_FRAGMENT, MIME_FRAGMENT, MIME_NODE
from app.features.form_builder.qtside.theme.chrome import FormChrome

_ROW_ROLE = Qt.ItemDataRole.UserRole


class PieceSource(Protocol):
    """What the piece box asks of its pane."""

    def save_node(self, node_id: NodeId) -> None: ...

    def piece_menu(self, index: int): ...  # type: ignore[no-untyped-def]

    def insert_piece(self, index: int) -> None: ...

    def piece_at(self, index: int): ...  # type: ignore[no-untyped-def]


class PieceBox(QWidget):
    def __init__(self, pane: PieceSource, parent: QWidget) -> None:
        super().__init__(parent)
        self._pane = pane
        self.setObjectName("formBuilder.savedPiecesBox")
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)
        self.title = QLabel("Saved pieces", self)
        self.title.setObjectName("formBuilder.sectionTitle")
        layout.addWidget(self.title)
        self.list = PieceList(self)
        self.list.setObjectName("formBuilder.savedPieces")
        self.list.setAccessibleName("Saved pieces")
        self.list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list.setAcceptDrops(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        layout.addWidget(self.list)
        self.list.hide()

    def fill(self, pieces: Sequence[object]) -> None:
        self.list.clear()
        for index, piece in enumerate(pieces):
            name = str(getattr(piece, "name"))
            item = QListWidgetItem(name)
            item.setData(int(_ROW_ROLE), index)
            item.setToolTip("Insert %s. Press Enter." % name)
            self.list.addItem(item)
        self._fit()

    def apply_chrome(self, chrome: FormChrome) -> None:
        self.list.setStyleSheet(
            "QListWidget { background: %s; color: %s; border: 1px solid %s; }"
            "QListWidget::item:selected { background: %s; color: %s; }"
            "QListWidget:focus { border: %dpx solid %s; }"
            % (
                chrome.input,
                chrome.text,
                chrome.border,
                chrome.selected,
                chrome.text,
                chrome.focus_width,
                chrome.accent,
            )
        )

    def showEvent(self, event: QEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._fit()

    def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
        accept_node(event)

    def dragMoveEvent(self, event: object) -> None:  # type: ignore[override]
        accept_node(event)

    def dropEvent(self, event: object) -> None:  # type: ignore[override]
        node_id = accept_node(event)
        if node_id is not None:
            self._pane.save_node(node_id)

    def _fit(self) -> None:
        count = self.list.count()
        if count < 1:
            return
        row_h = self.list.sizeHintForRow(0)
        if row_h < 1:
            return
        shown = count if count < 8 else 8
        self.list.setFixedHeight(row_h * shown + self.list.frameWidth() * 2)

    def _menu(self, pos: QPoint) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        raw = item.data(int(_ROW_ROLE))
        if raw is None:
            return
        self._pane.piece_menu(int(raw)).popup(self.list.mapToGlobal(pos))


class PieceList(QListWidget):
    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            item = self.currentItem()
            raw = None if item is None else item.data(int(_ROW_ROLE))
            box = self.parent()
            if raw is not None and isinstance(box, PieceBox):
                box._pane.insert_piece(int(raw))
                return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event: QEvent) -> None:  # type: ignore[override]
        buttons = getattr(event, "buttons")()
        if not buttons & Qt.MouseButton.LeftButton:
            super().mouseMoveEvent(event)  # type: ignore[arg-type]
            return
        item = self.currentItem()
        if item is None:
            return
        raw = item.data(int(_ROW_ROLE))
        if raw is None:
            return
        box = self.parent()
        if not isinstance(box, PieceBox):
            return
        piece = box._pane.piece_at(int(raw))
        if piece is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        raw_xml = str(getattr(piece, "xml")).encode("utf-8")
        mime.setData(MIME_FRAGMENT, raw_xml)
        mime.setData(MIME_DESIGNER_FRAGMENT, raw_xml)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)

    def dragEnterEvent(self, event: object) -> None:  # type: ignore[override]
        self.parent().dragEnterEvent(event)  # type: ignore[attr-defined]

    def dragMoveEvent(self, event: object) -> None:  # type: ignore[override]
        self.parent().dragMoveEvent(event)  # type: ignore[attr-defined]

    def dropEvent(self, event: object) -> None:  # type: ignore[override]
        self.parent().dropEvent(event)  # type: ignore[attr-defined]


def accept_node(event: object) -> Optional[NodeId]:
    mime = getattr(event, "mimeData", lambda: None)()
    if mime is None or not mime.hasFormat(MIME_NODE):
        event.ignore()  # type: ignore[attr-defined]
        return None
    try:
        node_id = NodeId(int(bytes(mime.data(MIME_NODE)).decode("utf-8").strip()))
    except ValueError:
        event.ignore()  # type: ignore[attr-defined]
        return None
    event.acceptProposedAction()  # type: ignore[attr-defined]
    return node_id
