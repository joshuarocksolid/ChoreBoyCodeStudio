# pyright: reportAttributeAccessIssue=false
"""High-contrast workbench grabs at 100% and 200%.

Skips unless CBCS_FB_SCREENSHOT_DIR is set. The 200% files come from a
child process with QT_SCALE_FACTOR=2.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtWidgets import QApplication, QWidget

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)


def _pump(qapp: QApplication) -> None:
    for _ in range(6):
        qapp.processEvents()


def _grab(widget: QWidget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _theme(window: QWidget, mode: str, qapp: QApplication) -> None:
    window._theme_mode = mode  # type: ignore[attr-defined]
    window._shell_theme_workflow.apply_theme_styles()  # type: ignore[attr-defined]
    _pump(qapp)


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_8a_panel import open_invoice

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, surface, guard = open_invoice(tmp, qapp)
    try:
        window.resize(1400, 900)
        _pump(qapp)
        logic = surface.findChild(QWidget, "formBuilder.logic")
        assert logic is not None
        field = logic.findChild(QWidget, "formBuilder.logic.filter")
        assert field is not None
        splitter = window.findChild(QWidget, "formBuilder.splitter")
        assert splitter is not None
        for mode in _MODES:
            _theme(window, mode, qapp)
            field.setFocus()
            _pump(qapp)
            _grab(logic, folder / ("logic-filter-%s-%s.png" % (mode, scale)))
            _grab(splitter, folder / ("workbench-%s-%s.png" % (mode, scale)))
    finally:
        _close(window, qapp, guard)


@pytest.mark.timeout(300)
def test_m9_3_shots(qapp: QApplication, tmp_path: Path) -> None:
    del tmp_path
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
            "--timeout",
            "300",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_m9_3_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
