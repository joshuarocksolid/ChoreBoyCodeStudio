"""Read-only banner for a generated Python buffer."""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import Qt, Signal
from app.qt.QtGui import QColor, QIcon, QPainter, QPixmap
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from app.editors.generated_file import GeneratedBanner
from app.shell.theme_tokens import ShellThemeTokens


def generated_lock_icon(color: str = "#5A6168", size: int = 16) -> QIcon:
    """A small lock. The project tree and the banner share it."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    body_top = int(size * 0.42)
    painter.drawRoundedRect(int(size * 0.18), body_top, int(size * 0.64), int(size * 0.46), 1, 1)
    painter.setBrush(Qt.NoBrush)
    pen = painter.pen()
    pen.setColor(QColor(color))
    pen.setWidth(max(1, size // 8))
    painter.setPen(pen)
    shackle_w = int(size * 0.34)
    left = (size - shackle_w) // 2
    painter.drawArc(left, int(size * 0.12), shackle_w, int(size * 0.42), 0, 180 * 16)
    painter.end()
    return QIcon(pixmap)


class GeneratedFileBar(QFrame):
    """Lock, the generated-from sentence, and Open / Edit anyway."""

    open_source_requested = Signal(str)
    open_logic_requested = Signal(str)
    edit_anyway_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.generatedFileBar")
        self._banner: Optional[GeneratedBanner] = None
        self._tokens: Optional[ShellThemeTokens] = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        self._icon = QLabel(self)
        self._icon.setObjectName("shell.generatedFileBar.icon")
        layout.addWidget(self._icon)
        self._message = QLabel(self)
        self._message.setObjectName("shell.generatedFileBar.message")
        self._message.setWordWrap(True)
        layout.addWidget(self._message, 1)
        self._source_button = QPushButton(self)
        self._source_button.setObjectName("shell.generatedFileBar.openSource")
        self._logic_button = QPushButton(self)
        self._logic_button.setObjectName("shell.generatedFileBar.openLogic")
        self._edit_button = QPushButton("Edit anyway", self)
        self._edit_button.setObjectName("shell.generatedFileBar.editAnyway")
        for button in (self._source_button, self._logic_button, self._edit_button):
            button.setAutoDefault(False)
            layout.addWidget(button)
        self._source_button.clicked.connect(self._open_source)
        self._logic_button.clicked.connect(self._open_logic)
        self._edit_button.clicked.connect(self.edit_anyway_requested.emit)
        self.setVisible(False)

    def banner(self) -> Optional[GeneratedBanner]:
        return self._banner

    def message(self) -> str:
        return self._message.text()

    def show_banner(self, banner: GeneratedBanner) -> None:
        self._banner = banner
        self._message.setText(banner.message)
        source_name = banner.source_path.rsplit("/", 1)[-1]
        self._source_button.setText("Open %s" % source_name)
        self._source_button.setVisible(True)
        if banner.logic_path:
            logic_name = banner.logic_path.rsplit("/", 1)[-1]
            self._logic_button.setText("Open %s" % logic_name)
            self._logic_button.setVisible(True)
        else:
            self._logic_button.setVisible(False)
        self._edit_button.setVisible(True)
        self._apply_look()
        self.setVisible(True)

    def note_editable(self) -> None:
        """Edit anyway already made this tab writable. The button goes away."""
        self._edit_button.setVisible(False)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._apply_look()

    def _open_source(self) -> None:
        banner = self._banner
        if banner is not None:
            self.open_source_requested.emit(banner.source_path)

    def _open_logic(self) -> None:
        banner = self._banner
        if banner is not None and banner.logic_path:
            self.open_logic_requested.emit(banner.logic_path)

    def _apply_look(self) -> None:
        tokens = self._tokens
        muted = tokens.text_muted if tokens is not None else "#5A6168"
        self._icon.setPixmap(generated_lock_icon(muted, 16).pixmap(16, 16))
        if tokens is None:
            return
        self.setStyleSheet(
            "QFrame#shell\\.generatedFileBar { background: %s; color: %s;"
            " border-bottom: 1px solid %s; }"
            "QFrame#shell\\.generatedFileBar QLabel { color: %s; background: transparent; }"
            "QFrame#shell\\.generatedFileBar QPushButton { background: %s; color: %s;"
            " border: 1px solid %s; border-radius: 4px; padding: 3px 10px; }"
            % (
                tokens.panel_bg,
                tokens.text_primary,
                tokens.border,
                tokens.text_primary,
                tokens.input_bg,
                tokens.text_primary,
                tokens.border,
            )
        )
