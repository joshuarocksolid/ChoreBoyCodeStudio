# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportOptionalMemberAccess=false
"""Preview with the real invoice form, four themes at 100% and 200%.

Skips unless CBCS_FB_SCREENSHOT_DIR is set (UX §13.4.9).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.features.form_builder.engine.ipc.protocol import Appearance, TryStart, encode_frame
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.preview.child.session import ChildSession
from app.features.form_builder.integration.preview_notice import preview_request
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QTreeWidget, QWidget
from app.shell.theme_tokens import tokens_from_palette
from app.features.form_builder.engine.logic.checks import Preset, write_checks
from app.features.form_builder.engine.logic.events_codec import EventStep, call_step, write_list
from tests.form_builder.qtside.test_m7_6_try import (
    _Session,
    _Writer,
    _prop,
    _scope,
    _window_text,
)

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)
_EMAIL = "Enter an email address like name@example.com"


def _field(class_name: str, name: str, body: str) -> str:
    return '<widget class="%s" name="%s">%s</widget>' % (class_name, name, body)


def _label(name: str, text: str, buddy: str = "") -> str:
    buddy_xml = ('<property name="buddy"><cstring>%s</cstring></property>' % buddy) if buddy else ""
    return _field(
        "QLabel",
        name,
        '<property name="text"><string>%s</string></property>%s' % (text, buddy_xml),
    )


def _row(row: int, label: str, field: str) -> str:
    return (
        '<item row="%d" column="0">%s</item><item row="%d" column="1">%s</item>'
        % (row, label, row, field)
    )


def _shot_text() -> str:
    """One form: Discount, Discount rate, Qty, Price, Line total, Email, Save.

    Rows sit together. Spare space is below Save, which is sized to its text.
    """

    checks = write_checks((Preset("email", None),))
    assert checks is not None
    steps = write_list((EventStep("validate"), call_step("save_invoice")))
    rows = (
        _row(0, _label("discountLabel", "Discount"), _field(
            "QCheckBox", "discountCheck", '<property name="text"><string></string></property>',
        )),
        _row(1, _label("discountRateLabel", "Discount rate", "discountEdit"), _field(
            "QLineEdit", "discountEdit", _prop("cbcsEnabledWhen", "discountCheck"),
        )),
        _row(2, _label("qtyLabel", "Qty"), _field("QSpinBox", "qtySpin", "")),
        _row(3, _label("priceLabel", "Price"), _field(
            "QDoubleSpinBox", "priceSpin", '<property name="decimals"><number>2</number></property>',
        )),
        _row(4, _label("lineTotalName", "Line total", "lineTotalLabel"), _field(
            "QLabel", "lineTotalLabel", _prop("cbcsValue", "qtySpin * priceSpin") + _prop("cbcsFormat", "money"),
        )),
        _row(5, _label("emailLabel", "Email"), _field(
            "QLineEdit", "emailEdit", _prop("cbcsValidate", checks) + _prop("cbcsErrorLabel", "emailError"),
        )),
        '<item row="6" column="0" colspan="2">%s</item>' % _field(
            "QLabel", "emailError", '<property name="text"><string></string></property>',
        ),
    )
    save = _field("QPushButton", "saveButton", '<property name="text"><string>Save</string></property>' + _prop("cbcsOnClicked", steps))
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Invoice</class>
 <widget class="QDialog" name="Invoice">
  <property name="geometry"><rect><x>0</x><y>0</y><width>360</width><height>280</height></rect></property>
  <property name="windowTitle"><string>Invoice</string></property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QFormLayout" name="formLayout">
     %s
    </layout>
   </item>
   <item>
    <layout class="QHBoxLayout" name="saveRow">
     <item><spacer name="saveSpacer"><property name="orientation"><enum>Qt::Horizontal</enum></property><property name="sizeHint" stdset="0"><size><width>40</width><height>20</height></size></property></spacer></item>
     <item>%s</item>
    </layout>
   </item>
   <item><spacer name="belowSpacer"><property name="orientation"><enum>Qt::Vertical</enum></property><property name="sizeHint" stdset="0"><size><width>20</width><height>40</height></size></property></spacer></item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
""" % ("".join(rows), save)


