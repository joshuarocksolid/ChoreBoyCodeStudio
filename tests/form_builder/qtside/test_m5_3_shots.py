# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportArgumentType=false
"""Screenshots of the M5.3 states (UX 12.2). Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.style import gateway
from app.qt.QtGui import QPalette
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QMenu, QScrollArea, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.inspector.test_inspector_round2 import _close, _pane, _select
from tests.unit.features.form_builder.test_workbench import _open

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Shop</class>
 <widget class="QWidget" name="Shop">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>300</height></rect></property>
  <property name="styleSheet"><string notr="true">QPushButton { background: #1A7F37; border: none; }
#cancelButton { color: #FFFFFF; }
QProgressBar { color: red; }</string></property>
  <layout class="QVBoxLayout" name="mainLayout">
   <item><widget class="QLabel" name="titleLabel"><property name="text"><string>Shop</string></property></widget></item>
   <item><widget class="QPushButton" name="okButton"><property name="text"><string>OK</string></property></widget></item>
   <item><widget class="QPushButton" name="cancelButton"><property name="text"><string>Cancel</string></property></widget></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _grab(qapp: QApplication, widget: QWidget, folder: Path, stem: str) -> None:
    qapp.processEvents()
    widget.grab().save(str(folder / (stem + ".png")))


def _fit(qapp: QApplication, window: QWidget, pane: QWidget, row_target: int) -> None:
    scroll = pane.findChild(QScrollArea, "formBuilder.inspectorScroll")
    width = row_target + 60
    for _ in range(30):
        window.resize(width, 900)
        qapp.processEvents()
        pane.flush()
        row = scroll.viewport().width() - 16
        if row == row_target:
            return
        width += row_target - row


@pytest.mark.timeout(600)
def test_m5_3_shots(qapp: QApplication, tmp_path: Path) -> None:
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
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    completed = subprocess.run(
        [sys.executable, "-s", "-m", "pytest", "-p", "no:cacheprovider", "--import-mode=importlib", "-q",
         str(Path(__file__).resolve()), "-k", "test_m5_3_shots"],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + "\n" + completed.stderr


def _shoot(qapp: QApplication, folder: Path, suffix: str, tmp_path: Path) -> None:
    for mode in _MODES:
        tokens = tokens_from_palette(QPalette(), force_mode=mode)
        for width in (236, 320):
            window, pane, session, realizer = _pane(qapp, _FORM)
            try:
                pane.apply_chrome(chrome_for(tokens))
                _select(session, "okButton")
                _fit(qapp, window, pane, width)
                pane.flush()
                _grab(qapp, pane, folder, "colour-rows-%s-%s-%d" % (mode, suffix, width))
                _select(session, "Shop")
                pane.flush()
                _fit(qapp, window, pane, width)
                _grab(qapp, pane, folder, "form-look-%s-%s-%d" % (mode, suffix, width))
            finally:
                _close(window, pane, realizer, session, qapp)
        host = QWidget()
        surface = _open(host, _FORM, tmp_path / ("shop-%s-%s.ui" % (mode, suffix)))
        host.show()
        surface.show()
        host.resize(1200, 800)
        surface.resize(1200, 800)
        surface.apply_theme(tokens)
        qapp.processEvents()
        try:
            session = surface.session
            title = session.document.by_name("titleLabel")[0]
            session.selection.set((title,), source=SelectionSource.PROGRAM)
            gateway.open_drawer(session, session.document.root.id)
            drawer = surface.workbench._under_widget
            # The caret inside the first rule: the canvas outlines OK and Cancel in ov.style_match.
            cursor = drawer.editor.textCursor()
            cursor.setPosition(5)
            drawer.editor.setTextCursor(cursor)
            drawer.editor.setFocus()
            QTest.qWait(450)
            _grab(qapp, surface, folder, "style-drawer-valid-%s-%s" % (mode, suffix))
            drawer.editor.setPlainText(drawer.editor.toPlainText().rstrip()[:-1] + "\n#okButton { color: red;")
            QTest.qWait(450)
            _grab(qapp, surface, folder, "style-drawer-error-%s-%s" % (mode, suffix))
            drawer._insert.menu().popup(drawer._insert.mapToGlobal(drawer._insert.rect().bottomLeft()))
            qapp.processEvents()
            menus = [item for item in QApplication.topLevelWidgets() if isinstance(item, QMenu) and item.isVisible()]
            if menus:
                _grab(qapp, menus[-1], folder, "style-insert-menu-%s-%s" % (mode, suffix))
                menus[-1].close()
            drawer.close_drawer()
        finally:
            surface.release()
            host.close()
