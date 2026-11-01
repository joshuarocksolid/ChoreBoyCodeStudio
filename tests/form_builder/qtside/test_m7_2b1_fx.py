# pyright: reportAttributeAccessIssue=false
"""The formula field: completion, underlines, fixes, lines, commit, cancel."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Tuple

import pytest

from app.features.form_builder.engine.logic.formula import FormulaEnv, SlotKind, WidgetFacts
from app.features.form_builder.engine.logic.formula.types import TEXT
from app.features.form_builder.engine.project.window_facts import MethodFacts
from app.features.form_builder.engine.ui4.writer import write_ui
from app.features.form_builder.integration.chrome import chrome_for
from app.features.form_builder.qtside.formula.editor import FormulaEditor
from app.features.form_builder.qtside.inspector.behavior_ext.state import open_state_row
from app.qt.QtCore import QPoint, QRect, Qt
from app.qt.QtGui import QColor, QTextCharFormat
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QListWidget, QPlainTextEdit, QVBoxLayout, QWidget
from app.shell.theme_tokens import tokens_from_palette
from tests.form_builder.qtside.test_m7_2b1_shots import _with_pytest_path
from tests.form_builder.qtside.test_m7_2b1_state import _select, _stored, desk, pump

pytestmark = [pytest.mark.unit]


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _mod(name: str) -> object:
    return getattr(getattr(Qt, "KeyboardModifier", Qt), name)


def _editor(root: QWidget) -> QPlainTextEdit:
    found = root.findChild(QPlainTextEdit, "formBuilder.formula")
    assert isinstance(found, QPlainTextEdit)
    return found


def _click(widget: QWidget, key: str, *mods: str) -> None:
    value = getattr(getattr(Qt, "KeyboardModifier", Qt), "NoModifier")
    for name in mods:
        value = value | getattr(getattr(Qt, "KeyboardModifier", Qt), name)  # type: ignore[operator]
    QTest.keyClick(widget, _key(key), value)  # type: ignore[arg-type]
    pump()


def test_tab_inserts_the_object_name_and_ctrl_enter_is_one_undo(qapp: QApplication) -> None:
    del qapp
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        pump()
        editor = _editor(pane)
        if not editor.isVisible():
            editor.setFocus()
            pump()
        assert QApplication.focusWidget() is editor
        QTest.keyClicks(editor, "disc")
        pump()
        listed = pane.findChild(QListWidget, "formBuilder.formula.complete")
        assert listed is not None and listed.isVisible() and listed.count() >= 1
        assert listed.item(0).text().startswith("discountCheck  Discount  Yes or no")
        status = pane.findChild(QLabel, "formBuilder.state.status")
        state = pane.findChild(QWidget, "formBuilder.state")
        assert status is not None and state is not None and status.isVisible() and status.height() > 8
        list_top = listed.mapTo(state, QPoint(0, 0)).y()
        status_bottom = status.mapTo(state, QPoint(0, status.height())).y()
        assert list_top >= status_bottom - 2
        pane.window().resize(280, 720)
        pump()
        assert status.height() > status.fontMetrics().lineSpacing()
        list_top = listed.mapTo(state, QPoint(0, 0)).y()
        status_bottom = status.mapTo(state, QPoint(0, status.height())).y()
        assert list_top >= status_bottom - 2
        assert listed.item(0).text().startswith("discountCheck")
        _click(editor, "Key_Tab")
        assert editor.toPlainText() == "discountCheck"
        assert not listed.isVisible()
        status = pane.findChild(QLabel, "formBuilder.state.status")
        assert status is not None and "now: no" in status.text() and "a yes or no" in status.text()
        _click(editor, "Key_Return", "ControlModifier")
        assert not editor.isVisible()
        assert session.log.undo_label() == "Set Enabled when for Discount rate"
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == "discountCheck"
        written = write_ui(session.document).text
        assert "cbcsEnabledWhen" in written and "discountCheck" in written
        assert session.log.undo()
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == ""
        assert session.log.undo_label() is None


def test_an_error_stays_open_and_esc_restores() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        editor = _editor(pane)
        assert not editor.horizontalScrollBar().isVisible()
        pad = pane.findChild(QWidget, "formBuilder.state.edit")
        state = pane.findChild(QWidget, "formBuilder.state")
        assert pad is not None and pad.layout() is not None and pad.layout().contentsMargins().left() == 12
        assert state is not None and editor.width() >= state.width() - 40
        QTest.keyClicks(editor, "missingField")
        pump()
        assert not editor.horizontalScrollBar().isVisible()
        _click(editor, "Key_Return", "ControlModifier")
        assert editor.isVisible()
        status = pane.findChild(QLabel, "formBuilder.state.status")
        assert status is not None and "Fix or press Esc to undo this formula" in status.text()
        assert "a window value" not in status.text()
        assert "now:" not in status.text()
        assert session.log.undo_label() is None
        _click(editor, "Key_Escape")
        assert not editor.isVisible()
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == ""


def test_leaving_a_finished_formula_saves_it() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        editor = _editor(pane)
        QTest.keyClicks(editor, "False")
        pump()
        other = QWidget()
        other.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus"))
        other.show()
        other.setFocus()
        pump()
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == "False"
        assert session.log.undo_label() == "Set Enabled when for Discount rate"
        other.close()


def test_clearing_the_field_is_its_own_undo() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        editor = _editor(pane)
        QTest.keyClicks(editor, "False")
        _click(editor, "Key_Return", "ControlModifier")
        open_state_row(pane, "cbcsEnabledWhen")
        editor = _editor(pane)
        _click(editor, "Key_A", "ControlModifier")
        _click(editor, "Key_Delete")
        _click(editor, "Key_Return", "ControlModifier")
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == ""
        assert session.log.undo_label() == "Clear Enabled when for Discount rate"


def test_ctrl_dot_applies_one_fix_and_lists_several() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountEdit")
        open_state_row(pane, "cbcsEnabledWhen")
        editor = _editor(pane)
        editor.setPlainText("=discountCheck")
        pump()
        _click(editor, "Key_Period", "ControlModifier")
        assert editor.toPlainText() == "discountCheck"
        assert session.log.undo_label() is None
        editor.setPlainText("TRUE && FALSE")
        pump()
        _click(editor, "Key_Period", "ControlModifier")
        fixes = pane.findChild(QListWidget, "formBuilder.formula.fixes")
        assert fixes is not None and fixes.isVisible() and fixes.count() >= 2
        assert editor.toPlainText() == "TRUE && FALSE"


def test_shift_enter_stops_at_six_lines(qapp: QApplication) -> None:
    del qapp
    window = QWidget()
    editor = FormulaEditor(window)
    layout = QVBoxLayout(window)
    layout.addWidget(editor)
    window.show()
    editor.setFocus()
    pump()
    assert editor.document().blockCount() == 1
    for _ in range(5):
        _click(editor, "Key_Return", "ShiftModifier")
    assert editor.document().blockCount() == 6
    _click(editor, "Key_Return", "ShiftModifier")
    assert editor.document().blockCount() == 6
    window.close()


@pytest.mark.parametrize("mode", ["light", "dark", "high_contrast_light", "high_contrast_dark"])
def test_an_error_underline_uses_the_theme_error_token(qapp: QApplication, mode: str) -> None:
    chrome = chrome_for(tokens_from_palette(qapp.palette(), force_mode=mode))
    assert chrome.error
    window = QWidget()
    editor = FormulaEditor(window)
    layout = QVBoxLayout(window)
    layout.addWidget(editor)
    window.resize(480, 160)
    window.show()
    editor.set_chrome(chrome)
    editor.set_context(FormulaEnv.for_test(), SlotKind.condition(), SimpleNamespace())
    editor.setPlainText("missingField")
    pump()
    _assert_underline(editor, chrome.error, "SingleUnderline")
    window.close()


def test_underlines_use_the_chrome_token_for_each_severity(qapp: QApplication) -> None:
    chrome = chrome_for(tokens_from_palette(qapp.palette(), force_mode="light"))
    assert chrome.error and chrome.warning and chrome.info
    window = QWidget()
    editor = FormulaEditor(window)
    layout = QVBoxLayout(window)
    layout.addWidget(editor)
    window.resize(480, 160)
    window.show()
    editor.set_chrome(chrome)
    editor.set_context(FormulaEnv.for_test(), SlotKind.condition(), SimpleNamespace())
    editor.setPlainText("missingField")
    pump()
    _assert_underline(editor, chrome.error, "SingleUnderline")
    warning = FormulaEnv.for_test(widgets={"oddEdit": WidgetFacts("QLineEdit", "Odd", kind="nope")})
    editor.set_context(warning, SlotKind.value(TEXT), SimpleNamespace())
    editor.setPlainText("oddEdit")
    pump()
    _assert_underline(editor, chrome.warning, "SingleUnderline")
    info = FormulaEnv.for_test(
        methods={"is_manager": MethodFacts("is_manager", 1, 2)},
        returns={},
    )
    editor.set_context(info, SlotKind.condition(), SimpleNamespace())
    editor.setPlainText("window.is_manager()")
    pump()
    _assert_underline(editor, chrome.info, "DotLine")
    window.close()


_ROW_KEYS = (
    "cbcsKind",
    "cbcsEnabledWhen",
    "cbcsVisibleWhen",
    "cbcsReadOnlyWhen",
    "cbcsValue",
    "cbcsFormat",
    "cbcsDefault",
)


@pytest.mark.timeout(120)
def test_wrapped_status_pushes_the_rows_below_it(qapp: QApplication) -> None:
    del qapp
    if os.environ.get("CBCS_FB_GEOM_CHILD") == "1":
        for width in (236, 300):
            _assert_status_clears_the_next_row(width)
        return
    for width in (236, 300):
        _assert_status_clears_the_next_row(width)
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
            "test_wrapped_status_pushes_the_rows_below_it",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    tail = "\n".join(text.splitlines()[-12:])
    # Qt teardown can SIGSEGV after a passing child. The shot harness allows it.
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), tail


def _assert_status_clears_the_next_row(width: int) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_2b1_k27 import _session
    from tests.form_builder.qtside.test_m7_2b1_shots import _pump, _set_inspector_width

    qapp = QApplication.instance()
    assert isinstance(qapp, QApplication)
    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, _path = _session(tmp, qapp)
    try:
        surface = kb.surface
        edit = surface.session.document.by_name("discountEdit")[0]
        inspector = surface.workbench.inspector
        surface.session.selection.set((edit,), source="canvas")
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        _pump(qapp)
        _set_inspector_width(window, width, qapp)
        open_state_row(inspector, "cbcsVisibleWhen")
        _pump(qapp)
        editor = _editor(inspector)
        editor.setPlainText("missingField")
        QApplication.processEvents()
        pump()
        _assert_block(inspector, list_open=False)
        editor.setPlainText("")
        QTest.keyClicks(editor, "disc")
        QApplication.processEvents()
        pump()
        _assert_block(inspector, list_open=True)
    finally:
        _close(window, qapp, guard)


def _mapped(widget: QWidget, root: QWidget) -> QRect:
    return QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())


def _assert_block(pane: QWidget, list_open: bool) -> None:
    state = pane.findChild(QWidget, "formBuilder.state")
    status = pane.findChild(QLabel, "formBuilder.state.status")
    pad = pane.findChild(QWidget, "formBuilder.state.edit")
    nxt = pane.findChild(QWidget, "formBuilder.state.row.cbcsReadOnlyWhen")
    assert state is not None and status is not None and pad is not None and nxt is not None
    assert state.width() <= 320, state.width()
    inspector = state.window().findChild(QWidget, "formBuilder.inspector")
    if inspector is not None:
        assert state.width() <= inspector.width(), (state.width(), inspector.width())
    assert status.isVisible() and "Fix or press Esc to undo this formula" in status.text()
    status_bottom = status.mapTo(state, QPoint(0, status.height())).y()
    next_top = nxt.mapTo(state, QPoint(0, 0)).y()
    assert status_bottom <= next_top, (status_bottom, next_top, status.height(), status.width())
    needed = status.heightForWidth(max(1, status.contentsRect().width()))
    assert status.height() + 1 >= needed, (status.height(), needed, status.contentsRect().width())
    pad_rect = _mapped(pad, state)
    for key in _ROW_KEYS:
        row = pane.findChild(QWidget, "formBuilder.state.row.%s" % key)
        assert row is not None and not row.isHidden()
        assert not pad_rect.intersects(_mapped(row, state))
    if not list_open:
        return
    listed = pane.findChild(QListWidget, "formBuilder.formula.complete")
    assert listed is not None and listed.isVisible()
    assert not _mapped(listed, state).intersects(_mapped(status, state))


def _assert_underline(editor: FormulaEditor, color: str, style_name: str) -> None:
    wanted = QColor(color).name().lower()
    styles = getattr(QTextCharFormat, "UnderlineStyle", QTextCharFormat)
    expected = getattr(styles, style_name)
    found = False
    for extra in editor.extraSelections():
        paint = extra.format.underlineColor().name().lower()
        if paint != wanted:
            continue
        found = True
        assert extra.format.underlineStyle() == expected
    assert found, color
