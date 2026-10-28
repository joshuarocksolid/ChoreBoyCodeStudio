# pyright: reportAttributeAccessIssue=false
"""Opus gate repros for M3.7b (sizing sentences that do not follow the live widget)."""

from __future__ import annotations

import pytest

from app.qt.QtWidgets import QSplitter
from tests.form_builder.qtside.support import form, opened
from tests.form_builder.qtside.test_size_sentences import (
    _close,
    _events,
    _growth_sentence,
    _pane,
    _select,
    _show_root,
    _splitter,
    _why,
)

pytestmark = pytest.mark.usefixtures("qapp")


def _drag_grip(root: QSplitter, by: int) -> None:
    sizes = [int(size) for size in root.sizes()]
    root.setSizes([sizes[0] + by, sizes[1] - by])
    _events()
    _events()


def test_a_grip_drag_does_not_change_what_a_share_zero_pane_does_when_it_grows() -> None:
    # A share-0 pane next to a share-3 pane keeps its size when the splitter grows.
    # Dragging the grip is not growth, so the sentence must not change.
    with opened(_splitter(0, 3)) as (session, realizer):
        root = _show_root(realizer)
        assert isinstance(root, QSplitter)
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "left")
            first = _growth_sentence(_why(pane).text())
            _drag_grip(root, 40)
            after = _growth_sentence(_why(pane).text())
            assert after == first, (first, after)
        finally:
            _close(window, pane)


def test_a_grip_drag_does_not_erase_the_share_ratio() -> None:
    with opened(_splitter(1, 3)) as (session, realizer):
        root = _show_root(realizer)
        assert isinstance(root, QSplitter)
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, "right")
            first = _growth_sentence(_why(pane).text())
            _drag_grip(root, 40)
            after = _growth_sentence(_why(pane).text())
            assert "of every" in after, (first, after)
        finally:
            _close(window, pane)


_MAIN = form(
    'class="QMainWindow" name="Form"',
    """
  <property name="geometry"><rect><x>0</x><y>0</y><width>480</width><height>320</height></rect></property>
  <widget class="QWidget" name="centralwidget">
   <layout class="QVBoxLayout" name="verticalLayout">
    <item><widget class="QLineEdit" name="email"/></item>
   </layout>
  </widget>
  <widget class="QStatusBar" name="statusbar"/>
""",
)


@pytest.mark.parametrize("name", ["centralwidget", "statusbar"])
def test_main_window_parts_are_not_called_free(name: str) -> None:
    # The main window sizes its central widget and status bar; Placement does not.
    with opened(_MAIN) as (session, realizer):
        _show_root(realizer)
        window, pane = _pane(session, realizer)
        try:
            _select(session, pane, name)
            text = _why(pane).text()
            assert "as stored" not in text, text
        finally:
            _close(window, pane)