def _live(qapp: QApplication, tmp_path: Path) -> tuple:
    writer = _Writer()
    child = ChildSession(writer, qapp)
    document, scope, path = _scope(tmp_path, _shot_text())
    Path(scope.window_path).write_text(
        _window_text("\n    def note(self) -> str:\n        return ''\n"),
        encoding="utf-8",
    )
    message = preview_request(
        _Session(document, scope),
        str(path),
        "v1",
        run_behavior=True,
        appearance=Appearance(title="Preview · invoice"),
    )
    assert isinstance(message, TryStart)
    child._handle_line(encode_frame(message))  # noqa: SLF001
    qapp.processEvents()
    shell = child._views["v1"].widget  # noqa: SLF001
    check = shell.findChild(QWidget, "discountCheck")
    qty = shell.findChild(QWidget, "qtySpin")
    price = shell.findChild(QWidget, "priceSpin")
    email = shell.findChild(QLineEdit, "emailEdit")
    save = shell.findChild(QWidget, "saveButton")
    assert check is not None and email is not None and save is not None
    check.setChecked(True)  # type: ignore[attr-defined]
    qty.setValue(2)  # type: ignore[attr-defined]
    price.setValue(3)  # type: ignore[attr-defined]
    qapp.processEvents()
    email.setText("not-an-email")
    email.editingFinished.emit()
    qapp.processEvents()
    save.click()  # type: ignore[attr-defined]
    qapp.processEvents()
    note = shell.findChild(QLineEdit, "preview.windowValue.note")
    if note is not None:
        note.setText("shop")
        qapp.processEvents()
    tree = shell.findChild(QTreeWidget, "preview.whatRan.list")
    if tree is not None:
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            if item.childCount():
                item.setExpanded(True)
                break
    total = shell.findChild(QLabel, "lineTotalLabel")
    error = shell.findChild(QLabel, "emailError")
    assert total is not None and total.text() == "$6.00"
    assert error is not None and error.text() == _EMAIL
    discount = shell.findChild(QWidget, "discountEdit")
    assert discount is not None and discount.isEnabled()
    labels = []
    if tree is not None:
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            labels.append(item.text(1))
            for child_index in range(item.childCount()):
                labels.append(item.child(child_index).text(1))
    shown = "\n".join(labels)
    assert "Discount rate · Enabled when" in shown
    assert "discount edit" not in shown
    shell.resize(1100, 680)
    shell._splitter.setSizes([420, 680])  # noqa: SLF001
    shell.show()
    qapp.processEvents()
    return child, shell


def _shoot(qapp: QApplication, folder: Path, scale: str, tmp_path: Path) -> None:
    before_path = list(sys.path)
    before_modules = dict(sys.modules)
    child, shell = _live(qapp, tmp_path)
    try:
        for mode in _MODES:
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            shell.apply_chrome(chrome_for(tokens))
            qapp.processEvents()
            path = folder / ("preview-what-ran-%s-%s.png" % (mode, scale))
            path.parent.mkdir(parents=True, exist_ok=True)
            shell.grab().save(str(path))
    finally:
        for view_id in list(child._views):  # noqa: SLF001
            widget = child._views.pop(view_id).widget  # noqa: SLF001
            widget.hide()
            widget.deleteLater()
        qapp.processEvents()
        qapp.removeEventFilter(child._user_close)  # noqa: SLF001
        sys.path[:] = before_path
        for name in list(sys.modules):
            if name not in before_modules:
                sys.modules.pop(name, None)
        for name, module in before_modules.items():
            sys.modules[name] = module


@pytest.mark.timeout(180)
def test_m7_6_preview_shots(qapp: QApplication, tmp_path: Path) -> None:
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
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
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
            "test_m7_6_preview_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
