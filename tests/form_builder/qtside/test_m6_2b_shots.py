# pyright: reportAttributeAccessIssue=false
"""Screenshots of the M6.2b code states.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. 100% is this process. 200% is a
child with QT_SCALE_FACTOR=2. Inspector states are also grabbed at 236 px.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtWidgets import QApplication, QCheckBox, QLabel, QMessageBox, QVBoxLayout, QWidget
from app.shell.theme_tokens import tokens_from_palette

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)
_INSPECTOR = (
    "method-page",
    "method-page-bad-name",
    "your-methods",
    "events-by-name",
    "form-settings",
    "problems-fb201",
    "code-017",
)


def _pump(qapp: QApplication, times: int = 4) -> None:
    for _ in range(times):
        qapp.processEvents()


def _sheet(tokens: object) -> str:
    return (
        "QWidget { background: %s; color: %s; }"
        "QLabel { background: transparent; color: %s; }"
        "QCheckBox { color: %s; }"
        % (tokens.panel_bg, tokens.text_primary, tokens.text_primary, tokens.text_primary)  # type: ignore[attr-defined]
    )


def _host(qapp: QApplication, mode: str, width: int) -> tuple:
    tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
    host = QWidget()
    host.setStyleSheet(_sheet(tokens))
    column = QVBoxLayout(host)
    host.resize(width, 280)
    return host, column, tokens


def _label(parent: QWidget, text: str, color: str) -> QLabel:
    label = QLabel(text, parent)
    label.setWordWrap(True)
    label.setStyleSheet("color: %s; background: transparent;" % color)
    return label


def _fill(host: QWidget, column: QVBoxLayout, tokens: object, state: str) -> None:
    if state == "method-page":
        column.addWidget(_label(host, "print_receipt", tokens.text_primary))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "Adds print_receipt() to SaleWindow in sale_window.py.", tokens.text_muted))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "METHODS IN sale_window.py", tokens.text_muted))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "show_total()", tokens.text_primary))  # type: ignore[attr-defined]
    elif state == "method-page-bad-name":
        column.addWidget(_label(host, "close", tokens.text_primary))  # type: ignore[attr-defined]
        column.addWidget(
            _label(
                host,
                "close is a method of QDialog, so it would replace it. Try close_sale.",
                tokens.diag_error_color,  # type: ignore[attr-defined]
            )
        )
    elif state == "your-methods":
        column.addWidget(_label(host, "YOUR METHODS · sale_window.py", tokens.text_muted))  # type: ignore[attr-defined]
        column.addWidget(
            _label(
                host,
                "Code Studio adds methods to sale_window.py and never changes the rest of it.",
                tokens.text_muted,  # type: ignore[attr-defined]
            )
        )
        column.addWidget(_label(host, "print_receipt() · Print receipt clicked · line 42", tokens.text_primary))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "close_shift() · not used · line 60", tokens.text_primary))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "export_day() · not in sale_window.py", tokens.diag_warning_color))  # type: ignore[attr-defined]
    elif state == "events-by-name":
        column.addWidget(_label(host, "When clicked", tokens.text_primary))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "on_printButton_clicked() runs by its name", tokens.text_primary))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "sale_window.py:18", tokens.accent))  # type: ignore[attr-defined]
    elif state == "form-settings":
        box = QCheckBox("Connect methods by name", host)
        box.setObjectName("formBuilder.formSetting.connectslotsbyname.check")
        box.setChecked(True)
        column.addWidget(box)
        column.addWidget(
            _label(
                host,
                "Methods named on_{widget}_{event} with @Slot run without a step. "
                "Qt Designer calls this Connect slots by name.",
                tokens.text_muted,  # type: ignore[attr-defined]
            )
        )
    elif state == "problems-fb201":
        column.addWidget(_label(host, "FB201  print_receipt() is not in sale_window.py.", tokens.diag_error_color))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "Create method    Use print_receipt", tokens.accent))  # type: ignore[attr-defined]
    elif state == "code-017":
        column.addWidget(_label(host, "This form isn't in a project, so it has no window file.", tokens.text_muted))  # type: ignore[attr-defined]
        column.addWidget(_label(host, "Adopt this form…", tokens.accent))  # type: ignore[attr-defined]
    elif state == "preview-would-call":
        column.addWidget(
            _label(
                host,
                "Preview: Print receipt clicked would call print_receipt() in sale_window.py.",
                tokens.text_primary,  # type: ignore[attr-defined]
            )
        )
    host.show()


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    states = _INSPECTOR + ("f5-dialog", "preview-would-call")
    for mode in _MODES:
        for state in states:
            host, column, tokens = _host(qapp, mode, 420)
            if state == "f5-dialog":
                box = QMessageBox(host)
                box.setText("Save sale_window.py before running? It has code this form calls.")
                box.addButton("Save and run", _role("AcceptRole"))
                box.addButton("Run without saving", _role("DestructiveRole"))
                box.addButton("Cancel", _role("RejectRole"))
                box.show()
                _pump(qapp)
                box.grab().save(str(folder / ("%s-%s-%s.png" % (state, mode, scale))))
                box.close()
                host.close()
                continue
            _fill(host, column, tokens, state)
            host.setFixedWidth(420)
            host.adjustSize()
            _pump(qapp)
            host.grab().save(str(folder / ("%s-%s-%s.png" % (state, mode, scale))))
            if state in _INSPECTOR:
                narrow, narrow_column, narrow_tokens = _host(qapp, mode, 236)
                _fill(narrow, narrow_column, narrow_tokens, state)
                narrow.setFixedWidth(236)
                narrow.adjustSize()
                _pump(qapp)
                narrow.grab().save(str(folder / ("%s-%s-%s-236.png" % (state, mode, scale))))
                narrow.close()
            host.close()


def _role(name: str) -> object:
    nested = getattr(QMessageBox, "ButtonRole", None)
    if nested is not None and hasattr(nested, name):
        return getattr(nested, name)
    return getattr(QMessageBox, name)


@pytest.mark.timeout(300)
def test_m6_2b_shots(qapp: QApplication) -> None:
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
            "test_m6_2b_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
