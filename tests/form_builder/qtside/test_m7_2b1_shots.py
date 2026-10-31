# pyright: reportAttributeAccessIssue=false
"""State and formula screenshots. Skips unless CBCS_FB_SCREENSHOT_DIR is set."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.core import constants
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QWidget

pytestmark = pytest.mark.unit

_MODES = (
    constants.UI_THEME_MODE_LIGHT,
    constants.UI_THEME_MODE_DARK,
    constants.UI_THEME_MODE_HIGH_CONTRAST_LIGHT,
    constants.UI_THEME_MODE_HIGH_CONTRAST_DARK,
)

def _pump(qapp: QApplication, times: int = 6) -> None:
    for _ in range(times):
        qapp.processEvents()


def _grab(widget: QWidget, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    widget.grab().save(str(path))


def _child(root: QWidget, name: str) -> QWidget:
    found = root.findChild(QWidget, name)
    assert found is not None, name
    return found


def _theme(window: QWidget, mode: str, qapp: QApplication) -> None:
    window._theme_mode = mode  # type: ignore[attr-defined]
    window._shell_theme_workflow.apply_theme_styles()  # type: ignore[attr-defined]
    _pump(qapp)


def _set_inspector_width(window: QWidget, width: int, qapp: QApplication) -> None:
    from app.qt.QtWidgets import QSplitter

    splitter = window.findChild(QSplitter, "formBuilder.splitter")
    assert splitter is not None
    right = splitter.widget(2)
    right.setMinimumWidth(width)
    right.setMaximumWidth(width)
    sizes = splitter.sizes()
    total = sum(sizes) or splitter.width()
    left = sizes[0] if len(sizes) == 3 else 232
    splitter.setSizes([left, max(360, total - left - width), width])
    _pump(qapp)


def _clear_inspector_width(window: QWidget, qapp: QApplication) -> None:
    from app.features.form_builder.integration.layout import INSPECTOR_DEFAULT, INSPECTOR_MAX, INSPECTOR_MIN

    from app.qt.QtWidgets import QSplitter

    splitter = window.findChild(QSplitter, "formBuilder.splitter")
    assert splitter is not None
    right = splitter.widget(2)
    right.setMinimumWidth(INSPECTOR_MIN)
    right.setMaximumWidth(INSPECTOR_MAX)
    _set_inspector_width(window, INSPECTOR_DEFAULT, qapp)


def _key(name: str) -> object:
    from app.qt.QtCore import Qt

    return getattr(getattr(Qt, "Key", Qt), name)


def _shoot(qapp: QApplication, folder: Path, scale: str) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m7_2b1_k27 import _session

    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, _path = _session(tmp, qapp)
    try:
        surface = kb.surface
        edit = surface.session.document.by_name("discountEdit")[0]
        inspector = surface.workbench.inspector
        for mode in _MODES:
            _theme(window, mode, qapp)
            surface.session.selection.set((edit,), source="canvas")
            inspector.focus_tab(TabId.BEHAVIOR)
            inspector.flush()
            _pump(qapp)
            state = _child(inspector, "formBuilder.state")
            _save(state, window, folder, "state-empty", mode, scale, qapp)
            from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row

            open_state_row(inspector, "cbcsEnabledWhen")
            _pump(qapp)
            editor = _child(inspector, "formBuilder.formula")
            QTest.keyClicks(editor, "discountCheck")
            _pump(qapp)
            from app.qt.QtCore import Qt

            QTest.keyClick(editor, _key("Key_Return"), Qt.KeyboardModifier.ControlModifier)  # type: ignore[arg-type]
            _pump(qapp)
            _save(state, window, folder, "state-filled", mode, scale, qapp)
            open_state_row(inspector, "cbcsVisibleWhen")
            _pump(qapp)
            editor = _child(inspector, "formBuilder.formula")
            QTest.keyClicks(editor, "disc")
            _pump(qapp)
            _save(state, window, folder, "fx-complete", mode, scale, qapp)
            editor = _child(inspector, "formBuilder.formula")
            editor.setPlainText("missingField")
            _pump(qapp)
            _save(state, window, folder, "fx-error", mode, scale, qapp)
            QTest.keyClick(editor, _key("Key_Escape"))
            _pump(qapp)
    finally:
        from tests.form_builder.qtside.test_m3_keyboard_scripts import _close

        _close(window, qapp, guard)


def _save(state: QWidget, window: QWidget, folder: Path, slug: str, mode: str, scale: str, qapp: QApplication) -> None:
    _grab(state, folder / ("%s-%s-%s.png" % (slug, mode, scale)))
    _set_inspector_width(window, 236, qapp)
    _grab(state, folder / ("%s-%s-%s-236.png" % (slug, mode, scale)))
    _clear_inspector_width(window, qapp)


@pytest.mark.timeout(300)
def test_m7_2b1_shots(qapp: QApplication) -> None:
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
            "test_m7_2b1_shots",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), text
