"""VS Code-style section header for the outline panel."""

from __future__ import annotations

from typing import Any, Optional

from PySide2.QtCore import QSize, Qt, Signal
from PySide2.QtGui import QPalette
from PySide2.QtWidgets import (
    QAction,
    QActionGroup,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from app.shell.outline.outline_icons import chevron_icon, make_codicon_text_icon
from app.shell.outline.outline_tree import (
    SORT_CATEGORY,
    SORT_NAME,
    SORT_POSITION,
    _VALID_SORT_MODES,
)


class _OutlineHeaderBar(QWidget):
    """VS Code-style section header: chevron + title + file label + actions."""

    toggled: Any = Signal(bool)
    filter_toggled: Any = Signal(bool)
    follow_cursor_toggled: Any = Signal(bool)
    sort_mode_changed: Any = Signal(str)
    collapse_all_clicked: Any = Signal()
    expand_all_clicked: Any = Signal()
    hide_clicked: Any = Signal()

    MIN_HEADER_HEIGHT = 28

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.outlinePanel.header")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(self.MIN_HEADER_HEIGHT)
        self.setProperty("collapsed", False)

        self._collapsed = False
        self._hover = False
        self._sort_mode = SORT_POSITION

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        self._chevron_btn = QToolButton(self)
        self._chevron_btn.setObjectName("shell.outlinePanel.chevron")
        self._chevron_btn.setAutoRaise(True)
        self._chevron_btn.setFocusPolicy(Qt.NoFocus)
        self._chevron_btn.setIconSize(QSize(12, 12))
        self._chevron_btn.setCursor(Qt.PointingHandCursor)
        self._chevron_btn.clicked.connect(self._handle_chevron_clicked)
        layout.addWidget(self._chevron_btn)

        self._title_label = QLabel("OUTLINE", self)
        self._title_label.setObjectName("shell.outlinePanel.title")
        layout.addWidget(self._title_label)

        self._file_label = QLabel("", self)
        self._file_label.setObjectName("shell.outlinePanel.fileLabel")
        self._file_label.setTextInteractionFlags(Qt.NoTextInteraction)
        layout.addWidget(self._file_label, 1)

        self._filter_btn = self._make_action_button(
            "shell.outlinePanel.action.filter",
            tooltip="Filter symbols",
            checkable=True,
        )
        self._filter_btn.toggled.connect(self.filter_toggled)
        layout.addWidget(self._filter_btn)

        self._follow_btn = self._make_action_button(
            "shell.outlinePanel.action.follow",
            tooltip="Follow Cursor",
            checkable=True,
        )
        self._follow_btn.setChecked(True)
        self._follow_btn.toggled.connect(self.follow_cursor_toggled)
        layout.addWidget(self._follow_btn)

        self._sort_btn = self._make_action_button(
            "shell.outlinePanel.action.sort",
            tooltip="Sort By",
            checkable=False,
        )
        self._sort_btn.setPopupMode(QToolButton.InstantPopup)
        self._sort_menu = QMenu(self._sort_btn)
        self._sort_action_group = QActionGroup(self._sort_menu)
        self._sort_action_group.setExclusive(True)
        self._sort_actions: dict[str, QAction] = {}
        for mode, label in (
            (SORT_POSITION, "Sort By: Position"),
            (SORT_NAME, "Sort By: Name"),
            (SORT_CATEGORY, "Sort By: Category"),
        ):
            action = QAction(label, self._sort_menu)
            action.setCheckable(True)
            action.setData(mode)
            self._sort_action_group.addAction(action)
            self._sort_menu.addAction(action)
            self._sort_actions[mode] = action
        self._sort_actions[SORT_POSITION].setChecked(True)
        self._sort_action_group.triggered.connect(self._handle_sort_action_triggered)
        self._sort_btn.setMenu(self._sort_menu)
        layout.addWidget(self._sort_btn)

        self._collapse_all_btn = self._make_action_button(
            "shell.outlinePanel.action.collapseAll",
            tooltip="Collapse All",
            checkable=False,
        )
        self._collapse_all_btn.clicked.connect(self.collapse_all_clicked)
        layout.addWidget(self._collapse_all_btn)

        self._more_btn = self._make_action_button(
            "shell.outlinePanel.action.more",
            tooltip="More Actions",
            checkable=False,
        )
        self._more_btn.setPopupMode(QToolButton.InstantPopup)
        self._more_menu = QMenu(self._more_btn)
        self._expand_all_action = QAction("Expand All", self._more_menu)
        self._expand_all_action.triggered.connect(self.expand_all_clicked)
        self._more_menu.addAction(self._expand_all_action)
        self._collapse_all_action = QAction("Collapse All", self._more_menu)
        self._collapse_all_action.triggered.connect(self.collapse_all_clicked)
        self._more_menu.addAction(self._collapse_all_action)
        self._more_menu.addSeparator()
        self._hide_action = QAction("Hide Outline", self._more_menu)
        self._hide_action.triggered.connect(self.hide_clicked)
        self._more_menu.addAction(self._hide_action)
        self._more_btn.setMenu(self._more_menu)
        layout.addWidget(self._more_btn)

        self._update_chevron_icon()
        self._refresh_action_visibility()

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setProperty("collapsed", bool(collapsed))
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self._update_chevron_icon()
        self._refresh_action_visibility()

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_file_label(self, text: str) -> None:
        self._file_label.setText(text)

    def set_filter_active(self, active: bool) -> None:
        was = self._filter_btn.blockSignals(True)
        self._filter_btn.setChecked(active)
        self._filter_btn.blockSignals(was)
        self._refresh_action_visibility()

    def set_follow_cursor(self, follow: bool) -> None:
        was = self._follow_btn.blockSignals(True)
        self._follow_btn.setChecked(follow)
        self._follow_btn.blockSignals(was)
        self._refresh_action_visibility()

    def set_sort_mode(self, mode: str) -> None:
        if mode not in _VALID_SORT_MODES:
            mode = SORT_POSITION
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        action = self._sort_actions.get(mode)
        if action is not None:
            was = self._sort_action_group.blockSignals(True)
            action.setChecked(True)
            self._sort_action_group.blockSignals(was)

    def chevron_button(self) -> QToolButton:
        return self._chevron_btn

    def filter_button(self) -> QToolButton:
        return self._filter_btn

    def follow_button(self) -> QToolButton:
        return self._follow_btn

    def sort_button(self) -> QToolButton:
        return self._sort_btn

    def collapse_all_button(self) -> QToolButton:
        return self._collapse_all_btn

    def more_button(self) -> QToolButton:
        return self._more_btn

    def apply_theme_colors(self, *, icon_color: str, accent_color: str) -> None:
        self._icon_color = icon_color
        self._accent_color = accent_color
        self._update_chevron_icon()
        self._update_action_icons()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.LeftButton:
            target = self.childAt(event.pos())
            if target is None or target is self._chevron_btn or target is self._title_label or target is self._file_label:
                self._toggle_collapsed()
                event.accept()
                return
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover = True
        self._refresh_action_visibility()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover = False
        self._refresh_action_visibility()
        super().leaveEvent(event)

    def _make_action_button(
        self,
        object_name: str,
        *,
        tooltip: str,
        checkable: bool,
    ) -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName(object_name)
        btn.setAutoRaise(True)
        btn.setCheckable(checkable)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip(tooltip)
        btn.setIconSize(QSize(14, 14))
        btn.setFocusPolicy(Qt.NoFocus)
        return btn

    def _toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)
        self.toggled.emit(self._collapsed)

    def _handle_chevron_clicked(self) -> None:
        self._toggle_collapsed()

    def _handle_sort_action_triggered(self, action: QAction) -> None:
        mode = action.data()
        if not isinstance(mode, str) or mode not in _VALID_SORT_MODES:
            return
        if mode == self._sort_mode:
            return
        self._sort_mode = mode
        self.sort_mode_changed.emit(mode)

    def _resolved_icon_color(self) -> str:
        return getattr(self, "_icon_color", self.palette().color(QPalette.Text).name())

    def _resolved_accent_color(self) -> str:
        return getattr(self, "_accent_color", self.palette().color(QPalette.Highlight).name())

    def _update_chevron_icon(self) -> None:
        color = self._resolved_icon_color()
        self._chevron_btn.setIcon(chevron_icon(color, expanded=not self._collapsed))

    def _update_action_icons(self) -> None:
        color = self._resolved_icon_color()
        self._filter_btn.setIcon(make_codicon_text_icon("F", color))
        self._follow_btn.setIcon(make_codicon_text_icon("\u00b7", color))
        self._sort_btn.setIcon(make_codicon_text_icon("\u21f5", color))
        self._collapse_all_btn.setIcon(make_codicon_text_icon("\u2212", color))
        self._more_btn.setIcon(make_codicon_text_icon("\u22ef", color))

    def _refresh_action_visibility(self) -> None:
        if self._collapsed:
            for btn in self._action_buttons():
                btn.setVisible(False)
            return
        show_all = self._hover
        for btn in self._action_buttons():
            sticky = btn.isCheckable() and btn.isChecked()
            btn.setVisible(show_all or sticky)

    def _action_buttons(self) -> tuple[QToolButton, ...]:
        return (
            self._filter_btn,
            self._follow_btn,
            self._sort_btn,
            self._collapse_all_btn,
            self._more_btn,
        )
