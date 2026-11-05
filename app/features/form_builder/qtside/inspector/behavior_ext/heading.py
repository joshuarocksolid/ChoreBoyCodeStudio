"""Behavior section headers. Same disclosure as a Properties group."""

from __future__ import annotations

from app.qt.QtCore import Qt
from app.qt.QtGui import QFont
from app.qt.QtWidgets import QToolButton, QWidget


def section_heading(parent: QWidget, object_name: str, title: str) -> QToolButton:
    """An overline with an arrow. Checked means the section is open."""

    button = QToolButton(parent)
    button.setObjectName(object_name)
    button.setProperty("fbFlat", "true")
    button.setText(title)
    font = QFont()
    font.setPixelSize(10)
    weight = getattr(getattr(QFont, "Weight", QFont), "DemiBold")
    font.setWeight(weight)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    button.setFont(font)
    button.setCheckable(True)
    button.setChecked(True)
    button.setAccessibleName("%s group" % title.capitalize())
    style = getattr(getattr(Qt, "ToolButtonStyle", Qt), "ToolButtonTextBesideIcon")
    button.setToolButtonStyle(style)
    button.setArrowType(_arrow(True))
    button.setAutoRaise(True)
    button.setStyleSheet(
        "QToolButton { background: transparent; border: none; padding: 0px 2px; }"
    )
    button.toggled.connect(lambda checked, host=button: _toggle(host, checked))
    return button


def _toggle(button: QToolButton, checked: bool) -> None:
    button.setArrowType(_arrow(checked))
    overline = button.parentWidget()
    host = overline.parentWidget() if overline is not None else None
    layout = host.layout() if host is not None else None
    if layout is None or overline is None:
        return
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is None or widget is overline:
            continue
        widget.setVisible(checked)


def _arrow(expanded: bool) -> Qt.ArrowType:
    name = "DownArrow" if expanded else "RightArrow"
    arrows = getattr(Qt, "ArrowType", Qt)
    return getattr(arrows, name)
