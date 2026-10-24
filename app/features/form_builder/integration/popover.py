"""Small form popovers. They are not window-modal dialogs."""

from __future__ import annotations

from typing import Iterable

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QWidget

from app.features.form_builder.engine.shell_commands import FormCommand

_LAYOUT_CHOICES = (
    ("Vertical", "form.action.layoutVertical"),
    ("Horizontal", "form.action.layoutHorizontal"),
    ("Grid", "form.action.layoutGrid"),
    ("Form", "form.action.layoutForm"),
)


class ProblemPopover(QFrame):
    """The problem text when the Problems panel cannot show the row."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("formBuilder.problemPopover")
        self.setAccessibleName("Problem")
        self.setFocusPolicy(_no_focus())
        self.setMaximumWidth(480)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        self._text = QLabel(self)
        self._text.setObjectName("formBuilder.problemText")
        self._text.setWordWrap(True)
        self._text.setFocusPolicy(_no_focus())
        row.addWidget(self._text, 1)
        self.hide()

    def show_message(self, text: str) -> None:
        self._text.setText(text)
        self._text.setAccessibleName(text)
        self.show()
        self.raise_()
        self.place()

    def place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        width = min(480, max(self.sizeHint().width(), 160), max(1, parent.width() - 16))
        height = max(self.sizeHint().height(), 28)
        self.resize(width, height)
        self.move(max(0, (parent.width() - width) // 2), max(0, parent.height() - height - 16))


def open_layout_menu(parent: QWidget, commands: Iterable[FormCommand], at: object) -> QMenu:
    """A non-blocking menu of layout choices. Disabled rows carry a plain tooltip."""
    by_id = {command.command_id: command for command in commands}
    menu = QMenu(parent)
    menu.setObjectName("formBuilder.layoutPopover")
    menu.setToolTipsVisible(True)
    for label, command_id in _LAYOUT_CHOICES:
        action = menu.addAction(label)
        command = by_id.get(command_id)
        enabled = bool(command.available) if command is not None else False
        action.setEnabled(enabled)
        if not enabled:
            action.setToolTip("Not available yet")
    menu.popup(at)  # type: ignore[arg-type]
    return menu


def tree_contains(tree: QWidget, text: str) -> bool:
    """True when any row shows ``text``."""
    role_count = getattr(tree, "columnCount", None)
    columns = role_count() if callable(role_count) else 1
    root = getattr(tree, "invisibleRootItem", None)
    if not callable(root):
        return False
    return _walk(root(), text, max(1, int(columns)))


def _walk(item: object, text: str, columns: int) -> bool:
    reader = getattr(item, "text", None)
    if callable(reader):
        for column in range(columns):
            if text and text in str(reader(column)):
                return True
    count = getattr(item, "childCount", None)
    child = getattr(item, "child", None)
    if not callable(count) or not callable(child):
        return False
    for index in range(count()):
        found = child(index)
        if found is not None and _walk(found, text, columns):
            return True
    return False


def _no_focus() -> Qt.FocusPolicy:
    return getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
