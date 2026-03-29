"""Shell run/debug toolbar widget."""

from __future__ import annotations

from typing import Any, Callable, List

from PySide2.QtCore import Qt, Signal
from PySide2.QtGui import QKeyEvent, QMouseEvent, QResizeEvent
from PySide2.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.shell.menus import MenuStubRegistry
from app.shell.run_target_summary import RunTargetSummaryViewModel
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

class RunTargetSummaryPanel(QFrame):
    """Two-line informational run summary; optionally emits clicked when interactive."""

    clicked: Any = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.toolbar.btn.runTarget")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setMinimumWidth(280)
        self.setProperty("runTargetTone", "normal")

        self._full_line1 = "Editor file: —"
        self._full_line2 = "Project run: open a project"
        self._interactive = False

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 4, 8, 4)
        outer.setSpacing(8)

        text_box = QWidget(self)
        text_box.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        text_layout = QVBoxLayout(text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)

        self._line1_label = QLabel(self._full_line1, text_box)
        self._line1_label.setObjectName("shell.toolbar.runTarget.line1")
        self._line1_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._line1_label.setWordWrap(False)
        self._line1_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._line1_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._line2_label = QLabel(self._full_line2, text_box)
        self._line2_label.setObjectName("shell.toolbar.runTarget.line2")
        self._line2_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._line2_label.setWordWrap(False)
        self._line2_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._line2_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        text_layout.addWidget(self._line1_label)
        text_layout.addWidget(self._line2_label)

        self._chevron = QLabel("›", self)
        self._chevron.setObjectName("shell.toolbar.runTarget.chevron")
        self._chevron.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._chevron.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._chevron.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        outer.addWidget(text_box, 1)
        outer.addWidget(self._chevron, 0)

        self.set_interactive(False)

    def set_run_target_view_model(self, vm: RunTargetSummaryViewModel) -> None:
        self._full_line1 = vm.line1
        self._full_line2 = vm.line2
        self.setToolTip(vm.tool_tip)
        self.setAccessibleName(vm.accessible_name)
        self.setAccessibleDescription(vm.accessible_description)

        tone = "muted" if vm.interactive_muted else "normal"
        if self.property("runTargetTone") != tone:
            self.setProperty("runTargetTone", tone)
            polish = self.style()
            if polish is not None:
                polish.unpolish(self)
                polish.polish(self)

        self._apply_elided_texts()

    def set_interactive(self, interactive: bool) -> None:
        self._interactive = interactive
        self.setCursor(Qt.PointingHandCursor if interactive else Qt.ArrowCursor)
        self._chevron.setVisible(interactive)
        self.setFocusPolicy(Qt.StrongFocus if interactive else Qt.NoFocus)

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._apply_elided_texts()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_elided_texts()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._interactive
            and event.button() == Qt.LeftButton
            and self.rect().contains(event.pos())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if self._interactive and key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)

    def _apply_elided_texts(self) -> None:
        reserve = 44 if self._interactive else 16
        panel_w = self.width()
        if panel_w <= reserve + 8:
            panel_w = max(self.minimumWidth(), 320)
        inner = max(200, panel_w - reserve)
        fm1 = self._line1_label.fontMetrics()
        fm2 = self._line2_label.fontMetrics()
        w1_need = fm1.horizontalAdvance(self._full_line1)
        w2_need = fm2.horizontalAdvance(self._full_line2)
        self._line1_label.setText(
            self._full_line1 if w1_need <= inner else fm1.elidedText(self._full_line1, Qt.ElideRight, inner)
        )
        self._line2_label.setText(
            self._full_line2 if w2_need <= inner else fm2.elidedText(self._full_line2, Qt.ElideRight, inner)
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

        self._target_summary_panel = RunTargetSummaryPanel(self)
        interactive = on_target_summary_clicked is not None
        self._target_summary_panel.set_interactive(interactive)
        if on_target_summary_clicked is not None:
            self._target_summary_panel.clicked.connect(on_target_summary_clicked)
        layout.addWidget(self._target_summary_panel, 0)

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

    def set_run_target_view_model(self, view_model: RunTargetSummaryViewModel) -> None:
        self._target_summary_panel.set_run_target_view_model(view_model)


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
