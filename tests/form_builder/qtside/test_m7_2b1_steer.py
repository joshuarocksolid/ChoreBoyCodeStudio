# pyright: reportAttributeAccessIssue=false
"""toggled → setEnabled asks for a rule. Keys choose. Esc chooses nothing."""

from __future__ import annotations

from typing import Tuple

import pytest

from app.features.form_builder.engine.logic.events import read_event
from app.qt.QtCore import Qt, QTimer
from app.qt.QtTest import QTest
from app.qt.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from app.features.form_builder.qtside.inspector.behavior_ext._rows import Gesture
from tests.form_builder.qtside.test_m7_2b1_state import _select, _stored, desk, pump

pytestmark = [pytest.mark.unit]

_ENABLED = (
    "Keep Discount rate enabled only while Discount is checked? "
    "A rule also gets this right when the form opens."
)
_VISIBLE = (
    "Keep Discount rate visible only while Discount is checked? "
    "A rule also gets this right when the form opens."
)


def _key(name: str) -> object:
    return getattr(getattr(Qt, "Key", Qt), name)


def _press(dialog: QWidget, key: str) -> None:
    QTest.keyClick(dialog, _key(key))  # type: ignore[arg-type]
    pump()


def _run(pane: object, slot: str, choose: object) -> None:
    events = pane.behavior.section_widget("events")  # type: ignore[attr-defined]
    QTimer.singleShot(0, choose)  # type: ignore[arg-type]
    events._run(Gesture("add_slot", signal="toggled", target="discountEdit", slot=slot))  # type: ignore[attr-defined]
    pump()


def _dialog() -> QWidget:
    found = QApplication.activeModalWidget()
    assert found is not None
    return found


def test_make_it_a_rule_writes_the_check_box_and_skips_the_slot() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountCheck")
        seen = {}

        def choose() -> None:
            dialog = _dialog()
            label = dialog.findChild(QLabel, "formBuilder.steer.sentence")
            rule = dialog.findChild(QPushButton, "formBuilder.steer.rule")
            connect = dialog.findChild(QPushButton, "formBuilder.steer.connect")
            assert label is not None and rule is not None and connect is not None
            seen["sentence"] = label.text()
            seen["rule"] = rule.text()
            seen["connect"] = connect.text()
            assert rule.isDefault()
            _press(rule, "Key_Return")

        _run(pane, "setEnabled(bool)", choose)
        assert seen["sentence"] == _ENABLED
        assert seen["rule"] == "Make it a rule" and seen["connect"] == "Connect anyway"
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == "discountCheck"
        assert read_event(session.document, "discountCheck", "toggled").steps == ()
        assert session.log.undo_label() == "Set Enabled when for Discount rate"


def test_connect_anyway_keeps_the_slot() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountCheck")

        def choose() -> None:
            dialog = _dialog()
            _press(dialog, "Key_Tab")
            focus = QApplication.focusWidget()
            assert focus is not None and focus.objectName() == "formBuilder.steer.connect"
            _press(focus, "Key_Return")

        _run(pane, "setEnabled(bool)", choose)
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == ""
        steps = read_event(session.document, "discountCheck", "toggled").steps
        assert len(steps) == 1 and steps[0].verb == "slot"
        assert steps[0].target == "discountEdit" and steps[0].slot.startswith("setEnabled")


def test_escape_writes_nothing() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountCheck")

        def choose() -> None:
            _press(_dialog(), "Key_Escape")

        _run(pane, "setEnabled(bool)", choose)
        assert _stored(session, "discountEdit", "cbcsEnabledWhen") == ""
        assert read_event(session.document, "discountCheck", "toggled").steps == ()
        assert session.log.undo_label() is None


def test_set_visible_asks_about_keeping_it_visible() -> None:
    with desk() as (session, pane):
        _select(session, pane, "discountCheck")
        seen = {}

        def choose() -> None:
            dialog = _dialog()
            label = dialog.findChild(QLabel, "formBuilder.steer.sentence")
            assert label is not None
            seen["sentence"] = label.text()
            _press(dialog, "Key_Escape")

        _run(pane, "setVisible(bool)", choose)
        assert seen["sentence"] == _VISIBLE
        assert _stored(session, "discountEdit", "cbcsVisibleWhen") == ""
