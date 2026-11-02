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
from tests.form_builder.qtside.test_m7_6_try import (
    _Session,
    _Writer,
    _invoice_text,
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


def _shot_text() -> str:
    text = _invoice_text()
    # The Logic panel's invoice names this field from its buddy. What ran uses
    # that same name, so the shot form carries the same label.
    label = (
        '<item row="6" column="0">'
        '<widget class="QLabel" name="discountRateLabel">'
        '<property name="text"><string>Discount rate</string></property>'
        '<property name="buddy"><cstring>discountEdit</cstring></property>'
        "</widget></item>"
    )
    text = text.replace('<item row="0" column="0">', label + '<item row="0" column="0">', 1)
    text = text.replace(
        '<widget class="QLineEdit" name="emailEdit">',
        '<widget class="QLineEdit" name="emailEdit">%s' % _prop("cbcsErrorLabel", "emailError"),
    )
    extra = (
        '<item row="4" column="1">'
        '<widget class="QLabel" name="emailError">'
        '<property name="text"><string></string></property>'
        "</widget></item>"
        '<item row="5" column="1">'
        '<widget class="QLabel" name="noteLabel">%s</widget></item>'
        % _prop("cbcsValue", "window.note()")
    )
    needle = '</layout>\n   </item>\n   <item>\n    <widget class="QPushButton" name="saveButton">'
    if needle not in text:
        raise AssertionError("invoice layout changed")
    return text.replace(needle, extra + needle, 1)


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
