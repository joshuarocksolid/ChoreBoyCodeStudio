"""Vertical activity bar for switching sidebar panels (Explorer, Search, etc.)."""

from __future__ import annotations

from PySide2.QtCore import QSize, Qt, Signal
from PySide2.QtGui import QIcon
from PySide2.QtWidgets import QToolButton, QVBoxLayout, QWidget


class ActivityBar(QWidget):
    """Narrow vertical icon strip for switching sidebar views."""

    view_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("shell.activityBar")
        self.setFixedWidth(36)
        self._buttons: dict[str, QToolButton] = {}
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

        if not self._active_view:
            self.set_active_view(view_id)

    def set_active_view(self, view_id: str) -> None:
        self._active_view = view_id
        for vid, btn in self._buttons.items():
            btn.setChecked(vid == view_id)

    def active_view(self) -> str:
        return self._active_view

    def _on_button_clicked(self, view_id: str) -> None:
        self.set_active_view(view_id)
        self.view_changed.emit(view_id)
