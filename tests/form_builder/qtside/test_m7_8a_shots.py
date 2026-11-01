# pyright: reportAttributeAccessIssue=false
"""Logic panel and Uses shots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import cast

import pytest

from app.qt.QtWidgets import QApplication, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m7_2b1_shots import _MODES, _grab, _pump, _with_pytest_path
from tests.form_builder.qtside.test_m7_8a_panel import open_invoice

pytestmark = pytest.mark.unit


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from app.features.form_builder.engine.query.selection import SelectionSource
    from app.features.form_builder.qtside.logic_panel.open import show_uses
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, surface, guard = open_invoice(tmp, qapp)
    try:
        node = surface.session.document.by_name("discountEdit")[0]  # type: ignore[attr-defined]
        surface.session.selection.set((node,), current=node, source=SelectionSource.PROGRAM)  # type: ignore[attr-defined]
        panel = surface.findChild(QWidget, "formBuilder.logic")  # type: ignore[attr-defined]
        assert panel is not None
        for mode in _MODES:
            tokens = tokens_from_palette(qapp.palette(), force_mode=mode)
            surface.apply_theme(tokens)  # type: ignore[attr-defined]
            _pump(qapp)
            checks = panel.findChild(QWidget, "formBuilder.logic.chip.checks")
            assert checks is not None
            checks.setChecked(False)  # type: ignore[attr-defined]
            _pump(qapp)
            panel.setFixedWidth(320)
            panel.setFixedHeight(860)
            _pump(qapp)
            _grab(panel, folder / ("logic-filled-%s-%s.png" % (mode, scale)))
            panel.setFixedWidth(184)
            panel.setFixedHeight(980)
            _pump(qapp)
            _grab(panel, folder / ("logic-filled-%s-%s-184.png" % (mode, scale)))
            panel.setMinimumWidth(0)
            panel.setMaximumWidth(16777215)
            show_uses(surface)
            _pump(qapp)
            found = getattr(surface, "_logic_uses", None)
            assert isinstance(found, QWidget)
            dialog = cast(QWidget, found)
            dialog.setMinimumWidth(0)
            dialog.setMaximumWidth(16777215)
            dialog.resize(420, 280)
            _pump(qapp)
            _grab(dialog, folder / ("logic-uses-%s-%s.png" % (mode, scale)))
            dialog.setFixedWidth(184)
            _pump(qapp)
            _grab(dialog, folder / ("logic-uses-%s-%s-184.png" % (mode, scale)))
            dialog.close()
    finally:
        _close(window, qapp, guard)


@pytest.mark.timeout(300)
def test_m7_8a_shots(qapp: QApplication) -> None:
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
            "test_m7_8a_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
