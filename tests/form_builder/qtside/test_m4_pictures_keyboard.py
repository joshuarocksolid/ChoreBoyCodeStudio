# pyright: reportAttributeAccessIssue=false
"""K15 pictures (UX_SPEC §12.3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.qt.QtCore import QPoint, Qt
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLineEdit, QToolButton, QWidget
from tests.form_builder.inspector.test_m43c_pictures import (
    _close,
    _form,
    _pane,
    _press,
    _search,
    _seed,
    _select,
)

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("qapp")]


def test_k15_pictures(qapp: QApplication, tmp_path: Path) -> None:
    _seed(tmp_path, ("save.png", "dot.png", "other.png"))
    path = str(tmp_path / "form.ui")
    window, pane, session, realizer = _pane(qapp, _form(), path)
    try:
        original = session.text()
        _select(session, "ok")
        pane.flush()
        summary = pane.findChild(QWidget, "formBuilder.row.icon").findChild(QWidget, "formBuilder.summary")
        assert summary is not None
        summary.setFocus()
        _press(summary, Qt.Key.Key_Return)
        search = _search(qapp)
        assert isinstance(search, QLineEdit)
        QTest.keyClicks(search, "save")
        qapp.processEvents()
        _press(search, Qt.Key.Key_Down)
        grid = search.parent().findChild(QWidget, "formBuilder.pictureGrid")
        assert grid is not None and grid.hasFocus()
        _press(grid, Qt.Key.Key_Return)
        qapp.processEvents()
        assert len(session.log.entries()) == 1
        assert session.log.undo_label() == "Change icon of ok"
        assert "<normaloff>:/icons/save.png</normaloff>" in session.text()
        kept = session.text()
        summary.setFocus()
        _press(summary, Qt.Key.Key_Return)
        other = _search(qapp).window().findChild(QToolButton, "formBuilder.iconOtherStates")
        assert other is not None
        other.click()
        qapp.processEvents()
        disabled = other.window().findChild(QToolButton, "formBuilder.iconState.disabledoff")
        assert disabled is not None
        disabled.click()
        qapp.processEvents()
        search = _search(qapp)
        search.clear()
        QTest.keyClicks(search, "dot")
        qapp.processEvents()
        grid = search.parent().findChild(QWidget, "formBuilder.pictureGrid")
        assert grid is not None
        # A click picks without closing, so Esc can revert the whole session.
        QTest.mouseClick(grid, Qt.MouseButton.LeftButton, pos=QPoint(28, 48))
        qapp.processEvents()
        assert "disabledoff" in session.text()
        _press(grid, Qt.Key.Key_Escape)
        qapp.processEvents()
        assert session.text() == kept
        assert len(session.log.entries()) == 1
        assert session.log.undo()
        assert session.text() == original
    finally:
        _close(window, pane, realizer, session, qapp)
