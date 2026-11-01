# pyright: reportAttributeAccessIssue=false
"""Checks rows, the add page, and the offer do not overlap at 236 and 300."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.qt.QtCore import QPoint, QRect
from app.qt.QtWidgets import QApplication, QLabel, QLineEdit, QMenu, QPushButton, QWidget
from tests.form_builder.qtside.test_m7_2b1_shots import _pump, _set_inspector_width, _with_pytest_path

pytestmark = [pytest.mark.unit, pytest.mark.timeout(300)]


def _mapped(widget: QWidget, root: QWidget) -> QRect:
    return QRect(widget.mapTo(root, QPoint(0, 0)), widget.size())


def _walk(layout: object, root: QWidget) -> None:
    rects = []
    count = layout.count()  # type: ignore[attr-defined]
    for index in range(count):
        widget = layout.itemAt(index).widget()  # type: ignore[attr-defined]
        if widget is None or not widget.isVisible():
            continue
        rect = _mapped(widget, root)
        assert rect.left() >= -1, rect
        assert rect.right() <= root.width() + 1, (rect, root.width())
        rects.append((widget.objectName(), rect))
        child = widget.layout()
        if child is not None:
            _walk(child, root)
    rects.sort(key=lambda item: (item[1].top(), item[1].left()))
    for (left_name, left), (right_name, right) in zip(rects, rects[1:]):
        assert not left.intersects(right), (left_name, left, right_name, right)
        stacked = left.right() > right.left() and right.right() > left.left()
        if stacked and left.top() < right.top():
            assert left.bottom() <= right.top() + 1, (left_name, left, right_name, right)


def _assert_section(window: QWidget) -> None:
    section = window.findChild(QWidget, "formBuilder.checks")
    inspector = window.findChild(QWidget, "formBuilder.inspector")
    assert section is not None and inspector is not None
    assert section.width() <= inspector.width(), (section.width(), inspector.width())
    layout = section.layout()
    assert layout is not None
    _walk(layout, section)


def _open_required(window: QWidget, qapp: QApplication) -> None:
    add = window.findChild(QPushButton, "formBuilder.checks.add")
    assert add is not None
    add.click()
    _pump(qapp)
    menu = window.findChild(QMenu, "formBuilder.checks.menu")
    assert menu is not None
    picked = next(action for action in menu.actions() if action.data() == "required")
    picked.trigger()
    _pump(qapp)
    page = window.findChild(QWidget, "formBuilder.checks.page")
    assert page is not None and page.isVisible()
    message = window.findChild(QLineEdit, "formBuilder.checks.message")
    assert isinstance(message, QLineEdit)
    assert message.text()


def _assert_width(width: int) -> None:
    from app.features.form_builder.qtside.inspector import TabId
    from tests.form_builder.qtside.test_m3_keyboard_scripts import _close
    from tests.form_builder.qtside.test_m7_3b_k28 import _session

    qapp = QApplication.instance()
    assert isinstance(qapp, QApplication)
    tmp = Path(tempfile.mkdtemp()).resolve()
    window, kb, guard, _path = _session(tmp, qapp)
    try:
        surface = kb.surface
        edit = surface.session.document.by_name("emailEdit")[0]
        inspector = surface.workbench.inspector
        surface.session.selection.set((edit,), source="canvas")
        inspector.focus_tab(TabId.BEHAVIOR)
        inspector.flush()
        _pump(qapp)
        _set_inspector_width(window, width, qapp)
        _open_required(window, qapp)
        _set_inspector_width(window, width, qapp)
        _assert_section(window)
        when = window.findChild(QLabel, "formBuilder.checks.when")
        assert when is not None and when.text() == "Checked when: leaving the field"
        commit = window.findChild(QPushButton, "formBuilder.checks.commit")
        assert commit is not None and commit.isEnabled()
        commit.click()
        _pump(qapp)
        _set_inspector_width(window, width, qapp)
        offer = window.findChild(QWidget, "formBuilder.checks.offer")
        page = window.findChild(QWidget, "formBuilder.checks.page")
        assert offer is not None and offer.isVisible()
        assert page is not None and not page.isVisible()
        _assert_section(window)
        skip = window.findChild(QPushButton, "formBuilder.checks.notNow")
        assert skip is not None
        skip.click()
        _pump(qapp)
        _set_inspector_width(window, width, qapp)
        outline = window.findChild(QWidget, "formBuilder.checks.outlineLine")
        assert outline is not None and outline.isVisible()
        words = window.findChild(QLabel, "formBuilder.checks.outlineWords")
        assert words is not None and words.text() == "Fields that fail a check get no outline yet."
        _assert_section(window)
        add = window.findChild(QPushButton, "formBuilder.checks.add")
        assert add is not None
        add.click()
        _pump(qapp)
        menu = window.findChild(QMenu, "formBuilder.checks.menu")
        assert menu is not None and menu.isVisible()
        rects = [menu.actionGeometry(action) for action in menu.actions()]
        assert rects
        for left, right in zip(rects, rects[1:]):
            assert not left.intersects(right), (left, right)
            assert left.bottom() <= right.top() + 1
        menu.close()
    finally:
        _close(window, qapp, guard)


def test_checks_page_and_offer_fit_the_inspector(qapp: QApplication) -> None:
    del qapp
    if os.environ.get("CBCS_FB_GEOM_CHILD") == "1":
        for width in (236, 300):
            _assert_width(width)
        return
    for width in (236, 300):
        _assert_width(width)
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
            "--timeout",
            "300",
            "-q",
            str(Path(__file__).resolve()),
            "-k",
            "test_checks_page_and_offer_fit_the_inspector",
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
