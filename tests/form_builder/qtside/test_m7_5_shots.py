# pyright: reportAttributeAccessIssue=false
"""Builder screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtCore import Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

_FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <property name="geometry"><rect><x>0</x><y>0</y><width>420</width><height>320</height></rect></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <widget class="QCheckBox" name="discountCheck">
     <property name="text"><string>Discount</string></property>
    </widget>
   </item>
   <item>
    <widget class="QLineEdit" name="discountEdit"/>
   </item>
   <item>
    <widget class="QLabel" name="qtyLabel">
     <property name="text"><string>Qty</string></property>
     <property name="buddy"><cstring>qtySpin</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QSpinBox" name="qtySpin"/>
   </item>
   <item>
    <widget class="QLabel" name="priceLabel">
     <property name="text"><string>Price</string></property>
     <property name="buddy"><cstring>priceSpin</cstring></property>
    </widget>
   </item>
   <item>
    <widget class="QDoubleSpinBox" name="priceSpin">
     <property name="decimals"><number>2</number></property>
    </widget>
   </item>
   <item>
    <widget class="QLabel" name="lineTotalLabel">
     <property name="text"><string>Line total</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    import sys

    from app.shell.main_window import MainWindow
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close, _open, _project, _require
    from tests.form_builder.qtside.test_m7_2b1_shots import _save, _theme
    _require()
    if sys.platform == "darwin":
        from app.qt.QtGui import qt_set_sequence_auto_mnemonic

        qt_set_sequence_auto_mnemonic(True)
    tmp = Path(tempfile.mkdtemp()).resolve()
    root = tmp / "shop"
    window = MainWindow(state_root=str((tmp / "state").resolve()))
    _project(window, root)
    path = root / "forms" / "invoice.ui"
    surface = _open(window, qapp, path, _FORM)
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _NoMouse

    guard = _NoMouse()
    qapp.installEventFilter(guard)
    try:
        inspector = surface.workbench.inspector  # type: ignore[attr-defined]
        for mode in _MODES:
            _theme(window, mode, qapp)
            _show(surface, inspector, qapp, "discountEdit", "cbcsEnabledWhen", "discountCheck and discountCheck")
            state = _unfold(inspector, window, qapp)
            _save(state, window, folder, "builder-condition", mode, scale, qapp)
            _close_editor(inspector, qapp)
            _show(surface, inspector, qapp, "lineTotalLabel", "cbcsValue", "qtySpin * priceSpin")
            state = _unfold(inspector, window, qapp)
            _save(state, window, folder, "builder-value", mode, scale, qapp)
            _close_editor(inspector, qapp)
            _show(surface, inspector, qapp, "lineTotalLabel", "cbcsValue", "qtySpin * priceSpin if discountCheck else 0")
            state = _unfold(inspector, window, qapp)
            _save(state, window, folder, "builder-if", mode, scale, qapp)
            _close_editor(inspector, qapp)
    finally:
        _close(window, qapp, guard)


def _unfold(inspector: QWidget, window: QWidget, qapp: QApplication) -> QWidget:
    from tests.form_builder.qtside.test_m7_2b1_shots import _pump

    state = inspector.findChild(QWidget, "formBuilder.state")
    body = inspector.findChild(QWidget, "formBuilder.behaviorBody")
    assert state is not None and body is not None
    state.setMinimumHeight(state.sizeHint().height())
    body.setMinimumHeight(body.sizeHint().height())
    window.resize(1100, max(900, body.sizeHint().height() + 160))
    _pump(qapp)
    return state


def _show(surface: object, inspector: QWidget, qapp: QApplication, widget: str, key: str, text: str) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
    from tests.form_builder.qtside.test_m7_2b1_shots import _pump

    found = surface.session.document.by_name(widget)[0]  # type: ignore[attr-defined]
    surface.session.selection.set((found,), source="canvas")  # type: ignore[attr-defined]
    inspector.focus_tab(TabId.BEHAVIOR)  # type: ignore[attr-defined]
    inspector.flush()  # type: ignore[attr-defined]
    _pump(qapp)
    open_state_row(inspector, key)
    _pump(qapp)
    editor = inspector.findChild(QWidget, "formBuilder.formula")
    assert editor is not None
    editor.setFocus()  # type: ignore[attr-defined]
    _pump(qapp)
    editor.setPlainText(text)  # type: ignore[attr-defined]
    _pump(qapp)
    switch = inspector.findChild(QWidget, "formBuilder.formula.switch")
    assert switch is not None and switch.isEnabled()  # type: ignore[attr-defined]
    QTest.keyClick(switch, _key("Key_Space"))  # type: ignore[arg-type]
    _pump(qapp)
    builder = inspector.findChild(QWidget, "formBuilder.builder")
    assert builder is not None and builder.isVisible()


def _close_editor(inspector: QWidget, qapp: QApplication) -> None:
    from tests.form_builder.qtside.test_m7_2b1_shots import _pump

    editor = inspector.findChild(QWidget, "formBuilder.formula")
    assert editor is not None
    editor.setFocus()  # type: ignore[attr-defined]
    _pump(qapp)
    QTest.keyClick(editor, _key("Key_Escape"))
    _pump(qapp)


@pytest.mark.timeout(300)
def test_m7_5_shots(qapp: QApplication) -> None:
    from tests.form_builder.qtside.test_m7_2b1_shots import _with_pytest_path

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
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    _with_pytest_path(env)
    done = subprocess.run(
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
            "test_m7_5_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    tail = "\n".join(text.splitlines()[-20:])
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), tail
