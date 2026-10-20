"""Editor tab page: the tab's content plus an info bar for disk conflicts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide2.QtCore import Signal
from PySide2.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.shell.editor_tab_bar import TAB_STATE_MISSING, TAB_STATE_STALE, missing_marker_icon, warning_marker_icon
from app.shell.theme_tokens import ShellThemeTokens

EDITOR_TAB_PAGE_OBJECT_NAME = "shell.editorTabPage"
INFO_BAR_OBJECT_NAME = "shell.editorInfoBar"


def info_bar_message(state: str, file_path: str) -> str:
    name = Path(file_path).name
    if state == TAB_STATE_MISSING:
        return f"{name} is not on disk any more. Your text is still here."
    return f"{name} changed on disk after you opened it. You kept your version."


class DiskConflictInfoBar(QFrame):
    """In-editor bar that repeats a stale or missing tab's state with its actions."""

    reload_requested = Signal()
    compare_requested = Signal()
    save_as_requested = Signal()
    close_tab_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(INFO_BAR_OBJECT_NAME)
        self._state: Optional[str] = None
        self._tokens: Optional[ShellThemeTokens] = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        self._icon_label = QLabel(self)
        self._icon_label.setObjectName("shell.editorInfoBar.icon")
        layout.addWidget(self._icon_label)
        self._message_label = QLabel(self)
        self._message_label.setObjectName("shell.editorInfoBar.message")
        layout.addWidget(self._message_label, 1)
        self._reload_button = self._add_button(layout, "Reload from Disk")
        self._reload_button.setObjectName("shell.editorInfoBar.reloadBtn")
        self._compare_button = self._add_button(layout, "Compare...")
        self._compare_button.setObjectName("shell.editorInfoBar.compareBtn")
        self._save_as_button = self._add_button(layout, "Save As...")
        self._save_as_button.setObjectName("shell.editorInfoBar.saveAsBtn")
        self._close_button = self._add_button(layout, "Close Tab")
        self._close_button.setObjectName("shell.editorInfoBar.closeTabBtn")
        self._reload_button.clicked.connect(self.reload_requested.emit)
        self._compare_button.clicked.connect(self.compare_requested.emit)
        self._save_as_button.clicked.connect(self.save_as_requested.emit)
        self._close_button.clicked.connect(self.close_tab_requested.emit)
        self.setVisible(False)

    def _add_button(self, layout: QHBoxLayout, text: str) -> QPushButton:
        button = QPushButton(text, self)
        button.setAutoDefault(False)
        layout.addWidget(button)
        return button

    def state(self) -> Optional[str]:
        return self._state

    def message(self) -> str:
        return self._message_label.text()

    def set_state(self, state: Optional[str], file_path: str) -> None:
        if state not in (TAB_STATE_STALE, TAB_STATE_MISSING):
            self._state = None
            self.setVisible(False)
            return
        changed = state != self._state
        self._state = state
        self._message_label.setText(info_bar_message(state, file_path))
        stale = state == TAB_STATE_STALE
        self._reload_button.setVisible(stale)
        self._compare_button.setVisible(stale)
        self._save_as_button.setVisible(not stale)
        self._close_button.setVisible(not stale)
        if changed:
            self._apply_look()
        self.setVisible(True)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._apply_look()

    def _apply_look(self) -> None:
        tokens = self._tokens
        warning = (tokens.diag_warning_color if tokens else "") or "#D97706"
        error = (tokens.diag_error_color if tokens else "") or "#E03131"
        color = warning if self._state == TAB_STATE_STALE else error
        icon = warning_marker_icon(color, 16) if self._state == TAB_STATE_STALE else missing_marker_icon(color, 16)
        self._icon_label.setPixmap(icon.pixmap(16, 16))
        if tokens is None:
            self.setStyleSheet(f"QFrame#shell\\.editorInfoBar {{ border-left: 3px solid {color}; }}")
            return
        self.setStyleSheet(
            f"QFrame#shell\\.editorInfoBar {{ background: {tokens.panel_bg};"
            f" border-bottom: 1px solid {tokens.border}; border-left: 3px solid {color}; }}"
            f"QFrame#shell\\.editorInfoBar QLabel {{ color: {tokens.text_primary}; background: transparent; }}"
            f"QFrame#shell\\.editorInfoBar QPushButton {{ background: {tokens.input_bg}; color: {tokens.text_primary};"
            f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 3px 10px; font-weight: 600; }}"
        )


class EditorTabPage(QWidget):
    """What a tab shows: the conflict info bar above the editor (or markdown pane)."""

    def __init__(self, content: QWidget, *, buffer_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(EDITOR_TAB_PAGE_OBJECT_NAME)
        self._buffer_id = buffer_id
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.info_bar = DiskConflictInfoBar(self)
        self._layout.addWidget(self.info_bar, 0)
        self._content = content
        content.setParent(self)
        self._layout.addWidget(content, 1)
        self.setFocusProxy(content)

    @property
    def buffer_id(self) -> str:
        return self._buffer_id

    def content(self) -> QWidget:
        return self._content

    def set_content(self, content: QWidget) -> None:
        if content is self._content:
            return
        old = self._content
        # The new content may be a child of the old one (a markdown pane being
        # unwrapped); take it out first. Whoever replaced the old widget deletes it.
        content.setParent(self)
        self._layout.removeWidget(old)
        old.hide()
        self._content = content
        self._layout.addWidget(content, 1)
        self.setFocusProxy(content)
        content.show()


__all__ = [
    "DiskConflictInfoBar",
    "EDITOR_TAB_PAGE_OBJECT_NAME",
    "EditorTabPage",
    "INFO_BAR_OBJECT_NAME",
    "info_bar_message",
]
