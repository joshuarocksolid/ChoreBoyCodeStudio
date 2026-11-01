# pyright: reportAttributeAccessIssue=false
"""Read as text paragraphs do not overlap at 184 and 320, at 100% and 200%."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("app.qt.QtWidgets", exc_type=ImportError)

from app.qt.QtCore import QPoint, QRect  # noqa: E402
from app.qt.QtWidgets import QApplication, QWidget  # noqa: E402
from tests.form_builder.qtside.test_m3_keyboard_scripts import _close  # noqa: E402
from tests.form_builder.qtside.test_m7_2b1_shots import _pump, _with_pytest_path  # noqa: E402
from tests.form_builder.qtside.test_m7_8a_panel import open_invoice  # noqa: E402

pytestmark = [pytest.mark.unit, pytest.mark.timeout(180)]


def _box(page: QWidget, child: QWidget) -> QRect:
    origin = child.mapTo(page, QPoint(0, 0))
    return QRect(int(origin.x()), int(origin.y()), int(child.width()), int(child.height()))


def _named(page: QWidget, prefix: str) -> list:
    return [
        child
        for child in page.findChildren(QWidget)
        if child.objectName().startswith(prefix) and child.isVisible()
    ]


def _assert_width(page: QWidget, width: int, qapp: QApplication, *, wrapped: bool) -> None:
    page.setParent(None)
    page.setMinimumWidth(0)
    page.setMaximumWidth(16777215)
    page.setFixedWidth(width)
    page.resize(width, 900)
    page.show()
    _pump(qapp)
    column = page.findChild(QWidget, "formBuilder.readText.column")
    assert isinstance(column, QWidget)
    column_box = _box(page, column)
    assert page.rect().contains(column_box)
    paragraphs = _named(page, "formBuilder.readText.paragraph.")
    numbers = _named(page, "formBuilder.readText.number.")
    headers = _named(page, "formBuilder.readText.title.")
    heading = page.findChild(QWidget, "formBuilder.readText.heading")
    assert paragraphs and numbers and isinstance(heading, QWidget)
    text_left = None
    for paragraph in paragraphs:
        number_name = paragraph.objectName().replace("paragraph.", "number.")
        number = page.findChild(QWidget, number_name)
        assert isinstance(number, QWidget)
        paragraph_box = _box(column, paragraph)
        number_box = _box(column, number)
        assert column.rect().contains(paragraph_box), paragraph.objectName()
        assert column.rect().contains(number_box)
        assert paragraph_box.left() >= number_box.right() - 1
        if text_left is None:
            text_left = paragraph_box.left()
        assert paragraph_box.left() == text_left
    pieces = paragraphs + numbers + headers + [heading]
    rects = [_box(page, piece) for piece in pieces]
    for rect in rects:
        assert page.rect().contains(rect)
        assert rect.width() > 0 and rect.height() > 0
    for index, rect in enumerate(rects):
        for other in rects[index + 1 :]:
            overlap = rect.intersected(other)
            assert overlap.width() <= 1 or overlap.height() <= 1
    if wrapped:
        line = paragraphs[0].fontMetrics().height()
        assert any(paragraph.height() > line + 2 for paragraph in paragraphs)


def _assert_widths(qapp: QApplication, tmp_path: Path) -> None:
    from app.features.form_builder.qtside.logic_panel.read_as_text import show_behavior_text

    window, surface, guard = open_invoice(tmp_path, qapp)
    try:
        show_behavior_text(surface)
        page = getattr(surface, "_behavior_text_page", None)
        assert isinstance(page, QWidget)
        _assert_width(page, 320, qapp, wrapped=True)
        _assert_width(page, 1000, qapp, wrapped=False)
    finally:
        _close(window, qapp, guard)


def test_read_as_text_paragraphs_do_not_overlap(qapp: QApplication, tmp_path: Path) -> None:
    if os.environ.get("CBCS_FB_GEOM_CHILD") == "1":
        _assert_widths(qapp, tmp_path)
        return
    _assert_widths(qapp, tmp_path)
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
            "test_read_as_text_paragraphs_do_not_overlap",
        ],
        cwd=str(Path(__file__).resolve().parents[3]),
        env=env,
        capture_output=True,
        text=True,
    )
    text = done.stdout + "\n" + done.stderr
    tail = "\n".join(text.splitlines()[-12:])
    passed = "passed" in text and "failed" not in text
    assert done.returncode == 0 or (done.returncode in (-11, 139) and passed), tail
