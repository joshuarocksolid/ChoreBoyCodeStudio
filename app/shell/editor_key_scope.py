"""Keeps editor-only window shortcuts (Indent on Tab, Outdent on Shift+Tab) inside code editors."""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from app.editors.code_editor_widget import CodeEditorWidget
from app.qt.QtCore import QEvent, QObject, Qt
from app.qt.QtGui import QKeySequence
from app.qt.QtWidgets import QApplication, QWidget

EDITOR_ONLY_ACTION_IDS = ("shell.action.edit.indent", "shell.action.edit.outdent")


def _key_sequence_text(event: object) -> str:
    """Portable text of a key event, with Backtab spelled Shift+Tab."""
    key = int(getattr(event, "key")())
    mods = getattr(event, "modifiers")()
    if key == int(Qt.Key_Backtab):
        key = int(Qt.Key_Tab)
        mods = mods | Qt.ShiftModifier
    flags = getattr(mods, "value", mods)
    try:
        sequence = QKeySequence(int(flags) | key)
    except TypeError:
        return ""
    return sequence.toString(QKeySequence.PortableText)


def _is_in_code_editor(widget: QWidget) -> bool:
    current: Optional[QWidget] = widget
    while current is not None:
        if isinstance(current, CodeEditorWidget):
            return True
        current = current.parentWidget()
    return False


class EditorKeyScope(QObject):
    """Lets editor-only shortcut keys reach the focused widget outside code editors.

    The indent actions are window shortcuts, so without this Tab never moves
    focus anywhere in the window. The filter sits only on the focused widget
    of this window, and only while that widget is not in a code editor.
    Accepting ``ShortcutOverride`` there hands the key press to the widget,
    which moves focus as Qt normally does.
    """

    def __init__(self, window: QWidget, actions: Callable[[], Iterable[object]]) -> None:
        super().__init__(window)
        self._window = window
        self._actions = actions
        self._watched: Optional[QWidget] = None
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.focusChanged.connect(self._handle_focus_changed)
            self._handle_focus_changed(None, app.focusWidget())

    def _handle_focus_changed(self, _old: Optional[QWidget], new: Optional[QWidget]) -> None:
        if self._watched is not None:
            try:
                self._watched.removeEventFilter(self)
            except RuntimeError:
                pass
            self._watched = None
        if new is None or not self._owns(new) or _is_in_code_editor(new):
            return
        new.installEventFilter(self)
        self._watched = new

    def _owns(self, widget: QWidget) -> bool:
        """This window, or a popup or tool window parented to it (a form builder item editor)."""
        current: Optional[QWidget] = widget.window()
        while current is not None:
            if current is self._window:
                return True
            parent = current.parentWidget()
            current = parent.window() if parent is not None else None
        return False

    def _editor_only_keys(self) -> set[str]:
        keys = set()
        for action in self._actions():
            text = getattr(action, "shortcut")().toString(QKeySequence.PortableText)
            if text:
                keys.add(text)
        return keys

    def eventFilter(self, watched: object, event: object) -> bool:  # noqa: N802 - Qt API
        del watched
        if getattr(event, "type")() != QEvent.ShortcutOverride:
            return False
        if _key_sequence_text(event) not in self._editor_only_keys():
            return False
        getattr(event, "accept")()
        return True
