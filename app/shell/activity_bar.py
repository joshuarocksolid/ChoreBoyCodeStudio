"""Vertical activity bar for switching sidebar panels (Explorer, Search, etc.)."""

from __future__ import annotations

from typing import Any

from app.qt.QtCore import QSize, Qt, Signal
from app.qt.QtGui import QColor, QIcon
from app.qt.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget


class ActivityBar(QWidget):
    """Narrow vertical icon strip for switching sidebar views."""

    view_changed: Any = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.activityBar")
        self.setFixedWidth(36)
        self._buttons: dict[str, QToolButton] = {}
        self._icon_factories: dict[str, Any] = {}
        self._badges: dict[str, QLabel] = {}
        self._active_view: str = ""
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(2, 4, 2, 4)
        self._layout.setSpacing(2)
        self._layout.addStretch()

    def add_view(
        self,
        view_id: str,
        label: str,
        tooltip: str,
        icon: QIcon | None = None,
        icon_factory: Any | None = None,
    ) -> None:
        btn = QToolButton(self)
        btn.setObjectName(f"shell.activityBar.btn.{view_id}")
        if icon is not None and not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(QSize(20, 20))
        else:
            btn.setText(label)
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setFixedSize(32, 32)
        btn.clicked.connect(lambda checked=False, vid=view_id: self._on_button_clicked(vid))
        insert_index = self._layout.count() - 1
        self._layout.insertWidget(insert_index, btn)
        self._buttons[view_id] = btn
        if icon_factory is not None:
            self._icon_factories[view_id] = icon_factory

        if not self._active_view:
            self.set_active_view(view_id)

    def index_of(self, view_id: str) -> int | None:
        try:
            return list(self._buttons).index(view_id)
        except ValueError:
            return None

    def recolor_factory_icons(self, normal: QColor, active: QColor) -> None:
        for view_id, factory in self._icon_factories.items():
            self.set_view_icon(view_id, factory(normal, active))

    def set_badge(self, view_id: str, count: int) -> None:
        """Show a small count on a view button. Zero hides it."""
        button = self._buttons.get(view_id)
        if button is None:
            return
        badge = self._badges.get(view_id)
        if badge is None:
            badge = QLabel(button)
            badge.setObjectName(f"shell.activityBar.badge.{view_id}")
            badge.setAlignment(Qt.AlignCenter)
            self._badges[view_id] = badge
        if count <= 0:
            badge.hide()
            return
        badge.setText(str(count))
        badge.adjustSize()
        badge.setFixedHeight(14)
        badge.setMinimumWidth(14)
        badge.move(max(0, button.width() - badge.width() - 1), 1)
        badge.show()
        badge.raise_()

    def set_active_view(self, view_id: str) -> None:
        self._active_view = view_id
        for vid, btn in self._buttons.items():
            btn.setChecked(vid == view_id)

    def set_view_icon(self, view_id: str, icon: QIcon) -> None:
        """Update icon for an existing view button."""
        button = self._buttons.get(view_id)
        if button is None or icon.isNull():
            return
        button.setIcon(icon)
        button.setIconSize(QSize(20, 20))

    def active_view(self) -> str:
        return self._active_view

    def _on_button_clicked(self, view_id: str) -> None:
        self.set_active_view(view_id)
        self.view_changed.emit(view_id)
