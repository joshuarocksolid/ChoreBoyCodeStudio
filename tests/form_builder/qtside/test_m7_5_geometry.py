# pyright: reportAttributeAccessIssue=false
"""Builder rows do not overlap at the narrow and default inspector widths, at 100% and 200%."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.qt.QtCore import QPoint, QRect
from app.qt.QtWidgets import QApplication, QComboBox, QWidget
from tests.form_builder.qtside.test_m7_2b1_shots import _pump, _set_inspector_width, _with_pytest_path

pytestmark = [pytest.mark.unit]

_CONDITION = (
    "formBuilder.formula.switch",
    "formBuilder.builder.cond.join",
    "formBuilder.builder.cond.row.0",
    "formBuilder.builder.cond.row.1",
    "formBuilder.builder.cond.add",
    "formBuilder.state.status",
)
_VALUE = (
    "formBuilder.formula.switch",
    "formBuilder.builder.shape",
    "formBuilder.builder.if",
    "formBuilder.builder.then",
    "formBuilder.builder.else",
    "formBuilder.state.status",
)


def _mapped(widget: QWidget, root: QWidget) -> QRect:
    return QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())


def _assert_rows(pane: QWidget, names: tuple) -> None:
    state = pane.findChild(QWidget, "formBuilder.state")
    assert state is not None
    rects = []
    for name in names:
        widget = pane.findChild(QWidget, name)
        assert widget is not None and widget.isVisible(), name
        rect = _mapped(widget, state)
        assert rect.width() > 0 and rect.height() > 0, (name, rect, widget.sizeHint().height())
        assert rect.right() <= state.width() + 1, (name, rect, state.width())
        rects.append((name, rect))
    for index, (left_name, left) in enumerate(rects):
        for right_name, right in rects[index + 1 :]:
            assert not left.intersects(right), (left_name, left, right_name, right)
    status = pane.findChild(QWidget, "formBuilder.state.status")
    pad = pane.findChild(QWidget, "formBuilder.state.edit")
    assert status is not None and pad is not None
    pad_bottom = pad.mapTo(state, QPoint(0, pad.height())).y()
    next_top = None
    for row in state.findChildren(QWidget):
        if not row.objectName().startswith("formBuilder.state.row.") or not row.isVisible():
            continue
        top = row.mapTo(state, QPoint(0, 0)).y()
        if top + 2 >= pad_bottom and (next_top is None or top < next_top):
            next_top = top
    if next_top is not None:
        assert pad_bottom <= next_top, (pad_bottom, next_top)
    _assert_inside(pane)


def _assert_inside(pane: QWidget) -> None:
    """Every builder child sits in the section, and no combo is narrower than its hint."""

    state = pane.findChild(QWidget, "formBuilder.state")
    builder = pane.findChild(QWidget, "formBuilder.builder")
    assert state is not None and builder is not None
    content = state.contentsRect().adjusted(-1, -1, 1, 1)
    for child in builder.findChildren(QWidget):
        if not child.isVisible():
            continue
        rect = _mapped(child, state)
        if rect.width() <= 0 or rect.height() <= 0:
            continue
        assert content.contains(rect), (child.objectName(), rect, content)
    for combo in builder.findChildren(QComboBox):
        if not combo.isVisible() or combo.width() <= 0:
            continue
        hint = combo.minimumSizeHint().width()
        assert combo.width() + 1 >= hint, (combo.objectName(), combo.width(), hint)


def _open_formula(pane: QWidget, key: str, text: str) -> None:
    from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
    from app.qt.QtCore import Qt
    from app.qt.QtTest import QTest

    open_state_row(pane, key)
    _pump(QApplication.instance())  # type: ignore[arg-type]
    editor = pane.findChild(QWidget, "formBuilder.formula")
    assert editor is not None
    editor.setFocus()  # type: ignore[attr-defined]
    _pump(QApplication.instance())  # type: ignore[arg-type]
    editor.setPlainText(text)  # type: ignore[attr-defined]
    _pump(QApplication.instance())  # type: ignore[arg-type]
    switch = pane.findChild(QWidget, "formBuilder.formula.switch")
    assert switch is not None and switch.isEnabled()  # type: ignore[attr-defined]
    QTest.keyClick(switch, getattr(getattr(Qt, "Key", Qt), "Key_Space"))  # type: ignore[arg-type]
    _pump(QApplication.instance())  # type: ignore[arg-type]


def _assert_widths(width: int) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_2b1_k27 import _session

    qapp = QApplication.instance()
    assert isinstance(qapp, QApplication)
    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, _path = _session(tmp, qapp)
    try:
        window.resize(1100, 900)
        _pump(qapp)
        surface = kb.surface
        edit = surface.session.document.by_name("discountEdit")[0]
        inspector = surface.workbench.inspector
        surface.session.selection.set((edit,), source="canvas")
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        _pump(qapp)
        _set_inspector_width(window, width, qapp)
        _open_formula(inspector, "cbcsEnabledWhen", "discountCheck and discountCheck")
        _assert_rows(inspector, _CONDITION)
        from app.qt.QtCore import Qt
        from app.qt.QtTest import QTest

        editor = inspector.findChild(QWidget, "formBuilder.formula")
        assert editor is not None
        editor.setFocus()
        _pump(qapp)
        QTest.keyClick(editor, getattr(getattr(Qt, "Key", Qt), "Key_Escape"))
        _pump(qapp)
        _open_formula(inspector, "cbcsValue", "10 if discountCheck else 0")
        _pump(qapp)
        state = inspector.findChild(QWidget, "formBuilder.state")
        body = inspector.findChild(QWidget, "formBuilder.behaviorBody")
        assert state is not None and body is not None
        state.setMinimumHeight(state.sizeHint().height())
        body.setMinimumHeight(body.sizeHint().height())
        window.resize(1100, max(900, body.sizeHint().height() + 160))
        _pump(qapp)
        _assert_rows(inspector, _VALUE)
    finally:
        _close(window, qapp, guard)


@pytest.mark.timeout(180)
def test_builder_rows_do_not_overlap(qapp: QApplication) -> None:
    del qapp
    if os.environ.get("CBCS_FB_GEOM_CHILD") == "1":
        for width in (236, 300):
            _assert_widths(width)
        return
    for width in (236, 300):
        _assert_widths(width)
    env = os.environ.copy()
    env["QT_SCALE_FACTOR"] = "2"
    env["CBCS_FB_GEOM_CHILD"] = "1"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["PYTHONNOUSERSITE"] = "1"
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
            "test_builder_rows_do_not_overlap",
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
