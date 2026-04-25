"""Custom tab bar behavior for editor tabs."""

from __future__ import annotations

from typing import Callable

from PySide2.QtCore import QEvent, Qt
from PySide2.QtGui import QFont, QFontMetrics, QMouseEvent
from PySide2.QtWidgets import QStyle, QStyleOptionTab, QStylePainter, QTabBar, QWidget


class MiddleClickTabBar(QTabBar):
    """Editor tab bar with middle-click close and preview-tab styling."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tab_double_click_callback: Callable[[int], None] | None = None

    def set_tab_double_click_callback(self, callback: Callable[[int], None] | None) -> None:
        self._tab_double_click_callback = callback

    def mousePressEvent(self, arg__1: QMouseEvent) -> None:
        if arg__1.button() == Qt.MiddleButton:
            tab_index = self.tabAt(arg__1.pos())
            if tab_index >= 0:
                self.tabCloseRequested.emit(tab_index)
        else:
            super().mousePressEvent(arg__1)

    def mouseDoubleClickEvent(self, arg__1: QMouseEvent) -> None:  # noqa: N802 - Qt signature
        tab_index = self.tabAt(arg__1.pos())
        if tab_index >= 0 and self._tab_double_click_callback is not None:
            self._tab_double_click_callback(tab_index)
            arg__1.accept()
            return
        super().mouseDoubleClickEvent(arg__1)

    def paintEvent(self, arg__1: QEvent) -> None:  # noqa: N802 - Qt signature
        painter = QStylePainter(self)
        option = QStyleOptionTab()
        for index in range(self.count()):
            self.initStyleOption(option, index)
            data = self.tabData(index)
            is_preview = isinstance(data, dict) and bool(data.get("is_preview"))
            if is_preview:
                preview_font = QFont(self.font())
                preview_font.setItalic(True)
                option.fontMetrics = QFontMetrics(preview_font)
                painter.save()
                painter.setFont(preview_font)
            painter.drawControl(QStyle.CE_TabBarTabShape, option)
            painter.drawControl(QStyle.CE_TabBarTabLabel, option)
            if is_preview:
                painter.restore()
        arg__1.accept()
