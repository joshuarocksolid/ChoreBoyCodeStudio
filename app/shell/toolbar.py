"""Shell run/debug toolbar widget."""

from __future__ import annotations

from typing import Any, Callable, List

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from app.shell.menus import MenuStubRegistry
from app.shell.toolbar_icons import build_toolbar_icon

_GROUP_1_IDS = (
    "shell.action.run.run",
    "shell.action.run.debug",
    "shell.action.run.runProject",
    "shell.action.run.debugProject",
    "shell.action.run.stop",
    "shell.action.run.restart",
)

_GROUP_2_IDS = (
    "shell.action.run.continue",
    "shell.action.run.pause",
    "shell.action.run.stepOver",
    "shell.action.run.stepInto",
    "shell.action.run.stepOut",
    "shell.action.run.removeAllBreakpoints",
)

_GROUP_RIGHT_IDS = (
    "shell.action.build.package",
)

_ACTION_ID_TO_OBJ_SUFFIX: dict[str, str] = {
    "shell.action.run.run": "run",
    "shell.action.run.debug": "debug",
    "shell.action.run.runProject": "runProject",
    "shell.action.run.debugProject": "debugProject",
    "shell.action.run.stop": "stop",
    "shell.action.run.restart": "restart",
    "shell.action.run.continue": "continue",
    "shell.action.run.pause": "pause",
    "shell.action.run.stepOver": "stepOver",
    "shell.action.run.stepInto": "stepInto",
    "shell.action.run.stepOut": "stepOut",
    "shell.action.run.removeAllBreakpoints": "removeAllBp",
    "shell.action.build.package": "package",
}


class RunToolbarWidget(QWidget):
    """Compact run/debug toolbar intended to sit above the editor area."""

    def __init__(
        self,
        menu_registry: MenuStubRegistry,
        parent: QWidget | None = None,
        on_target_summary_clicked: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("shell.toolbar.runDebug")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

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

        self._target_summary_button = QToolButton(self)
        self._target_summary_button.setObjectName("shell.toolbar.btn.runTarget")
        self._target_summary_button.setCursor(Qt.PointingHandCursor)
        self._target_summary_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._target_summary_button.setAutoRaise(False)
        self._target_summary_button.setText("Targets: open a file or project")
        self._target_summary_button.setToolTip("Shows what Run, Run Project, and the active named configuration will do.")
        self._target_summary_button.setEnabled(False)
        if on_target_summary_clicked is not None:
            self._target_summary_button.clicked.connect(on_target_summary_clicked)
        layout.addWidget(self._target_summary_button, 0)

        layout.addStretch(1)

        for action_id in _GROUP_RIGHT_IDS:
            btn = self._make_button(menu_registry, action_id)
            if btn is not None:
                layout.addWidget(btn)

        self._update_separator_visibility()

    def _make_button(self, registry: MenuStubRegistry, action_id: str) -> QToolButton | None:
        action = registry.action(action_id)
        if action is None:
            return None

        icon = build_toolbar_icon(action_id, accent_color="#5B8CFF")
        if icon is not None:
            action.setIcon(icon)

        suffix = _ACTION_ID_TO_OBJ_SUFFIX.get(action_id, "btn")
        obj_name = f"shell.toolbar.btn.{suffix}"

        btn = QToolButton(self)
        btn.setObjectName(obj_name)
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

    def set_target_summary(self, text: str, *, tooltip: str, enabled: bool) -> None:
        self._target_summary_button.setText(text)
        self._target_summary_button.setToolTip(tooltip)
        self._target_summary_button.setEnabled(enabled)


def build_run_toolbar_widget(
    menu_registry: MenuStubRegistry | None,
    parent: QWidget | None = None,
    on_target_summary_clicked: Callable[[], object] | None = None,
) -> RunToolbarWidget | None:
    """Factory: build toolbar widget or return None if registry unavailable."""
    if menu_registry is None:
        return None
    return RunToolbarWidget(
        menu_registry,
        parent=parent,
        on_target_summary_clicked=on_target_summary_clicked,
    )
