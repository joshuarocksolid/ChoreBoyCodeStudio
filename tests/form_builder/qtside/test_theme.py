"""The realized form keeps the Fusion runtime look when the shell theme changes."""

from __future__ import annotations

import pytest

from app.qt.QtGui import QColor, QPalette  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QLabel, QMainWindow
from app.features.form_builder.qtside.theme.runtime import (
    host_form,
    runtime_palette,
    selectors_are_tooltip_only,
)
from tests.form_builder.qtside.support import form, opened

pytestmark = pytest.mark.usefixtures("qapp")

_FORM = form(
    'class="QWidget" name="Form"',
    """
  <property name="styleSheet"><string>QLabel#caption { color: #123456; }</string></property>
  <layout class="QVBoxLayout" name="lay">
   <item><widget class="QLabel" name="caption"><property name="text"><string>Hello</string></property></widget></item>
  </layout>
""",
)


def _role(name: str) -> object:
    return getattr(getattr(QPalette, "ColorRole", QPalette), name)


def _color(widget: object, name: str) -> str:
    return widget.palette().color(_role(name)).name()  # type: ignore[attr-defined]


def test_theme_switch_does_not_reach_the_realized_form(qapp: QApplication) -> None:
    reference = runtime_palette()
    saved_palette = QPalette(qapp.palette())
    saved_sheet = qapp.styleSheet()
    try:
        with opened(_FORM) as (session, realizer):
            root = realizer.root_widget
            assert root is not None
            label_id = session.document.by_name("caption")[0]
            label = realizer.widget_for(label_id)
            assert isinstance(label, QLabel)
            assert root.styleSheet() == "QLabel#caption { color: #123456; }"
            view = host_form(root)
            assert view.scene() is not None
            window_role = _role("Window")
            fusion_window = reference.color(window_role).name()
            assert _color(root, "Window") == fusion_window
            chrome = QMainWindow()
            chrome.setStyleSheet("QWidget { color: #ff00ff; background-color: #00ff00; }")
            for window, text in (("#000000", "#ffffff"), ("#ffffff", "#000000")):
                themed = QPalette(saved_palette)
                themed.setColor(window_role, QColor(window))
                themed.setColor(_role("WindowText"), QColor(text))
                qapp.setPalette(themed)
                assert _color(root, "Window") == fusion_window
                assert _color(label, "WindowText") != "#ff00ff"
                assert root.styleSheet() == "QLabel#caption { color: #123456; }"
            with opened(_FORM) as (other_session, other):
                other_root = other.root_widget
                assert other_root is not None
                other_label = other.widget_for(other_session.document.by_name("caption")[0])
                assert isinstance(other_label, QLabel)
                assert _color(other_root, "Window") == fusion_window
                assert other_root.styleSheet() == root.styleSheet()
                assert _color(other_label, "WindowText") != "#ff00ff"
            del chrome
            del view
    finally:
        qapp.setPalette(saved_palette)
        qapp.setStyleSheet(saved_sheet)


def test_application_stylesheet_rules_are_tooltip_only(qapp: QApplication) -> None:
    saved = qapp.styleSheet()
    try:
        qapp.setStyleSheet("QToolTip { color: #ffffff; background-color: #000000; }")
        assert selectors_are_tooltip_only(qapp.styleSheet())
        qapp.setStyleSheet("QToolTip:disabled, QToolTip { color: #ffffff; }")
        assert selectors_are_tooltip_only(qapp.styleSheet())
        qapp.setStyleSheet("QWidget { color: red; }\nQToolTip { color: white; }")
        assert selectors_are_tooltip_only(qapp.styleSheet()) is False
    finally:
        qapp.setStyleSheet(saved)
