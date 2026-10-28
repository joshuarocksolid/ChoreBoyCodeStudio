# pyright: reportAttributeAccessIssue=false
"""Inspector shots for text, lists and custom properties. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtGui import QPalette
from app.qt.QtWidgets import QApplication, QCheckBox, QLineEdit, QWidget
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


def test_m43d_shots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    base = qapp.font()
    base_size = base.pointSize() if base.pointSize() > 0 else 13
    try:
        for mode in _MODES:
            for scale, suffix in ((1, "100"), (2, "200")):
                font = qapp.font()
                font.setPointSize(base_size * scale)
                qapp.setFont(font)
                for width in (236, 320):
                    tokens = tokens_from_palette(QPalette(), force_mode=mode)
                    window, pane, session, realizer = _pane(qapp, _LABEL)
                    try:
                        pane.apply_chrome(chrome_for(tokens))
                        window.resize(width, 640)
                        _select(session, "titleLabel")
                        _settle(qapp, pane)
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
                        popover = window.findChild(QWidget, "formBuilder.rowPopover")
                        assert popover is not None
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
                        _grab(qapp, pane, folder, "all-props-sorted-%s-%s-%d" % (mode, suffix, width))
                        tip = pane.findChild(QWidget, "formBuilder.row.toolTip")
                        if tip is not None:
                            button = tip.findChild(QWidget, "formBuilder.summary")
                            if button is not None:
                                button.click()
                                qapp.processEvents()
                                multi = window.findChild(QWidget, "formBuilder.rowPopover")
                                if multi is not None:
                                    _grab(
                                        qapp,
                                        multi,
                                        folder,
                                        "multiline-text-%s-%s-%d" % (mode, suffix, width),
                                    )
                    finally:
                        _close(window, pane, realizer, session, qapp)
                    window, pane, session, realizer = _pane(qapp, _LIST)
                    try:
                        pane.apply_chrome(chrome_for(tokens))
                        window.resize(width, 640)
                        _select(session, "Form")
                        _expand_all(qapp, pane)
                        row = pane.findChild(QWidget, "formBuilder.row.tags")
                        assert row is not None
                        button = row.findChild(QWidget, "formBuilder.summary")
                        assert button is not None
                        button.click()
                        qapp.processEvents()
                        popover = window.findChild(QWidget, "formBuilder.rowPopover")
                        assert popover is not None
                        _grab(qapp, popover, folder, "stringlist-popover-%s-%s-%d" % (mode, suffix, width))
                        done = popover.findChild(QWidget, "formBuilder.popoverDone")
                        if done is not None:
                            done.click()
                        add = pane.findChild(QWidget, "formBuilder.addCustomProperty")
                        assert add is not None
                        add.click()
                        qapp.processEvents()
                        _grab(qapp, pane, folder, "custom-props-%s-%s-%d" % (mode, suffix, width))
                        name = next(
                            item
                            for item in pane.findChildren(QLineEdit)
                            if item.accessibleName() == "Custom property name"
                        )
                        name.setText("2nd")
                        name.returnPressed.emit()
                        qapp.processEvents()
                        _grab(qapp, pane, folder, "custom-prop-add-error-%s-%s-%d" % (mode, suffix, width))
                    finally:
                        _close(window, pane, realizer, session, qapp)
    finally:
        font = qapp.font()
        font.setPointSize(base_size)
        qapp.setFont(font)


def test_popover_state_shots(qapp: QApplication) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    text = """<?xml version="1.0" encoding="UTF-8"?>
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
    for mode in (constants.UI_THEME_MODE_LIGHT, constants.UI_THEME_MODE_HIGH_CONTRAST_DARK):
        tokens = tokens_from_palette(QPalette(), force_mode=mode)
        window, pane, session, realizer = _pane(qapp, text)
        try:
            pane.apply_chrome(chrome_for(tokens))
            window.resize(320, 480)
            _select(session, "plainLabel")
            _settle(qapp, pane)
            row = pane.findChild(QWidget, "formBuilder.row.toolTip")
            assert row is not None
            button = row.findChild(QWidget, "formBuilder.summary")
            assert button is not None
            button.click()
            qapp.processEvents()
            popover = window.findChild(QWidget, "formBuilder.rowPopover")
            assert popover is not None
            _grab(qapp, popover, folder, "popover-unset-%s" % mode)
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
                    popover = window.findChild(QWidget, "formBuilder.rowPopover")
                    if popover is not None:
                        _grab(qapp, popover, folder, "popover-mixed-%s" % mode)
        finally:
            _close(window, pane, realizer, session, qapp)
