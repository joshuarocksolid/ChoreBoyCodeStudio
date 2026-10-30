"""A bad name locks the event, and one gesture is one command."""

from __future__ import annotations

from app.features.form_builder.engine.commands.catalog_ext.events import SetEventSteps
from app.features.form_builder.engine.diagnostic_codes.fb4xx_logic import logic_diagnostics
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector.behavior_ext._rows import (
    Gesture,
    finish,
    project_sender,
)
from tests.form_builder.engine.commands._support import open_log

_PLAIN = (
    '[{"do": "slot", "target": "nameEdit", "slot": "clear()"},'
    ' {"do": "slot", "target": "other", "slot": "setFocus()"}]'
)
_BAD = '[{"do": "slot", "target": "123bad", "slot": "clear()"}]'
_UNKNOWN = '[{"do": "hyperjump"}, {"do": "slot", "target": "nameEdit", "slot": "clear()"}]'


def _form(steps: str, owner: str = "clearButton") -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QLineEdit" name="other"/></item>
   <item>
    <widget class="QPushButton" name="%s">
     <property name="text"><string>Clear</string></property>
     <property name="cbcsOnClicked" stdset="0"><string>%s</string></property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections/>
</ui>
""" % (owner, steps.replace("&", "&amp;").replace("<", "&lt;"))


def _doc(steps: str):
    return open_log(_form(steps)).document


def test_a_bad_identifier_locks_the_event_without_fb401_or_fb403() -> None:
    doc = _doc(_BAD)
    view = project_sender(doc, QtClassTable.shared(), "clearButton")
    assert view.events[0].locked
    assert view.events[0].steps
    assert "can't use (123bad)" in view.events[0].banner
    codes = [item.code for item in logic_diagnostics(doc)]
    assert "FB401" not in codes
    assert "FB403" not in codes
    assert finish(doc, QtClassTable.shared(), "clearButton", Gesture("toggle", "clicked", 0)) is None
    assert finish(doc, QtClassTable.shared(), "clearButton", Gesture("delete", "clicked", 0)) is None


def test_toggle_move_and_delete_each_return_one_command() -> None:
    doc = _doc(_PLAIN)
    classes = QtClassTable.shared()
    for gesture in (
        Gesture("toggle", "clicked", 0),
        Gesture("move", "clicked", 0, 1),
        Gesture("delete", "clicked", 1),
    ):
        outcome = finish(doc, classes, "clearButton", gesture)
        assert outcome is not None and isinstance(outcome.command, SetEventSteps)
        log = open_log(_form(_PLAIN))
        before = len(log.entries())
        log.execute(outcome.command)
        assert len(log.entries()) == before + 1


def test_a_move_past_the_end_is_a_status_and_no_command() -> None:
    doc = _doc(_PLAIN)
    classes = QtClassTable.shared()
    up = finish(doc, classes, "clearButton", Gesture("move", "clicked", 0, -1))
    down = finish(doc, classes, "clearButton", Gesture("move", "clicked", 1, 1))
    assert up is not None and up.command is None and up.status == "That is the first step."
    assert down is not None and down.command is None and down.status == "That is the last step."


def test_an_unknown_step_stays_in_the_command_and_is_not_edited() -> None:
    doc = _doc(_UNKNOWN)
    classes = QtClassTable.shared()
    view = project_sender(doc, classes, "clearButton")
    assert view.events[0].locked is False
    assert view.events[0].steps[0].unknown and view.events[0].steps[0].readonly
    assert view.events[0].steps[1].readonly is False
    assert finish(doc, classes, "clearButton", Gesture("toggle", "clicked", 0)) is None
    outcome = finish(doc, classes, "clearButton", Gesture("toggle", "clicked", 1))
    assert outcome is not None and isinstance(outcome.command, SetEventSteps)
    steps = outcome.command.steps
    assert steps[0].raw is not None and steps[0].verb == "hyperjump"
    assert steps[1].enabled is False
    codes = [item.code for item in logic_diagnostics(doc)]
    assert "FB401" not in codes


_HINTED = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <layout class="QVBoxLayout" name="verticalLayout">
   <item><widget class="QLineEdit" name="nameEdit"/></item>
   <item><widget class="QPushButton" name="clearButton"/></item>
  </layout>
 </widget>
 <resources/>
 <connections>
  <connection>
   <sender>clearButton</sender>
   <signal>clicked()</signal>
   <receiver>nameEdit</receiver>
   <slot>clear()</slot>
   <hints>
    <hint type="sourcelabel"><x>40</x><y>90</y></hint>
    <hint type="destinationlabel"><x>120</x><y>30</y></hint>
   </hints>
  </connection>
 </connections>
</ui>
"""


def _hint_block(text: str) -> str:
    return text[text.index("<hints>"):text.index("</hints>")] if "<hints>" in text else ""


def test_the_list_keeps_designer_hints_off_then_on_and_on_an_unchanged_end() -> None:
    """D25: the list's gestures carry hints; changing the arrow's end drops them (D7)."""
    from tests.form_builder.engine.commands._support import saved

    classes = QtClassTable.shared()

    def run(log, gesture) -> None:
        outcome = finish(log.document, classes, "clearButton", gesture)
        assert outcome is not None and outcome.command is not None
        log.execute(outcome.command)

    log = open_log(_HINTED)
    original = _hint_block(saved(log.document))
    run(log, Gesture("toggle", "clicked", 0))
    run(log, Gesture("toggle", "clicked", 0))
    assert _hint_block(saved(log.document)) == original
    # Stored as a list while off: re-choosing the same end writes nothing, so the hints stay.
    run(log, Gesture("toggle", "clicked", 0))
    same = finish(log.document, classes, "clearButton", Gesture("replace_slot", "clicked", 0, target="nameEdit", slot="clear()"))
    assert same is None
    run(log, Gesture("toggle", "clicked", 0))
    assert _hint_block(saved(log.document)) == original
    run(log, Gesture("replace_slot", "clicked", 0, target="nameEdit", slot="selectAll()"))
    assert "<hints>" not in saved(log.document)
