"""Editor tab page: the tab's content plus bars for disk conflicts and generated files."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from app.qt.QtCore import Signal
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from app.editors.generated_banner import GeneratedLock, generated_bar_text
from app.shell.editor_tab_bar import TAB_STATE_MISSING, TAB_STATE_STALE, missing_marker_icon, warning_marker_icon
from app.shell.icon_provider import lock_icon
from app.shell.theme_tokens import ShellThemeTokens

EDITOR_TAB_PAGE_OBJECT_NAME = "shell.editorTabPage"
INFO_BAR_OBJECT_NAME = "shell.editorInfoBar"
GENERATED_BAR_OBJECT_NAME = "shell.generatedFileBar"


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
        # A narrow split group wraps the message instead of cutting it off.
        self._message_label.setWordWrap(True)
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


class GeneratedFileBar(QFrame):
    """Bar above a generated file: what it is made from, where code belongs, and Edit anyway."""

    open_requested = Signal(str)
    edit_anyway_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(GENERATED_BAR_OBJECT_NAME)
        self._lock: Optional[GeneratedLock] = None
        self._tokens: Optional[ShellThemeTokens] = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)
        self._icon_label = QLabel(self)
        self._icon_label.setObjectName("shell.generatedFileBar.icon")
        layout.addWidget(self._icon_label)
        self._message_label = QLabel(self)
        self._message_label.setObjectName("shell.generatedFileBar.message")
        self._message_label.setWordWrap(True)
        layout.addWidget(self._message_label, 1)
        self._open_source_button = self._add_button(layout)
        self._open_source_button.setObjectName("shell.generatedFileBar.openSourceBtn")
        self._open_window_button = self._add_button(layout)
        self._open_window_button.setObjectName("shell.generatedFileBar.openWindowBtn")
        self._edit_anyway_button = self._add_button(layout)
        self._edit_anyway_button.setObjectName("shell.generatedFileBar.editAnywayBtn")
        self._edit_anyway_button.setText("Edit anyway")
        self._open_source_button.clicked.connect(lambda: self._open(window=False))
        self._open_window_button.clicked.connect(lambda: self._open(window=True))
        self._edit_anyway_button.clicked.connect(self.edit_anyway_requested.emit)
        self.setVisible(False)

    def _add_button(self, layout: QHBoxLayout) -> QPushButton:
        button = QPushButton(self)
        button.setAutoDefault(False)
        layout.addWidget(button)
        return button

    def _open(self, *, window: bool) -> None:
        lock = self._lock
        if lock is not None:
            self.open_requested.emit(lock.banner.window_name if window else lock.banner.source_name)

    def set_lock(self, lock: Optional[GeneratedLock]) -> None:
        if lock == self._lock:
            return
        self._lock = lock
        if lock is None:
            self.setVisible(False)
            return
        banner = lock.banner
        self._message_label.setText(generated_bar_text(lock))
        self._open_source_button.setText("Open %s" % banner.source_name)
        self._open_window_button.setText("Open %s" % banner.window_name)
        self._open_window_button.setVisible(bool(banner.window_name))
        self._edit_anyway_button.setVisible(not lock.edit_anyway)
        self._apply_look()
        self.setVisible(True)

    def apply_theme(self, tokens: ShellThemeTokens) -> None:
        self._tokens = tokens
        self._apply_look()

    def _apply_look(self) -> None:
        tokens = self._tokens
        if tokens is None:
            return
        editing = self._lock is not None and self._lock.edit_anyway
        edge = tokens.diag_warning_color if editing else tokens.accent
        self._icon_label.setPixmap(lock_icon(tokens.icon_primary).pixmap(16, 16))
        self.setStyleSheet(
            f"QFrame#shell\\.generatedFileBar {{ background: {tokens.panel_bg};"
            f" border-bottom: 1px solid {tokens.border}; border-left: 3px solid {edge}; }}"
            f"QFrame#shell\\.generatedFileBar QLabel {{ color: {tokens.text_primary}; background: transparent; }}"
            f"QFrame#shell\\.generatedFileBar QPushButton {{ background: {tokens.input_bg}; color: {tokens.text_primary};"
            f" border: 1px solid {tokens.border}; border-radius: 4px; padding: 3px 10px; font-weight: 600; }}"
            f"QFrame#shell\\.generatedFileBar QPushButton:focus {{"
            f" border: {tokens.focus_border_width}px solid {tokens.accent}; }}"
        )


class EditorTabPage(QWidget):
    """What a tab shows: the conflict and generated-file bars above the editor (or markdown pane)."""

    def __init__(self, content: QWidget, *, buffer_id: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(EDITOR_TAB_PAGE_OBJECT_NAME)
        self._buffer_id = buffer_id
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self.info_bar = DiskConflictInfoBar(self)
        self._layout.addWidget(self.info_bar, 0)
        self.generated_bar = GeneratedFileBar(self)
        self._layout.addWidget(self.generated_bar, 0)
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


def page_editor(page: Optional[QWidget]) -> Any:
    """The code editor a tab page shows (inside a markdown pane, if wrapped), or None."""
    if not isinstance(page, EditorTabPage):
        return None
    content = page.content()
    if isinstance(content, QPlainTextEdit):
        return content
    source_editor = getattr(content, "source_editor", None)
    if callable(source_editor):
        editor = source_editor()
        if isinstance(editor, QPlainTextEdit):
            return editor
    return None


__all__ = [
    "DiskConflictInfoBar",
    "EDITOR_TAB_PAGE_OBJECT_NAME",
    "EditorTabPage",
    "GENERATED_BAR_OBJECT_NAME",
    "GeneratedFileBar",
    "INFO_BAR_OBJECT_NAME",
    "info_bar_message",
    "page_editor",
]
