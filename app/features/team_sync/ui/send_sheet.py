"""Toolbar Send button and the sheet it opens."""

from __future__ import annotations

from typing import Callable, Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.features.team_sync.api import TeamStatus
from app.shell.theme_tokens import ShellThemeTokens


class SendToolbarButton(QToolButton):
    """Package-style Send. Hidden until the project is shared."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.toolbar.send")
        self.setText("Send")
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setCursor(Qt.PointingHandCursor)
        self._count = 0
        self._badge = QLabel(self)
        self._badge.setObjectName("shell.teamSync.toolbar.sendBadge")
        self._badge.hide()
        self.hide()

    def count(self) -> int:
        return self._count

    def apply_status(self, status: TeamStatus) -> None:
        self._count = len(status.pending) if status.shared else 0
        self.setVisible(status.shared)
        if self._count:
            self._badge.setText(str(self._count))
            self._badge.adjustSize()
            self._badge.move(self.width() - 8, 0)
            self._badge.show()
        else:
            self._badge.hide()

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        del tokens
        self.style().unpolish(self)
        self.style().polish(self)
        self._badge.style().unpolish(self._badge)
        self._badge.style().polish(self._badge)


class SendSheet(QFrame):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.teamSync.sendSheet")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setWindowFlags(Qt.Popup)
        self._on_send: Optional[Callable[[str, list[str]], None]] = None
        self._checks: list[tuple[QCheckBox, str]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        self._title = QLabel("Send", self)
        layout.addWidget(self._title)
        self._files = QWidget(self)
        self._files.setObjectName("shell.teamSync.sendSheetFiles")
        self._file_layout = QVBoxLayout(self._files)
        self._file_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._files)
        self._note = QTextEdit(self)
        self._note.setObjectName("shell.teamSync.sendSheetNote")
        self._note.setPlaceholderText("Note")
        self._note.setFixedHeight(72)
        layout.addWidget(self._note)
        self._send = QPushButton("Send", self)
        self._send.setObjectName("shell.teamSync.sendSheetSend")
        self._send.clicked.connect(self._send_clicked)
        layout.addWidget(self._send)
        self.setMinimumWidth(320)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        del tokens
        self.style().unpolish(self)
        self.style().polish(self)

    def present(
        self,
        anchor: QWidget,
        status: TeamStatus,
        shop_name: str,
        on_send: Callable[[str, list[str]], None],
    ) -> None:
        self._on_send = on_send
        self._send.setText(f"Send to {shop_name}" if shop_name else "Send")
        while self._file_layout.count():
            item = self._file_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._checks = []
        for change in status.pending:
            box = QCheckBox(f"{change.kind}  {change.path}", self._files)
            box.setChecked(True)
            self._file_layout.addWidget(box)
            self._checks.append((box, change.path))
        self.adjustSize()
        origin = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(origin)
        self.show()

    def _send_clicked(self) -> None:
        paths = [path for box, path in self._checks if box.isChecked()]
        note = self._note.toPlainText().strip()
        self.hide()
        if self._on_send is not None:
            self._on_send(note, paths)


__all__ = ["SendSheet", "SendToolbarButton"]
