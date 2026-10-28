"""Drop refusals and creations: wizard pages, wizard steps, scroll area content (UX-CAT-014, UX-CONT-010)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.drop_plan import commands_for
from app.features.form_builder.engine.query.drop_target import (
    WIZARD_REFUSAL,
    AcceptedDrop,
    DropPayload,
    RefusedDrop,
    _widget_host,
    resolve_drop,
)
from app.features.form_builder.engine.query.hit_index import Rect
from app.features.form_builder.engine.ui4.spec import Fragment, NodeSpec, PropertyEntry
from app.features.form_builder.engine.ui4.values import StringValue
from app.features.form_builder.engine.ui4.writer import write_ui
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

FORM = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QWidget" name="plain"/>
  <widget class="QWizard" name="wizard">
   <widget class="QWizardPage" name="wizardPage_1">
    <property name="title"><string>Step 1</string></property>
   </widget>
  </widget>
  <widget class="QScrollArea" name="scroll"/>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _button(name: str) -> Fragment:
    spec = NodeSpec(
        "widget",
        None,
        (("class_name", "QPushButton"), ("object_name", name)),
        (PropertyEntry("property", "text", StringValue(name)),),
    )
    return Fragment((spec,))


def _rects(doc):  # type: ignore[no-untyped-def]
    return {
        nid(doc, "Form"): Rect(0, 0, 400, 300),
        nid(doc, "plain"): Rect(10, 10, 100, 60),
        nid(doc, "wizard"): Rect(10, 100, 300, 180),
        nid(doc, "scroll"): Rect(200, 10, 180, 80),
    }


def test_a_wizard_page_outside_a_wizard_is_refused_with_the_spec_sentence() -> None:
    log = open_log(FORM)
    doc = log.document
    host = _widget_host(doc, _rects(doc), nid(doc, "Form"), "Form")
    assert host is not None
    target = resolve_drop(host, (20, 20), DropPayload("widget", (nid(doc, "wizardPage_1"),), wizard_page=True))
    assert isinstance(target, RefusedDrop)
    assert target.sentence == WIZARD_REFUSAL == "A wizard page can only go into a wizard."


def test_a_wizard_page_dropped_into_the_wizard_becomes_its_last_step() -> None:
    log = open_log(FORM)
    doc = log.document
    host = _widget_host(doc, _rects(doc), nid(doc, "Form"), "Form")
    assert host is not None
    payload = DropPayload("widget", (nid(doc, "plain"),), wizard_page=True)
    target = resolve_drop(host, (150, 150), payload)
    assert isinstance(target, AcceptedDrop) and target.action == "wizard_step"
    page = nid(doc, "plain")
    for command in commands_for(doc, target, payload, None):
        log.execute(command)
    wizard = doc.node(nid(doc, "wizard"))
    assert [child.object_name for child in wizard.child_widgets] == ["wizardPage_1", "plain"]  # type: ignore[attr-defined]
    assert page is not None
    assert log.undo()


def test_dropping_into_an_empty_scroll_area_makes_its_content_widget() -> None:
    log = open_log(FORM)
    doc = log.document
    scroll = nid(doc, "scroll")
    host = _widget_host(doc, _rects(doc), scroll, "scroll")
    assert host is not None
    target = resolve_drop(host, (250, 40), DropPayload("widget"))
    assert isinstance(target, AcceptedDrop) and target.action == "scroll_content"
    before = write_ui(doc).text
    for command in commands_for(doc, target, DropPayload("widget"), _button("okButton")):
        log.execute(command)
    area = doc.node(scroll)
    content = area.child_widgets[0]  # type: ignore[attr-defined]
    assert content.object_name == "scrollAreaWidgetContents"
    assert content.layout is not None and content.layout.class_name == "QVBoxLayout"
    assert content.layout.items[0].content.object_name == "okButton"  # type: ignore[union-attr]
    assert log.undo()
    assert write_ui(doc).text == before
    assert len(doc.node(scroll).child_widgets) == 0  # type: ignore[attr-defined]
