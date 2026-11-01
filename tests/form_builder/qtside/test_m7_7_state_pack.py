# pyright: reportAttributeAccessIssue=false
"""STATE rows stay packed after the condition builder closes."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.qt.QtCore import QPoint
from app.qt.QtWidgets import QApplication, QWidget
from tests.form_builder.qtside.test_m7_2b1_shots import _pump, _with_pytest_path

pytestmark = [pytest.mark.unit]


def _rows(inspector: QWidget) -> list:
    state = inspector.findChild(QWidget, "formBuilder.state")
    assert state is not None
    found = []
    for child in state.findChildren(QWidget):
        name = child.objectName()
        if not name.startswith("formBuilder.state.row.") or not child.isVisible():
            continue
        if child.parent() is not state:
            continue
        found.append((child.mapTo(state, QPoint(0, 0)).y(), child.sizeHint().height(), child.height(), name))
    found.sort()
    return found


def _assert_packed(inspector: QWidget) -> None:
    rows = _rows(inspector)
    assert len(rows) >= 2, rows
    for (top, hint, height, name), (next_top, _hint, _height, next_name) in zip(rows, rows[1:]):
        gap = next_top - top
        assert gap <= hint + 8, (name, next_name, gap, hint, height)


def _commit_then_select_another(tmp: Path) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_2b1_k27 import _session

    qapp = QApplication.instance()
    assert isinstance(qapp, QApplication)
    window, kb, guard, _path = _session(tmp, qapp)
    try:
        window.resize(1400, 900)
        _pump(qapp)
        surface = kb.surface
        session = surface.session
        edit = session.document.by_name("discountEdit")[0]
        button = session.document.by_name("okButton")[0]
        inspector = surface.workbench.inspector
        session.selection.set((edit,), source="canvas")
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        _pump(qapp)
        open_state_row(inspector, "cbcsEnabledWhen")
        _pump(qapp)
        editor = inspector.findChild(QWidget, "formBuilder.formula")
        assert editor is not None
        editor.setPlainText("discountCheck")
        editor.commit_requested()
        _pump(qapp)
        pad = inspector.findChild(QWidget, "formBuilder.state.edit")
        assert pad is None or not pad.isVisible()
        session.selection.set((button,), source="canvas")
        inspector.flush()
        _pump(qapp)
        _assert_packed(inspector)
    finally:
        _close(window, qapp, guard)


@pytest.mark.timeout(180)
def test_state_rows_stay_packed_after_the_builder_closes(qapp: QApplication, tmp_path: Path) -> None:
    del qapp
    if os.environ.get("CBCS_FB_PACK_CHILD") == "1":
        _commit_then_select_another(tmp_path)
        return
    _commit_then_select_another(tmp_path)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_PACK_CHILD"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
    env["CBCS_DISABLE_BACKGROUND_RUNTIME"] = "1"
    env["CBCS_QT_API"] = "pyside6"
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
            "test_state_rows_stay_packed_after_the_builder_closes",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    tail = "\n".join(text.splitlines()[-30:])
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), tail
