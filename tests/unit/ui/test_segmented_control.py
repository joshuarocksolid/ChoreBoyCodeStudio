"""Unit tests for the SegmentedControl widget."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide2.QtWidgets", exc_type=ImportError)

from PySide2.QtWidgets import QApplication

from app.ui.segmented_control import SegmentedControl

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module", autouse=True)
def _qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_add_segment_populates_buttons() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    assert "a" in ctrl._buttons
    assert "b" in ctrl._buttons
    assert ctrl._buttons["a"].text() == "Alpha"
    assert ctrl._buttons["b"].text() == "Beta"


def test_first_segment_is_selected_by_default() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    assert ctrl.selected_data() == "a"
    assert ctrl._buttons["a"].isChecked()
    assert not ctrl._buttons["b"].isChecked()


def test_set_selected_updates_active_segment() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    ctrl.set_selected("b")

    assert ctrl.selected_data() == "b"
    assert ctrl._buttons["b"].isChecked()
    assert not ctrl._buttons["a"].isChecked()


def test_set_selected_ignores_unknown_data() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")

    ctrl.set_selected("unknown")

    assert ctrl.selected_data() == "a"


def test_selection_changed_signal_fires_on_click() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    received: list[str] = []
    ctrl.selection_changed.connect(received.append)

    ctrl._buttons["b"].click()

    assert received == ["b"]
    assert ctrl.selected_data() == "b"


def test_clicking_active_segment_does_not_emit() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    received: list[str] = []
    ctrl.selection_changed.connect(received.append)

    ctrl._buttons["a"].click()

    assert received == []
    assert ctrl.selected_data() == "a"


def test_set_segment_enabled_false_prevents_selection() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    ctrl.set_segment_enabled("b", False)
    ctrl._buttons["b"].click()

    assert ctrl.selected_data() == "a"


def test_set_segment_enabled_false_prevents_programmatic_selection() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")
    ctrl.add_segment("Beta", "b")

    ctrl.set_segment_enabled("b", False)
    ctrl.set_selected("b")

    assert ctrl.selected_data() == "a"


def test_set_segment_tooltip() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Alpha", "a")

    ctrl.set_segment_tooltip("a", "Tooltip text")

    assert ctrl._buttons["a"].toolTip() == "Tooltip text"


def test_segment_position_properties() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("A", "a")
    ctrl.add_segment("B", "b")
    ctrl.add_segment("C", "c")

    assert ctrl._buttons["a"].property("segmentPosition") == "first"
    assert ctrl._buttons["b"].property("segmentPosition") == "middle"
    assert ctrl._buttons["c"].property("segmentPosition") == "last"


def test_single_segment_position_is_only() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("Solo", "s")

    assert ctrl._buttons["s"].property("segmentPosition") == "only"


def test_segment_active_property_tracks_selection() -> None:
    ctrl = SegmentedControl()
    ctrl.add_segment("A", "a")
    ctrl.add_segment("B", "b")

    assert ctrl._buttons["a"].property("segmentActive") is True
    assert ctrl._buttons["b"].property("segmentActive") is False

    ctrl.set_selected("b")

    assert ctrl._buttons["a"].property("segmentActive") is False
    assert ctrl._buttons["b"].property("segmentActive") is True
