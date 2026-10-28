"""Delete page from the outline policy (UX-CONT-004)."""

from __future__ import annotations

import pytest

from app.features.form_builder.engine.commands.catalog_ext.pages import DeletePage
from app.features.form_builder.engine.query.outline import (
    AskDelete,
    Commit,
    ConfirmGesture,
    Idle,
    KeyGesture,
    OutlineCursor,
    OutlineWorld,
    plan,
    project,
)
from app.features.form_builder.engine.query.ref_index import RefIndex
from app.features.form_builder.engine.ui4.document import UiDocument
from tests.form_builder.engine.commands._support import nid, open_log

pytestmark = pytest.mark.unit

_TABS = """<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Form</class>
 <widget class="QWidget" name="Form">
  <widget class="QTabWidget" name="tabs">
   <widget class="QWidget" name="tab_empty">
    <attribute name="title"><string>Empty</string></attribute>
   </widget>
   <widget class="QWidget" name="tab_full">
    <attribute name="title"><string>Settings</string></attribute>
    <widget class="QLabel" name="inside"/>
   </widget>
  </widget>
 </widget>
 <resources/>
 <connections/>
</ui>
"""


def _world(doc: UiDocument) -> OutlineWorld:
    index = RefIndex()
    index.rebuild(doc)
    return OutlineWorld(index)


def _focus(node):  # type: ignore[no-untyped-def]
    return OutlineCursor(anchor=node, focus=node, selected=(node,))


def test_an_empty_page_deletes_immediately() -> None:
    log = open_log(_TABS)
    doc = log.document
    page = nid(doc, "tab_empty")
    effect = plan(doc, project(doc, frozenset(), lambda name: name), _focus(page), KeyGesture(key="delete"), _world(doc))
    assert isinstance(effect, Commit)
    assert isinstance(effect.commands[0], DeletePage)
    assert effect.toast == "Deleted page \u201cEmpty\u201d \u00b7 Undo"
    log.execute(effect.commands[0])
    assert log.document.by_name("tab_empty") == ()


def test_a_page_with_widgets_asks_and_confirm_deletes_the_page() -> None:
    log = open_log(_TABS)
    doc = log.document
    page = nid(doc, "tab_full")
    forest = project(doc, frozenset(), lambda name: name)
    effect = plan(doc, forest, _focus(page), KeyGesture(key="delete"), _world(doc))
    assert isinstance(effect, AskDelete)
    assert effect.prose.startswith("Delete page \u201cSettings\u201d and the 1 widget on it?")
    assert effect.ids == (page,)
    confirmed = plan(doc, forest, _focus(page), ConfirmGesture(effect.ids, True), _world(doc))
    assert isinstance(confirmed, Commit)
    assert isinstance(confirmed.commands[0], DeletePage)
    log.execute(confirmed.commands[0])
    assert log.document.by_name("tab_full") == ()
    assert log.document.by_name("inside") == ()


def test_cancelling_the_page_delete_changes_nothing() -> None:
    log = open_log(_TABS)
    doc = log.document
    page = nid(doc, "tab_full")
    effect = plan(doc, project(doc, frozenset(), lambda name: name), _focus(page), ConfirmGesture((page,), False), _world(doc))
    assert isinstance(effect, Idle)
    assert log.document.by_name("tab_full")
