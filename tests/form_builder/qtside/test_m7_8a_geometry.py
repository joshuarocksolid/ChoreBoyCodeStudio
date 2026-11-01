# pyright: reportAttributeAccessIssue=false
"""Logic rows stay inside the panel at the left pane's minimum and at 320."""

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


def _box(panel: QWidget, child: QWidget) -> QRect:
    origin = child.mapTo(panel, QPoint(0, 0))
    return QRect(int(origin.x()), int(origin.y()), int(child.width()), int(child.height()))


def _assert_width(panel: QWidget, width: int, qapp: QApplication) -> None:
    panel.setParent(None)
    panel.setMinimumWidth(0)
    panel.setMaximumWidth(width)
    panel.setFixedWidth(width)
    panel.resize(width, 640)
    panel.show()
    _pump(qapp)
    field = panel.findChild(QWidget, "formBuilder.logic.filter")
    assert field is not None
    bounds = panel.rect()
    box = _box(panel, field)
    assert box.width() > 0 and box.height() > 0
    assert bounds.contains(box)
    rows = [
        child
        for child in panel.findChildren(QWidget)
        if child.objectName().startswith("formBuilder.logic.row.") and child.isVisible()
    ]
    assert rows
    rects = []
    for row in rows:
        rect = _box(panel, row)
        assert rect.width() > 0 and rect.height() > 0, row.objectName()
        assert rect.left() >= -1, row.objectName()
        assert rect.right() <= bounds.right() + 1, row.objectName()
        rects.append(rect)
    for index, rect in enumerate(rects):
        for other in rects[index + 1 :]:
            overlap = rect.intersected(other)
            assert overlap.width() <= 1 or overlap.height() <= 1


def _assert_widths(qapp: QApplication, tmp_path: Path) -> None:
    window, surface, guard = open_invoice(tmp_path, qapp)
    try:
        panel = surface.findChild(QWidget, "formBuilder.logic")  # type: ignore[attr-defined]
        assert panel is not None
        for width in (184, 320):
            _assert_width(panel, width, qapp)
    finally:
        _close(window, qapp, guard)


def test_rows_stay_inside_the_panel(qapp: QApplication, tmp_path: Path) -> None:
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
            "test_rows_stay_inside_the_panel",
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
