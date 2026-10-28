# pyright: reportAttributeAccessIssue=false
"""Inspector shots for text, lists and custom properties. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtGui import QPalette
from app.qt.QtWidgets import QApplication, QCheckBox, QLineEdit, QScrollArea, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m43d_text import (
    _LABEL,
    _LIST,
    _close,
    _expand_all,
    _pane,
    _select,
    _settle,
)

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    qapp.processEvents()
    image = widget.grab()
    image.save(str(folder / (stem + ".png")))


def _reveal(qapp: QApplication, pane: QWidget, widget: QWidget) -> None:
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    if scroll is not None:
        scroll.ensureWidgetVisible(widget)
    qapp.processEvents()


def _open_popover(window: QWidget) -> QWidget:
    visible = [
        item
        for item in window.findChildren(QWidget, "formBuilder.rowPopover")
        if item.isVisible()
    ]
    assert visible, "no open row popover"
    return visible[-1]


def _fit(qapp: QApplication, window: QWidget, pane: QWidget, row_target: int) -> None:
    """Size the window so the inspector row is ``row_target`` px. From the reviewer's gate script."""
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    assert scroll is not None
    width = row_target + 60
    for _ in range(30):
        window.resize(width, 900)
        _settle(qapp, pane)
        row = scroll.viewport().width() - 16
        if row == row_target:
            return
        width += row_target - row


