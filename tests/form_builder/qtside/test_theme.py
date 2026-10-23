# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false
"""The realized form keeps the Fusion runtime look when the shell theme changes."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from app.core import constants
from app.qt.QtGui import QColor, QPalette  # type: ignore[reportAttributeAccessIssue]
from app.qt.QtWidgets import QApplication, QLabel, QMainWindow
from app.features.form_builder.qtside.theme.runtime import host_form, selectors_are_tooltip_only
from app.shell.style_sheet import build_shell_style_sheet
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.support import form, opened, run_module

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
    reference = _bare_reference()
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
            scene = view.scene()
            assert scene is not None
            window = QMainWindow()
            window.setCentralWidget(view)
            window.show()
            qapp.processEvents()
            window_role = _role("Window")
            text_role = _role("WindowText")
            modes = (
                constants.UI_THEME_MODE_DARK,
                constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
                constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
            )
            for mode in modes:
                tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
                themed = QPalette(saved_palette)
                themed.setColor(window_role, QColor(tokens.window_bg))
                themed.setColor(text_role, QColor(tokens.text_primary))
                qapp.setPalette(themed)
                window.setStyleSheet(build_shell_style_sheet(tokens))
                qapp.processEvents()
                assert scene.palette().color(window_role).name() == reference["scene_window"]
                assert scene.palette().color(text_role).name() == reference["scene_text"]
                assert _color(label, "Window") == reference["label_window"]
                assert _color(label, "WindowText") == reference["label_text"]
                assert _color(root, "Window") == reference["root_window"]
                assert root.styleSheet() == "QLabel#caption { color: #123456; }"
                if mode == constants.UI_THEME_MODE_HIGH_CONTRAST_DARK:
                    assert tokens.text_primary.lower() != reference["label_text"].lower()
            del window
            del view
    finally:
        qapp.setPalette(saved_palette)
        qapp.setStyleSheet(saved_sheet)


def _bare_reference() -> dict:
    """Colors from a form realized in a bare QApplication, in a subprocess."""
    with tempfile.NamedTemporaryFile("w", suffix=".ui", delete=False, encoding="utf-8") as handle:
        handle.write(_FORM)
        path = handle.name
    try:
        proc = run_module("tests.form_builder.qtside.tools.bare_palette", [path])
    finally:
        os.unlink(path)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


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
