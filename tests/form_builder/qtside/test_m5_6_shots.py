# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Screenshots of the M5.6 states (UX_SPEC 12.2): overlays, Tab order list, Buddy drop-down, keys page, F1 card.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. 100% is this process; 200% is a child with QT_SCALE_FACTOR=2.
The inspector states are 236 px wide.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.integration.widget_help import open_widget_help, show_keys_page
from app.features.form_builder.qtside.inspector.api import GroupId
from app.qt.QtWidgets import QApplication, QComboBox, QLabel, QVBoxLayout, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

SHOT_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Contact</class>
 <widget class="QWidget" name="Contact">
  <property name="geometry"><rect><x>0</x><y>0</y><width>460</width><height>260</height></rect></property>
  <layout class="QFormLayout" name="formLayout">
   <item row="0" column="0"><widget class="QLabel" name="nameLabel"><property name="text"><string>Name</string></property></widget></item>
   <item row="0" column="1"><widget class="QLineEdit" name="nameEdit"/></item>
   <item row="1" column="0"><widget class="QLabel" name="emailLabel"><property name="text"><string>Email</string></property></widget></item>
   <item row="1" column="1"><widget class="QLineEdit" name="emailEdit"/></item>
   <item row="2" column="0"><widget class="QLabel" name="phoneLabel"><property name="text"><string>Phone</string></property></widget></item>
   <item row="2" column="1"><widget class="QLineEdit" name="phoneEdit"/></item>
   <item row="3" column="0" colspan="2">
    <widget class="QDialogButtonBox" name="buttonBox">
     <property name="standardButtons"><set>QDialogButtonBox::Cancel|QDialogButtonBox::Ok</set></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _pump(qapp: QApplication) -> None:
    for _ in range(6):
        qapp.processEvents()


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    _pump(qapp)
    widget.grab().save(str(folder / (stem + ".png")))


@pytest.mark.timeout(600)
def test_m5_6_shots(qapp: QApplication, tmp_path: Path) -> None:
    raw = os.environ.get("CBCS_FB_SCREENSHOT_DIR") or ""
    if not raw:
        pytest.skip("CBCS_FB_SCREENSHOT_DIR is not set")
    folder = Path(raw)
    folder.mkdir(parents=True, exist_ok=True)
    if os.environ.get("CBCS_FB_SHOT_CHILD") == "1":
        _shoot(qapp, folder, "200", tmp_path)
        return
    _shoot(qapp, folder, "100", tmp_path)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_SHOT_CHILD"] = "1"
    env["CBCS_FB_SCREENSHOT_DIR"] = str(folder)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    done = subprocess.run(
        [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "-q",
         str(Path(__file__).resolve()), "-k", "test_m5_6_shots"],
        cwd=str(Path(__file__).resolve().parents[3]), env=env, capture_output=True, text=True,
    )
    assert done.returncode == 0, done.stdout + "\n" + done.stderr


def _status(host: QWidget, surface, tokens) -> QLabel:  # type: ignore[no-untyped-def]
    label = QLabel(host)
    label.setObjectName("shotStatus")
    label.setStyleSheet(
        "QLabel#shotStatus { background: %s; color: %s; padding: 4px 10px; border-top: 1px solid %s; }"
        % (tokens.panel_bg, tokens.text_primary, tokens.border)
    )
    host.layout().addWidget(label)
    return label


def _shoot(qapp: QApplication, folder: Path, suffix: str, tmp_path: Path) -> None:
    for mode in _MODES:
        tag = "%s-%s" % (mode, suffix)
        tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
        host = QWidget()
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        surface = _open(host, SHOT_FORM, tmp_path / ("contact-%s.ui" % tag))
        column.insertWidget(0, surface, 1)
        status = _status(host, surface, tokens)
        host.show()
        surface.show()
        surface.apply_theme(tokens)
        host.resize(1180, 640)
        _pump(qapp)
        document = surface.session.document
        modes = surface.modes
        canvas = surface.workbench.canvas
        # The Tab order overlay: two numbers given, the hover chip on the next field.
        modes.open("tab_order")
        modes.assign("phoneEdit")
        modes.assign("nameEdit")
        modes._hover = "emailEdit"
        modes._push()
        _grab(qapp, host, folder, "overlay-tab-order-%s" % tag)
        # The same overlay driven by keys: the status says what Enter will do.
        modes._hover = ""
        modes._push()
        surface.session.selection.set((document.by_name("emailEdit")[0],), source=SelectionSource.PROGRAM)
        status.setText(surface.editor_status_sentence())
        _grab(qapp, host, folder, "tab-order-overlay-keys-%s" % tag)
        modes.close()
        # The Buddies overlay: two links, one label still to pair.
        modes.open("buddies")
        modes.set_buddy(document.by_name("nameLabel")[0], "nameEdit")
        modes.set_buddy(document.by_name("emailLabel")[0], "emailEdit")
        status.setText("")
        _grab(qapp, host, folder, "overlay-buddies-%s" % tag)
        modes.start_link(document.by_name("phoneLabel")[0])
        modes._candidate = "phoneEdit"
        modes._push()
        surface.session.selection.set((document.by_name("phoneLabel")[0],), source=SelectionSource.PROGRAM)
        status.setText(surface.editor_status_sentence())
        _grab(qapp, host, folder, "buddy-overlay-keys-%s" % tag)
        modes.close()
        # The form inspector with its Tab order list, in the surface.
        surface.session.selection.set((), source=SelectionSource.PROGRAM)
        status.setText("")
        _grab(qapp, host, folder, "tab-order-list-%s" % tag)
        # F1 on the Email field, and Form designer keys filtered by "wrap".
        surface.session.selection.set((document.by_name("emailEdit")[0],), source=SelectionSource.PROGRAM)
        card = open_widget_help(surface)
        _grab(qapp, card, folder, "widget-help-card-%s" % tag)
        card.close()
        dialog = show_keys_page(surface)
        page = dialog.findChild(QWidget, "formBuilder.keysPage")
        page.filter.setText("wrap")
        _grab(qapp, dialog, folder, "keys-page-%s" % tag)
        dialog.close()
        surface.release()
        host.close()
        # The inspector alone at 236 px.
        window, pane, session2, realizer = _pane(qapp, SHOT_FORM)
        try:
            pane.apply_chrome(chrome_for(tokens))
            d2 = session2.document
            window.resize(236 + 60, 900)
            session2.selection.set((), source=SelectionSource.PROGRAM)
            _pump(qapp)
            pane.flush()
            _grab(qapp, pane, folder, "inspector-tab-order-list-236-%s" % tag)
            session2.selection.set((d2.by_name("phoneLabel")[0],), source=SelectionSource.PROGRAM)
            pane.set_group_expanded(GroupId.CONTENT, True)
            pane.flush()
            _pump(qapp)
            _grab(qapp, pane, folder, "inspector-buddy-row-236-%s" % tag)
            combo = pane.findChild(QComboBox, "formBuilder.buddyPicker")
            combo.showPopup()
            _pump(qapp)
            _grab(qapp, combo.view(), folder, "buddy-dropdown-%s" % tag)
            combo.hidePopup()
        finally:
            _close(window, pane, realizer, session2, qapp)
        del canvas