@pytest.mark.timeout(300)
def test_m43d_shots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, "200")
        return
    _shoot(qapp, folder, "100")
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [
            sys.executable,
            "-s",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m43d_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _shoot(qapp: QApplication, folder: Path, suffix: str) -> None:
    for mode in _MODES:
        for width in (236, 320):
            tokens = tokens_from_palette(QPalette(), force_mode=mode)
            window, pane, session, realizer = _pane(qapp, _LABEL)
            try:
                pane.apply_chrome(chrome_for(tokens))
                _select(session, "titleLabel")
                _settle(qapp, pane)
                _fit(qapp, window, pane, width)
                row = pane.findChild(QWidget, "formBuilder.row.text")
                assert row is not None
                toggle = row.findChild(QWidget, "formBuilder.translationToggle")
                assert toggle is not None
                toggle.click()
                box = row.findChild(QCheckBox)
                assert box is not None
                box.click()
                qapp.processEvents()
                tag = "%s-%s-%s-%d" % ("text-translation", mode, suffix, width)
                _grab(qapp, pane, folder, tag)
                _select(session, "richLabel")
                _settle(qapp, pane)
                rich = pane.findChild(QWidget, "formBuilder.row.text")
                assert rich is not None
                summary = rich.findChild(QWidget, "formBuilder.summary")
                assert summary is not None
                summary.click()
                qapp.processEvents()
                popover = _open_popover(window)
                _grab(qapp, popover, folder, "rich-text-%s-%s-%d" % (mode, suffix, width))
                source = next(
                    item for item in popover.findChildren(QWidget) if item.accessibleName() == "Source"
                )
                source.click()
                qapp.processEvents()
                _grab(qapp, popover, folder, "rich-text-source-%s-%s-%d" % (mode, suffix, width))
                done = popover.findChild(QWidget, "formBuilder.popoverDone")
                assert done is not None
                done.click()
                qapp.processEvents()
                pane.set_group_expanded(GroupId.ALL, True)
                _settle(qapp, pane)
                menu = pane.findChild(QWidget, "formBuilder.inspectorMenu")
                assert menu is not None and menu.menu() is not None
                sort = next(action for action in menu.menu().actions() if "Sort" in action.text())
                sort.setChecked(True)
                _settle(qapp, pane)
                hints = pane.findChild(QWidget, "formBuilder.row.inputMethodHints")
                if hints is not None:
                    _reveal(qapp, pane, hints)
                _grab(qapp, pane, folder, "all-props-sorted-%s-%s-%d" % (mode, suffix, width))
                tip = pane.findChild(QWidget, "formBuilder.row.toolTip")
                if tip is not None:
                    button = tip.findChild(QWidget, "formBuilder.summary")
                    if button is not None:
                        button.click()
                        qapp.processEvents()
                        _grab(
                            qapp,
                            _open_popover(window),
                            folder,
                            "multiline-text-%s-%s-%d" % (mode, suffix, width),
                        )
            finally:
                _close(window, pane, realizer, session, qapp)
            window, pane, session, realizer = _pane(qapp, _LIST)
            try:
                pane.apply_chrome(chrome_for(tokens))
                _select(session, "Form")
                _expand_all(qapp, pane)
                _fit(qapp, window, pane, width)
                row = pane.findChild(QWidget, "formBuilder.row.tags")
                assert row is not None
                button = row.findChild(QWidget, "formBuilder.summary")
                assert button is not None
                button.click()
                qapp.processEvents()
                popover = _open_popover(window)
                _grab(qapp, popover, folder, "stringlist-popover-%s-%s-%d" % (mode, suffix, width))
                done = popover.findChild(QWidget, "formBuilder.popoverDone")
                if done is not None:
                    done.click()
                add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
                assert add is not None
                add.click()
                qapp.processEvents()
                name = next(
                    item
                    for item in pane.findChildren(QLineEdit)
                    if item.accessibleName() == "Custom property name"
                )
                name.setText("requiredRole")
                name.returnPressed.emit()
                qapp.processEvents()
                created = pane.findChild(QWidget, "formBuilder.row.requiredRole")
                if created is not None:
                    _reveal(qapp, pane, created)
                else:
                    _reveal(qapp, pane, name)
                _grab(qapp, pane, folder, "custom-props-%s-%s-%d" % (mode, suffix, width))
                add.click()
                qapp.processEvents()
                name = next(
                    item
                    for item in pane.findChildren(QLineEdit)
                    if item.accessibleName() == "Custom property name"
                )
                name.setText("2nd")
                name.returnPressed.emit()
                qapp.processEvents()
                form = pane.findChild(QWidget, "formBuilder.customProperties")
                error = (
                    form.findChild(QWidget, "formBuilder.rowError") if form is not None else None
                )
                _reveal(qapp, pane, error if error is not None else name)
                _grab(qapp, pane, folder, "custom-prop-add-error-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
        if mode in (
            constants.UI_THEME_MODE_LIGHT,
            constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
        ):
            _shoot_states(qapp, folder, mode, suffix)


_STATE_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QLabel" name="plainLabel">
     <property name="text"><string>One</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="otherLabel">
     <property name="text"><string>Two</string></property>
     <property name="toolTip"><string>Other</string></property>
    </widget>
   </item>
  </layout>
 </widget>
</ui>
"""


def _shoot_states(qapp: QApplication, folder: Path, mode: str, suffix: str) -> None:
    tokens = tokens_from_palette(QPalette(), force_mode=mode)
    window, pane, session, realizer = _pane(qapp, _STATE_FORM)
    try:
        pane.apply_chrome(chrome_for(tokens))
        _select(session, "plainLabel")
        _settle(qapp, pane)
        _fit(qapp, window, pane, 320)
        row = pane.findChild(QWidget, "formBuilder.row.toolTip")
        assert row is not None
        button = row.findChild(QWidget, "formBuilder.summary")
        assert button is not None
        button.click()
        qapp.processEvents()
        popover = _open_popover(window)
        _grab(qapp, popover, folder, "popover-unset-%s-%s-320" % (mode, suffix))
        done = popover.findChild(QWidget, "formBuilder.popoverDone")
        if done is not None:
            done.click()
        _select(session, "plainLabel", "otherLabel")
        _settle(qapp, pane)
        row = pane.findChild(QWidget, "formBuilder.row.toolTip")
        if row is not None:
            button = row.findChild(QWidget, "formBuilder.summary")
            if button is not None:
                button.click()
                qapp.processEvents()
                _grab(
                    qapp,
                    _open_popover(window),
                    folder,
                    "popover-mixed-%s-%s-320" % (mode, suffix),
                )
    finally:
        _close(window, pane, realizer, session, qapp)

