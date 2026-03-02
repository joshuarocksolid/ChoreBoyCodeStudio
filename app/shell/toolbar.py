"""Shell run/debug toolbar widget."""

from __future__ import annotations

from typing import Any, List

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from app.shell.menus import MenuStubRegistry

_GROUP_1_IDS = (
    "shell.action.run.run",
    "shell.action.run.debug",
    "shell.action.run.stop",
    "shell.action.run.restart",
    "shell.action.run.pythonConsole",
)

_GROUP_2_IDS = (
    "shell.action.run.continue",
    "shell.action.run.pause",
    "shell.action.run.stepOver",
    "shell.action.run.stepInto",
    "shell.action.run.stepOut",
    "shell.action.run.toggleBreakpoint",
)


class RunToolbarWidget(QWidget):
    """Compact run/debug toolbar intended to sit above the editor area."""

    def __init__(self, menu_registry: MenuStubRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.toolbar.runDebug")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        self._group2_buttons: List[QToolButton] = []
        self._separator: QFrame | None = None

        for action_id in _GROUP_1_IDS:
            btn = self._make_button(menu_registry, action_id)
            if btn is not None:
                layout.addWidget(btn)

        sep = QFrame(self)
        sep.setObjectName("shell.toolbar.separator")
        sep.setFrameShape(QFrame.VLine)
        sep.setFixedWidth(1)
        sep.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        layout.addWidget(sep)
        self._separator = sep

        for action_id in _GROUP_2_IDS:
            btn = self._make_button(menu_registry, action_id)
            if btn is not None:
                self._group2_buttons.append(btn)
                layout.addWidget(btn)

        layout.addStretch(1)
        self._update_separator_visibility()

    def _make_button(self, registry: MenuStubRegistry, action_id: str) -> QToolButton | None:
        action = registry.action(action_id)
        if action is None:
            return None

        btn = QToolButton(self)
        btn.setObjectName("shell.toolbar.btn")
        btn.setDefaultAction(action)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setVisible(action.isEnabled())
        action.changed.connect(lambda a=action, b=btn: self._sync_button(a, b))
        return btn

    def _sync_button(self, action: Any, btn: QToolButton) -> None:
        btn.setVisible(action.isEnabled())
        self._update_separator_visibility()

    def _update_separator_visibility(self) -> None:
        if self._separator is None:
            return
        any_visible = any(b.isVisible() for b in self._group2_buttons)
        self._separator.setVisible(any_visible)


def build_run_toolbar_widget(
    menu_registry: MenuStubRegistry | None,
    parent: QWidget | None = None,
) -> RunToolbarWidget | None:
    """Factory: build toolbar widget or return None if registry unavailable."""
    if menu_registry is None:
        return None
    return RunToolbarWidget(menu_registry, parent=parent)
